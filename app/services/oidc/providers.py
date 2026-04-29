"""
app/services/oidc/providers.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
PoC용 소셜 로그인 (Google, Kakao) 컴포넌트 통합 구현체.
BaseOIDCProvider를 상속받습니다.
"""
from urllib.parse import urlencode

import httpx

from app.services.oidc.base import BaseOIDCProvider, OIDCUserInfo
from app.utils.exceptions import AppException, Unauthorized


class GoogleOIDCProvider(BaseOIDCProvider):
    """Google OAuth2/OIDC 제공자.
    
    PoC 및 초기 도입 목적을 위한 인증 어댑터입니다.
    """

    AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

    async def get_login_url(self, state: str = "") -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "offline",
            "state": state,
        }
        return f"{self.AUTHORIZATION_URL}?{urlencode(params)}"

    async def get_token_from_code(self, code: str) -> str:
        data = {
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
            "grant_type": "authorization_code",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(self.TOKEN_URL, data=data)

        if response.status_code != 200:
            raise AppException(message="Google: 인증 코드로 발급에 실패했습니다.", detail=response.text)

        return response.json().get("access_token")

    async def get_user_info(self, access_token: str) -> OIDCUserInfo:
        headers = {"Authorization": f"Bearer {access_token}"}

        async with httpx.AsyncClient() as client:
            response = await client.get(self.USERINFO_URL, headers=headers)

        if response.status_code != 200:
            raise Unauthorized("Google: 사용자 프로필 조회에 실패했습니다.")

        user_data = response.json()

        return OIDCUserInfo(
            provider="google",
            social_id=user_data.get("sub"),
            email=user_data.get("email"),
            full_name=user_data.get("name")
        )


class KeycloakOIDCProvider(BaseOIDCProvider):
    """Keycloak 전용 OIDC 제공자."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        base_url: str,
        internal_base_url: str,
        realm: str,
    ):
        super().__init__(client_id, client_secret, redirect_uri)
        # Keycloak 표준 엔드포인트 구성
        self.base_url = base_url.rstrip("/")
        self.internal_base_url = internal_base_url.rstrip("/")
        self.realm = realm
        
        # 브라우저 리다이렉트용 (외부망)
        self.auth_url = f"{self.base_url}/realms/{self.realm}/protocol/openid-connect/auth"
        
        # 서버 간 통신용 (내부망/Docker Network)
        self.token_url = f"{self.internal_base_url}/realms/{self.realm}/protocol/openid-connect/token"
        self.userinfo_url = f"{self.internal_base_url}/realms/{self.realm}/protocol/openid-connect/userinfo"

    async def get_login_url(self, state: str = "") -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
        }
        return f"{self.auth_url}?{urlencode(params)}"

    async def get_token_from_code(self, code: str) -> str:
        data = {
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
            "grant_type": "authorization_code",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(self.token_url, data=data)

        if response.status_code != 200:
            raise AppException(message="Keycloak: 토큰 발급에 실패했습니다.", detail=response.text)

        return response.json().get("access_token")

    async def get_user_info(self, access_token: str) -> OIDCUserInfo:
        headers = {"Authorization": f"Bearer {access_token}"}

        async with httpx.AsyncClient() as client:
            response = await client.get(self.userinfo_url, headers=headers)

        if response.status_code != 200:
            raise Unauthorized("Keycloak: 사용자 정보를 조회할 수 없습니다.")

        user_data = response.json()

        return OIDCUserInfo(
            provider="keycloak",
            social_id=user_data.get("sub"),  # Keycloak 표준 식별자 sub 사용
            email=user_data.get("email"),
            full_name=user_data.get("name") or user_data.get("preferred_username"),
        )
