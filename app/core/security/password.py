"""
app/core/security/password.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
bcrypt 패스워드 해싱 유틸리티.
"""
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """평문 패스워드를 bcrypt 해시로 변환합니다."""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """평문 패스워드와 해시를 비교합니다."""
    return pwd_context.verify(plain, hashed)
