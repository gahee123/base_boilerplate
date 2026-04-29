"""
app/api/v1/endpoints/auth.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
OIDC 및 SSO 인증 전용 엔드포인트.
Access Token(Body) + Refresh Token(Cookie) 시스템 구현.
"""
import base64
import hashlib
import json
import os
import urllib.parse
from datetime import UTC, datetime
import jwt
import uuid
import logging
from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_active_user
from app.core.redis import get_redis
from app.core.security import decode_token
from app.crud.user import crud_user
from app.models.user import User
from app.schemas.auth import AuthCodeRequest, TokenResponse, MessageResponse
from app.schemas.user import UserResponse
from app.services.auth import auth_service
from app.services.oidc.factory import get_oidc_provider
from app.utils.exceptions import BadRequest, Unauthorized, Forbidden

from app.utils.routing import AutoWrapRouter

logger = logging.getLogger(__name__)

router = AutoWrapRouter(prefix="/auth", tags=["Authentication"])


def generate_pkce() -> tuple[str, str]:
    """PKCE 해시 챌린지 생성 헬퍼"""
    verifier = base64.urlsafe_b64encode(os.urandom(32)).decode("utf-8").rstrip("=")
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
    return verifier, challenge


def _get_client_ip(request: Request) -> str:
    """클라이언트 IP 주소 추출."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    if request.client:
        ip = request.client.host
        if ip == "::1" or ip == "0:0:0:0:0:0:0:1":
            return "127.0.0.1"
        return ip
    return "127.0.0.1"


@router.get("/{provider}/login")
async def oidc_login(
    provider: str,
    request: Request,
    site: str | None = None,
    upform: str | None = None,
    redis: object = Depends(get_redis),
):
    if not redis:
        raise Unauthorized("인프라 연결 오류: Redis가 오프라인입니다.")

    redirect_uri = settings.HMG_SSO_CALLBACK_URI or str(request.url_for("oidc_callback", provider=provider))
    auth_provider = get_oidc_provider(provider, redirect_uri)

    state = str(uuid.uuid4())
    nonce = str(uuid.uuid4())
    verifier, challenge = generate_pkce()

    session_data = {"verifier": verifier, "nonce": nonce}
    await redis.set(f"sso_state:{state}", json.dumps(session_data), ex=300) # type: ignore

    frontend_url = settings.HMG_SSO_FRONTEND_LOGIN_CALLBACK_URL or "http://localhost:3000/callback"

    try:
        client_ip = _get_client_ip(request)
        url = await auth_provider.get_login_url(
            state=state, 
            nonce=nonce, 
            code_challenge=challenge,
            client_ip=client_ip, 
            upform=upform,
            site=site,
        )
        return RedirectResponse(url)
    except Exception as e:
        logger.error(f"SSO Login Initiation Error: {str(e)}")
        # Healthcheck 실패 등 초기화 에러 시 프론트엔드로 에러 리다이렉트
        error_msg = "인증 서버(HMG) 연결에 실패했습니다."
        if "3000" in str(e):
            error_msg = "등록되지 않은 사이트 코드입니다."
        
        return RedirectResponse(url=f"{frontend_url}?error=INIT_FAILED&message={urllib.parse.quote(error_msg)}")


@router.get("/{provider}/callback")
async def oidc_callback(
    provider: str,
    code: str | None = None,
    state: str = "",
    error: str | None = None,
    error_description: str | None = None,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    redis: object = Depends(get_redis),
):
    if not redis:
        raise Unauthorized("백엔드 캐시 오류가 발생했습니다.")

    frontend_url = settings.HMG_SSO_FRONTEND_LOGIN_CALLBACK_URL or "http://localhost:3000/callback"

    try:
        # 1. HMG SSO 자체 에러 처리
        if error:
            msg = _parse_error_message(error, error_description)
            return RedirectResponse(url=f"{frontend_url}?error={error}&message={urllib.parse.quote(msg)}")

        if not code:
            return RedirectResponse(url=f"{frontend_url}?error=NO_CODE&message={urllib.parse.quote('인증 코드가 없습니다')}")

        # 2. 세션 검증 (CSRF 방어)
        session_raw = await redis.get(f"sso_state:{state}") # type: ignore
        if not session_raw:
            return RedirectResponse(url=f"{frontend_url}?error=SESSION_EXPIRED&message={urllib.parse.quote('로그인 세션이 만료되었습니다. 다시 시도해주세요.')}")
        
        await redis.delete(f"sso_state:{state}") # type: ignore
        
        session_data = json.loads(session_raw)
        verifier = session_data["verifier"]
        nonce = session_data["nonce"]

        redirect_uri = settings.HMG_SSO_CALLBACK_URI or str(request.url_for("oidc_callback", provider=provider))
        auth_provider = get_oidc_provider(provider, redirect_uri)

        # 3. OIDC 프로필 획득 및 유저 동기화
        id_token, user_info = await auth_provider.process_callback(code, verifier, nonce, state)
        user = await auth_service.sso_sync_user(db, user_info)
        
        # 4. 임시 인증 코드 생성
        auth_code = await auth_service.generate_auth_code(redis, user.id)

        # 성공 리다이렉트
        return RedirectResponse(url=f"{frontend_url}?status=success&code={auth_code}")

    except Exception as e:
        logger.error(f"SSO Callback Error: {str(e)}")
        error_code = "AUTH_FAILED"
        message = "인증 처리 중 오류가 발생했습니다."
        
        if isinstance(e, (Unauthorized, BadRequest, Forbidden)):
            message = e.detail
            error_code = "VALIDATION_ERROR"
            
        # quote 에러 방지를 위해 문자열 캐스팅 및 기본값 처리
        safe_message = urllib.parse.quote(str(message or "인증 처리 중 오류가 발생했습니다."))
        return RedirectResponse(url=f"{frontend_url}?error={error_code}&message={safe_message}")


@router.post("/token", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def exchange_token(
    request_data: AuthCodeRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: object = Depends(get_redis),
):
    """임시 코드를 Access/Refresh 토큰으로 교환합니다."""
    user_id = await auth_service.exchange_auth_code(redis, request_data.code)
    if not user_id:
        raise Unauthorized("유효하지 않거나 만료된 인증 코드입니다.")

    user = await crud_user.get(db, id=user_id)
    if not user or not user.is_active:
        raise Forbidden("비활성 사용자이거나 존재하지 않는 사용자입니다.")

    tokens = auth_service.create_tokens(user)
    
    # 세션 활성화 (Sliding Window)
    await auth_service.activate_session(redis, str(user.id))

    # Refresh Token은 HttpOnly 쿠키에 저장
    response.set_cookie(
        key="refresh_token",
        value=tokens["refresh_token"],
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.APP_ENV == "production"
    )

    return TokenResponse(
        access_token=tokens["access_token"],
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: object = Depends(get_redis),
):
    """Refresh Token을 사용하여 Access Token을 갱신합니다."""
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise Unauthorized("리프레시 토큰이 없습니다.")

    try:
        payload = decode_token(refresh_token)
        if payload.get("token_type") != "refresh":
            raise Unauthorized("유효하지 않은 토큰 타입입니다.")
        
        user_id = payload.get("sub")
        user = await crud_user.get(db, id=user_id)
        if not user or not user.is_active:
            raise Forbidden("사용자를 찾을 수 없거나 비활성 상태입니다.")

        # 새로운 토큰 쌍 생성
        tokens = auth_service.create_tokens(user)
        
        # 세션 갱신
        await auth_service.touch_session(redis, str(user.id))

        # 쿠키 갱신
        response.set_cookie(
            key="refresh_token",
            value=tokens["refresh_token"],
            max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
            httponly=True,
            samesite="lax",
            secure=settings.APP_ENV == "production"
        )

        return TokenResponse(access_token=tokens["access_token"])
    except jwt.PyJWTError:
        raise Unauthorized("유효하지 않거나 만료된 리프레시 토큰입니다.")


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_active_user)):
    """현재 로그인한 사용자 정보를 반환합니다."""
    return UserResponse.model_validate(current_user)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    response: Response,
    redis: object | None = Depends(get_redis),
):
    """로그아웃 처리 (토큰 블랙리스트 및 쿠키 삭제)"""
    # 1. Access Token 블랙리스트 (Bearer 헤더에서 추출)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        try:
            payload = decode_token(token)
            token_jti = payload.get("jti", "")
            user_id = payload.get("sub", "")
            token_exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
            await auth_service.logout(redis, token_jti=token_jti, token_exp=token_exp, user_id=user_id)
        except jwt.PyJWTError:
            pass

    # 2. 쿠키 삭제
    response.delete_cookie("refresh_token")
    
    return MessageResponse(message="로그아웃 되었습니다.")


def _parse_error_message(error: str, error_description: str | None) -> str:
    if error_description:
        desc_upper = error_description.upper()
        if any(k in desc_upper for k in ["BLOCKED", "RETIRED", "SUSPENDED", "REST"]):
            return "로그인 권한이 없는 사용자입니다."
        if "HEALTHCHECK" in desc_upper:
            return "HEALTHCHECK를 먼저 진행해주세요."
        if "EXPIRED" in desc_upper:
            return "비밀번호가 만료되었습니다."
    return f"SSO 인증에 실패했습니다: {error}"
