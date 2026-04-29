"""
app/services/oidc/factory.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
지정된 provider_name으로 OIDC/SSO 공급자 인스턴스를 반환합니다.
HMG SSO 엔진 탑재.
"""

from app.core.config import settings
from app.services.oidc.base import BaseOIDCProvider
from app.services.oidc.hmg_provider import HMGOIDCProvider
from app.utils.exceptions import BadRequest


def get_oidc_provider(provider_name: str, redirect_uri: str) -> BaseOIDCProvider:
    """provider명에 맞는 OIDC 통신 어댑터 객체를 결합 생성합니다."""

    # hmg-sso를 default provider 패턴으로 채택
    if provider_name.lower() in ("hmg", "hmg-sso"):
        if not settings.HMG_SSO_BASE_URL or not settings.HMG_SSO_CLIENT_ID:
            raise BadRequest("HMG SSO 연동 환경변수가 누락되어 인스턴스를 생성할 수 없습니다.")
            
        return HMGOIDCProvider(
            client_id=settings.HMG_SSO_CLIENT_ID,
            client_secret=settings.HMG_SSO_CLIENT_SECRET or "",
            redirect_uri=redirect_uri,
            base_url=settings.HMG_SSO_BASE_URL,
        )

    raise BadRequest(f"지원하지 않은 인증 공급자 체계입니다: {provider_name}")
