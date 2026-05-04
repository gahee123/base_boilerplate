import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import hashlib
import base64
import jwt
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security.deps import get_current_active_user, get_current_user
from app.core.security.jwt import decode_access_token, decode_refresh_token
from app.crud.user import crud_user
from app.models.user import User
from app.schemas.auth import (
    AuthCodeRequest,
    MessageResponse,
    TokenResponse,
)
from app.services.auth.service import auth_service
from app.services.auth.oidc.factory import get_oidc_provider
from app.services.auth.sso.error_handler import HmgHealthcheckError
from app.utils.exceptions import BadRequest, Unauthorized

router = APIRouter(tags=["Authentication"], prefix="/auth")
logger = logging.getLogger(__name__)


@router.get("/{provider}/login", response_model=Any)
async def login_via_sso(
    provider: str,
    request: Request,
    upform: str = Query("N", description="상단바 유무 (Y/N)"),
    site: str = Query(None, description="HMG 사이트 코드"),
):
    """
    SSO 로그인을 위한 Authorize URL을 생성하고 클라이언트를 리다이렉트시킵니다.
    """
    state = str(uuid4())
    nonce = str(uuid4())
    code_verifier = str(uuid4()) + str(uuid4())
    # PKCE S256 생성
    sha256_hash = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(sha256_hash).decode().replace("=", "")

    redirect_uri = f"{settings.BACKEND_URL}/api/v1/auth/{provider}/callback"
    auth_provider = get_oidc_provider(provider, redirect_uri)

    try:
        login_url = await auth_provider.get_login_url(
            state=state,
            nonce=nonce,
            code_challenge=code_challenge,
            client_ip=request.client.host if request.client else "127.0.0.1",
            upform=upform,
            site=site,
        )
    except HmgHealthcheckError as e:
        logger.error("SSO Healthcheck 실패: %s", e.message)
        raise e

    redis = await get_redis()
    if redis:
        sso_data = {
            "state": state,
            "nonce": nonce,
            "code_verifier": code_verifier,
        }
        await redis.set(f"sso_state:{state}", str(sso_data), ex=600)

    return {"login_url": login_url}


@router.get("/{provider}/callback")
async def sso_callback(
    provider: str,
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
):
    """
    SSO 인증 후 돌아오는 콜백 엔드포인트.
    """
    redis = await get_redis()
    if not redis:
        raise HTTPException(status_code=500, detail="Redis connection error")

    stored_data_str = await redis.get(f"sso_state:{state}")
    if not stored_data_str:
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error=INVALID_STATE")

    stored_data = eval(stored_data_str.decode() if isinstance(stored_data_str, bytes) else stored_data_str)
    await redis.delete(f"sso_state:{state}")

    redirect_uri = f"{settings.BACKEND_URL}/api/v1/auth/{provider}/callback"
    auth_provider = get_oidc_provider(provider, redirect_uri)

    try:
        id_token, user_info = await auth_provider.process_callback(
            code=code,
            code_verifier=stored_data["code_verifier"],
            nonce=stored_data["nonce"],
            state=state,
        )
        
        user = await auth_service.sso_sync_user(db, user_info)
        await db.flush()

        auth_code = await auth_service.generate_auth_code(redis, user.id)
        
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/sso-callback?code={auth_code}")

    except Exception as e:
        logger.exception("SSO 콜백 처리 중 오류 발생")
        error_msg = str(e)
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/login?error=AUTH_FAILED&message={error_msg}")


@router.post("/token", response_model=TokenResponse)
async def exchange_token(
    request: AuthCodeRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """
    임시 코드를 실제 JWT 토큰(Access/Refresh)으로 교환합니다.
    """
    redis = await get_redis()
    user_id = await auth_service.exchange_auth_code(redis, request.code)
    
    if not user_id:
        raise BadRequest("유효하지 않거나 만료된 인증 코드입니다.")

    user = await crud_user.get(db, id=user_id)
    if not user or not user.is_active:
        raise Unauthorized("인증된 사용자를 찾을 수 없거나 비활성 상태입니다.")

    tokens = auth_service.create_tokens(user)
    
    response.set_cookie(
        key="access_token",
        value=tokens["access_token"],
        httponly=True,
        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
        secure=True,
    )
    response.set_cookie(
        key="refresh_token",
        value=tokens["refresh_token"],
        httponly=True,
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        samesite="lax",
        secure=True,
    )

    await auth_service.activate_session(redis, str(user.id))

    return TokenResponse(
        access_token=tokens["access_token"],
        token_type="bearer",
        user_id=user.id,
        role=user.role.value
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    response: Response,
    refresh_token: str = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Refresh Token을 사용하여 새로운 Access Token을 발급받습니다.
    """
    if not refresh_token:
        raise Unauthorized("Refresh Token이 없습니다.")

    try:
        payload = decode_refresh_token(refresh_token)
        if payload.get("token_type") != "refresh":
            raise Unauthorized("유효하지 않은 토큰 타입입니다.")
            
        user_id = payload.get("sub")
        user = await crud_user.get(db, id=user_id)
        
        if not user or not user.is_active:
            raise Unauthorized("사용자를 찾을 수 없거나 비활성 상태입니다.")

        tokens = auth_service.create_tokens(user)
        
        response.set_cookie(
            key="access_token", value=tokens["access_token"],
            httponly=True, secure=True, samesite="lax",
            max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
        response.set_cookie(
            key="refresh_token", value=tokens["refresh_token"],
            httponly=True, secure=True, samesite="lax",
            max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        )
        
        return TokenResponse(
            access_token=tokens["access_token"],
            token_type="bearer",
            user_id=user.id,
            role=user.role.value
        )
    except jwt.PyJWTError:
        raise Unauthorized("유효하지 않은 Refresh Token입니다.")


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
):
    """
    로그아웃을 수행하고 토큰을 블랙리스트에 추가합니다.
    (role에 관계없이 유효한 토큰이면 로그아웃 가능)
    Authorization 헤더 및 HttpOnly 쿠키 모두에서 토큰을 읽어 블랙리스트 처리합니다.
    """
    # Authorization 헤더 또는 쿠키에서 토큰 추출 (get_current_user와 동일한 우선순위)
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    if not token:
        token = request.cookies.get("access_token")

    redis = await get_redis()
    if token:
        try:
            payload = decode_access_token(token)
            jti = payload.get("jti")
            exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
            await auth_service.logout(redis, jti, exp, user_id=str(current_user.id))
        except Exception:
            pass

    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")

    return MessageResponse(message="성공적으로 로그아웃되었습니다.")
