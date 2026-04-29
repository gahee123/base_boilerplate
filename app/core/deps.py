"""
app/core/deps.py
~~~~~~~~~~~~~~~~
FastAPI 의존성 주입 모듈.

DB 세션, Redis 클라이언트, JWT 쿠키 인증, RBAC 권한 체크 등을 제공.
"""
from uuid import UUID

import jwt
from fastapi import Depends, Request
from fastapi.security import APIKeyCookie
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import decode_token
from app.crud.user import crud_user
from app.models.user import User, UserRole
from app.utils.exceptions import Forbidden, Unauthorized

# HttpOnly 쿠키 인증 수단
oauth2_cookie = APIKeyCookie(name="access_token", auto_error=False)


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """HttpOnly 쿠키 기반 인증으로 현재 사용자를 추출합니다."""
    # 1. Header(Authorization: Bearer) 우선 추출, 없으면 Cookie(access_token) 폴백
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    
    if not token:
        token = request.cookies.get("access_token") # 기존 호환성 유지
            
    if not token:
        raise Unauthorized("Access Token 토큰 없음", error_code="AUTH_001")

    # 2. 토큰 디코딩 및 서명 검증
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError as e:
        raise Unauthorized("Access Token 만기", error_code="AUTH_002") from e
    except jwt.InvalidTokenError as e:
        raise Unauthorized("Access Token 유효하지 않음", error_code="AUTH_003") from e

    # 3. 토큰 타입 검증
    if payload.get("token_type") != "access":
        raise Unauthorized("엑세스 토큰이 아닙니다.")

    # 4. 블랙리스트 확인
    redis = await get_redis()
    if redis:
        jti = payload.get("jti")
        if jti and await redis.get(f"bl:{jti}"):
            raise Unauthorized("로그아웃된 세션입니다. 다시 시도해주세요.")

    # 5. 비활동 세션 만료 확인 + TTL 리셋 (Sliding Window)
    user_id_str = payload.get("sub", "")
    if redis and user_id_str:
        from app.services.auth import auth_service
        session_alive = await auth_service.touch_session(redis, user_id_str)
        if not session_alive:
            raise Unauthorized(
                "장시간 미사용으로 세션이 만료되었습니다. 다시 로그인해주세요."
            )

    # 6. DB에서 사용자 조회
    try:
        user_id = UUID(payload["sub"])
    except (KeyError, ValueError) as e:
        raise Unauthorized("잘못된 인증 식별자입니다.") from e

    user = await crud_user.get(db, id=user_id)
    if not user:
        raise Unauthorized("Access Token 토큰은 유효하나 해당 사용자를 찾을 수 없습니다", error_code="AUTH_006")

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """상태가 활성화된 사용자만 반환합니다."""
    if current_user.role == UserRole.PERMISSION_REQUIRED:
        raise Forbidden("권한 요청이 필요합니다.", error_code="AUTH_007")
    if current_user.role == UserRole.PERMISSION_REQUESTED:
        raise Forbidden("권한 승인 대기 중입니다.", error_code="AUTH_008")
    
    if not current_user.is_active:
        raise Forbidden("비활성화된 계정입니다. 관리자에게 문의하세요.")
    return current_user


def requires_role(*roles: UserRole):
    """5단계 RBAC 역할 기반 접근 제어 의존성 팩토리."""
    async def role_checker(
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        if current_user.role not in roles:
            # 명세된 권한 부족 에러 매핑
            if roles == (UserRole.SUPERADMIN,):
                raise Forbidden("슈퍼 관리자 권한 필요", error_code="AUTH_010")
            elif UserRole.ADMIN in roles:
                raise Forbidden("관리자 권한 필요", error_code="AUTH_009")
                
            required = ", ".join(r.value for r in roles)
            raise Forbidden(f"이 기능은 [{required}] 권한이 필요합니다. 현재 수준: {current_user.role.value}")
        return current_user
    return role_checker
