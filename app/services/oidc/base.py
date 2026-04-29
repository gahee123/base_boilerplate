"""
app/services/oidc/base.py
~~~~~~~~~~~~~~~~~~~~~~~~~
OIDC/SSO 통합 인증 인터페이스 (Abstract Class).

HMG SSO 및 기타 확장을 위한 추상 클래스입니다.
"""
from abc import ABC, abstractmethod
from typing import TypedDict


class OIDCUserInfo(TypedDict):
    """표준화된 HMG SSO 유저 정보 반환 스펙.

    Java(VTDM) JwtTokenDto.UserInfoDto / UserDetailsDto 구조를 평면화한 것입니다.
    """
    email: str                    # Java: userinfo.mail
    employee_id: str              # Java: userid 또는 payload.uid
    full_name: str | None         # Java: userinfo.displayName
    department: str | None        # Java: userinfo.department (팀명)
    department_code: str | None   # Java: userinfo.departmentCode (팀코드)
    site: str | None              # Java: site (회사코드 — H199_W 등)


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
        """
        사용자를 리다이렉트시킬 로그인 엔드포인트 URL을 생성하여 반환합니다.
        필요 시 내부적인 Healthcheck를 선행할 수 있습니다.
        """
        pass

    @abstractmethod
    async def process_callback(
        self,
        code: str,
        code_verifier: str,
        nonce: str,
        state: str = "",
    ) -> tuple[str, OIDCUserInfo]:
        """
        Authorization Code를 Access Token 및 ID Token으로 교환한 뒤,
        ID Token을 파싱/검증하여 (id_token_hint, OIDCUserInfo) 튜플로 반환합니다.
        """
        pass
