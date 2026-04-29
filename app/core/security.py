"""
app/core/security.py
~~~~~~~~~~~~~~~~~~~~
보안 유틸리티.

bcrypt 패스워드 해싱 및 JWT 토큰 생성/검증을 담당합니다.
"""
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from passlib.context import CryptContext

from app.core.config import settings

# ── 패스워드 해싱 ────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """평문 패스워드를 bcrypt 해시로 변환합니다."""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """평문 패스워드와 해시를 비교합니다.

    Timing Attack에 안전한 bcrypt 내장 비교 사용.
    """
    return pwd_context.verify(plain, hashed)


# ── JWT 토큰 ─────────────────────────────────────────────────
def create_access_token(user_id: UUID, role: str) -> str:
    """Access Token을 생성합니다.

    Payload:
        sub: 사용자 UUID (문자열 변환)
        role: 사용자 역할
        exp: 만료 시각
        iat: 발급 시각
        jti: 토큰 고유 ID (UUID, 블랙리스트 용)
        token_type: "access"

    Returns:
        JWT 인코딩된 문자열
    """
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
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: UUID) -> str:
    """Refresh Token을 생성합니다.

    Access Token보다 긴 수명(기본 7일)을 가지며,
    Access Token 갱신 시 사용됩니다.

    Returns:
        JWT 인코딩된 문자열
    """
    now = datetime.now(UTC)
    expire = now + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": now,
        "jti": str(uuid4()),
        "token_type": "refresh",
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """JWT를 디코딩하고 검증합니다.

    검증 항목:
        - 서명 유효성 (SECRET_KEY + ALGORITHM)
        - 만료 시간 (exp)

    Raises:
        jwt.ExpiredSignatureError: 토큰 만료
        jwt.InvalidTokenError: 서명 불일치 등 토큰 무효

    Returns:
        디코딩된 payload 딕셔너리
    """
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
