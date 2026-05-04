"""
app/services/auth/oidc/base.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
OIDC/SSO 통합 인증 인터페이스.
"""
from abc import ABC, abstractmethod
from typing import TypedDict


class OIDCUserInfo(TypedDict):
    """표준화된 HMG SSO 유저 정보 반환 스펙."""
    email: str
    employee_id: str
    full_name: str | None
    department: str | None
    department_code: str | None
    site: str | None


class BaseOIDCProvider(ABC):
    """OIDC 기반 통합 인증 어댑터 추상 클래스."""

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    @abstractmethod
    async def get_login_url(
        self,
        state: str,
        nonce: str,
        code_challenge: str,
        client_ip: str = "127.0.0.1",
        **kwargs,
    ) -> str:
        pass

    @abstractmethod
    async def process_callback(
        self,
        code: str,
        code_verifier: str,
        nonce: str,
        state: str = "",
    ) -> tuple[str, OIDCUserInfo]:
        pass
