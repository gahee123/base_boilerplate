"""
app/api/v1/endpoints/auth.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
OIDC 및 SSO 인증 전용 엔드포인트.

로컬 Auth를 철거하고 완전히 HMG 플랫폼의 PKCE Flow 기반 쿠키 로그인을 수행합니다.
"""
import base64
import hashlib
import json
import os
import urllib.parse
from datetime import UTC, datetime

import jwt
from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_active_user
from app.core.redis import get_redis
from app.core.security import decode_token
from app.models.user import User
from app.schemas.user import UserResponse
from app.services.auth import auth_service
from app.services.oidc.factory import get_oidc_provider
from app.utils.exceptions import BadRequest, Unauthorized

router = APIRouter(prefix="/auth", tags=["Authentication"])


def generate_pkce() -> tuple[str, str]:
    """PKCE 해시 챌린지 생성 헬퍼"""
    verifier = base64.urlsafe_b64encode(os.urandom(32)).decode("utf-8").rstrip("=")
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
    return verifier, challenge


def _get_client_ip(request: Request) -> str:
    """
    클라이언트 IP 주소 추출.
    Java(VTDM) IpUtil.getIp() 호환 — 프록시 환경 대응.
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    if request.client:
        ip = request.client.host
        # IPv6 loopback → IPv4 표기 (Java 호환)
        if ip == "::1" or ip == "0:0:0:0:0:0:0:1":
            return "127.0.0.1"
        return ip
    return "127.0.0.1"


@router.get(
    "/{provider}/login",
    summary="HMG SSO 인가 리다이렉트",
    description="PKCE 보안 챌린지를 생성하고 브라우저를 HMG 로그인 화면으로 전환합니다."
)
async def oidc_login(
    provider: str,
    request: Request,
    login_type: str | None = None,
    site_code: str | None = None,
    redis: object = Depends(get_redis),
):
    if not redis:
        raise Unauthorized("인프라 연결 오류: Redis가 오프라인입니다.")

    # 프록시(Ingress) 환경 대응용 URL 추출
    redirect_uri = settings.HMG_SSO_CALLBACK_URI or str(request.url_for("oidc_callback", provider=provider))
    auth_provider = get_oidc_provider(provider, redirect_uri)

    state = base64.urlsafe_b64encode(os.urandom(16)).decode("utf-8").rstrip("=")
    nonce = base64.urlsafe_b64encode(os.urandom(16)).decode("utf-8").rstrip("=")
    verifier, challenge = generate_pkce()

    # Callback 검증을 위해 보안 값들을 세션 DB에 유지 (TTL 5분)
    session_data = {"verifier": verifier, "nonce": nonce}
    await redis.set(f"sso_state:{state}", json.dumps(session_data), ex=300) # type: ignore

    # Java(VTDM): Healthcheck에 사용자 IP 필요
    client_ip = _get_client_ip(request)

    url = await auth_provider.get_login_url(
        state=state,
        nonce=nonce,
        code_challenge=challenge,
        client_ip=client_ip,
        login_type=login_type,
        site_code=site_code,
    )
    return RedirectResponse(url)


@router.get(
    "/{provider}/callback",
    summary="SSO 인가 콜백 및 쿠키 주입",
    description="HMG 통신망으로부터 Code를 넘겨받아 AccessToken 교환 후 백엔드 HttpOnly 쿠키를 세팅합니다."
)
async def oidc_callback(
    provider: str,
    code: str | None = None,
    state: str = "",
    error: str | None = None,
    error_description: str | None = None,
    request: Request = None,
    response: Response = None,
    db: AsyncSession = Depends(get_db),
    redis: object = Depends(get_redis),
):
    if not redis:
        raise Unauthorized("백엔드 캐시 오류가 발생했습니다.")

    frontend_url = settings.HMG_SSO_FRONTEND_LOGIN_CALLBACK_URL or "http://localhost:3000"

    # Java(VTDM): HmgSsoController.callback() — 에러 파라미터 우선 처리
    if error:
        msg = _parse_error_message(error, error_description)
        encoded_msg = urllib.parse.quote(msg, safe="")
        return RedirectResponse(url=f"{frontend_url}?status=fail&message={encoded_msg}")

    if not code:
        encoded_msg = urllib.parse.quote("인증 코드가 없습니다", safe="")
        return RedirectResponse(url=f"{frontend_url}?status=fail&message={encoded_msg}")

    # 1. State 기반 세션 데이터 획득을 통한 CSRF 보호 탈출
    session_raw = await redis.get(f"sso_state:{state}") # type: ignore
    if not session_raw:
        raise BadRequest("로그인 세션이 만료되었습니다. 다시 로그인 버튼을 클릭해주세요.")
    await redis.delete(f"sso_state:{state}") # type: ignore
    
    session_data = json.loads(session_raw)
    verifier = session_data["verifier"]
    nonce = session_data["nonce"]

    redirect_uri = settings.HMG_SSO_CALLBACK_URI or str(request.url_for("oidc_callback", provider=provider))
    auth_provider = get_oidc_provider(provider, redirect_uri)

    # 2. RS256/AES-GCM 하드코어 보안 검증 후 OIDC 프로필 파싱
    id_token, user_info = await auth_provider.process_callback(code, verifier, nonce, state)
    
    # 3. 유저 DB 생성 혹은 정보 업데이트. 화이트리스트 접근 제어 판별
    user = await auth_service.sso_sync_user(db, user_info)
    
    # 4. 앱 구동용 쿠키 발급
    access_token = auth_service.create_session_token(user)

    # 5. Redis 비활동 세션 활성화 (Sliding Window TTL 시작)
    await auth_service.activate_session(redis, str(user.id))

    redirect_resp = RedirectResponse(url=f"{frontend_url}?status=success&message={urllib.parse.quote('로그인 성공', safe='')}")

    is_secure = settings.APP_ENV == "production"
    # 쿠키 max-age: JWT 절대 만료와 동기화 (비활동 만료는 Redis가 담당)
    max_age = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60

    redirect_resp.set_cookie(
        key="access_token",
        value=access_token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=is_secure
    )
    # 추후 완벽한 로그아웃(HMG 본진 로그아웃) 처리에 사용되는 실마리 보존
    redirect_resp.set_cookie(
        key="id_token_hint",
        value=id_token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=is_secure
    )

    return redirect_resp


@router.get(
    "/status",
    status_code=status.HTTP_200_OK,
    response_model=UserResponse,
    summary="HttpOnly 쿠키 인증 상태 검열",
)
async def auth_status(current_user: User = Depends(get_current_active_user)):
    """현재 브라우저-백엔드 구간의 HttpOnly 쿠키가 무사히 파싱되는지 검증하고 프로필을 전달합니다."""
    return UserResponse.model_validate(current_user)


@router.post(
    "/logout",
    summary="블랙리스트 기반 로그아웃 지원",
)
async def logout(
    request: Request,
    response: Response,
    redis: object | None = Depends(get_redis),
):
    """
    1) 백엔드 Access 쿠키 즉시 삭제 처리
    2) 토큰 재사용 방지용 블랙리스트 캐싱
    3) HMG 플랫폼과의 접점 해제를 위한 로그아웃 링크(id_token 기반) 반환 (결국 FrontEnd 가 GET 날림)
    """
    token = request.cookies.get("access_token")
    id_token_hint = request.cookies.get("id_token_hint")
    
    if token:
        try:
            payload = decode_token(token)
            token_jti = payload.get("jti", "")
            user_id = payload.get("sub", "")
            token_exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
            await auth_service.logout(
                redis, token_jti=token_jti, token_exp=token_exp, user_id=user_id
            )
        except jwt.InvalidTokenError:
            pass
            
    response.delete_cookie("access_token")
    response.delete_cookie("id_token_hint")

    # Java(VTDM): HmgSsoServiceImpl.generateLogoutUrl() 호환
    hmg_logout_url = None
    if settings.HMG_SSO_BASE_URL and id_token_hint:
        post_logout = settings.HMG_SSO_POST_LOGOUT_REDIRECT_URI or "http://localhost:3000"
        hmg_logout_url = (
            f"{settings.HMG_SSO_BASE_URL}/logout"
            f"?id_token_hint={id_token_hint}"
            f"&post_logout_redirect_uri={post_logout}"
        )

    return {
        "message": "로컬 세션 로그아웃 조치가 완료되었습니다.", 
        "hmg_logout_url": hmg_logout_url
    }


def _parse_error_message(error: str, error_description: str | None) -> str:
    """
    Java(VTDM) HmgSsoController.parseErrorMessage() +
              HmgErrorUtil.AuthorizeResponse 호환 에러 메시지 파싱.
    """
    if error_description:
        desc_upper = error_description.upper()
        if "BLOCKED" in desc_upper or "RETIRED" in desc_upper or "SUSPENDED" in desc_upper or "REST" in desc_upper:
            return "로그인 권한이 없는 사용자입니다."
        if "HEALTHCHECK" in desc_upper:
            return "HEALTHCHECK를 먼저 진행해주세요."
        if "EXPIRED" in desc_upper:
            return "비밀번호가 만료되었습니다."
    return f"SSO 인증에 실패했습니다: {error}"
