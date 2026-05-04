"""
app/core/security/jwt.py
~~~~~~~~~~~~~~~~~~~~~~~~
JWT 토큰 생성 및 검증 모듈.
"""
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt

from app.core.config import settings


def create_access_token(user_id: UUID, role: str) -> str:
    """Access Token을 생성합니다."""
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": expire,
        "iat": now,
        "jti": str(uuid4()),
        "token_type": "access",
    }
    return jwt.encode(payload, settings.ACCESS_TOKEN_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: UUID) -> str:
    """Refresh Token을 생성합니다."""
    now = datetime.now(UTC)
    expire = now + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": now,
        "jti": str(uuid4()),
        "token_type": "refresh",
    }
    return jwt.encode(payload, settings.REFRESH_TOKEN_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Access Token을 디코딩하고 검증합니다."""
    return jwt.decode(
        token,
        settings.ACCESS_TOKEN_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )


def decode_refresh_token(token: str) -> dict:
    """Refresh Token을 디코딩하고 검증합니다."""
    return jwt.decode(
        token,
        settings.REFRESH_TOKEN_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )


# 하위 호환용 (기존 decode_token은 Access Token 검증으로 기본 설정)
def decode_token(token: str) -> dict:
    return decode_access_token(token)
