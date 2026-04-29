"""
tests/test_auth.py
~~~~~~~~~~~~~~~~~~
인증 관련 통합 테스트.
회원가입, 로그인, 토큰 갱신, 로그아웃 시나리오를 검증합니다.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password
from app.models.user import User


@pytest.mark.asyncio
class TestRegister:
    """회원가입 테스트 클래스."""

    async def test_register_success(self, client: AsyncClient, db_session: AsyncSession):
        """성공적인 회원가입 시나리오."""
        payload = {
            "email": "new@example.com",
            "password": "NewPassword123!",
            "full_name": "신규 가입자"
        }
        response = await client.post("/api/v1/auth/register", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == payload["email"]
        assert data["full_name"] == payload["full_name"]
        assert "id" in data
        assert "password" not in data  # 비밀번호 미노출 확인

        # DB 저장 확인
        result = await db_session.execute(select(User).filter_by(email=payload["email"]))
        user = result.scalar_one()
        assert user.email == payload["email"]
        assert verify_password(payload["password"], user.hashed_password)

    async def test_register_duplicate_email(self, client: AsyncClient, test_user: User):
        """중복 이메일 가입 시도 시 409 에러."""
        payload = {
            "email": test_user.email,
            "password": "AnotherPassword123!",
            "full_name": "중복인"
        }
        response = await client.post("/api/v1/auth/register", json=payload)

        assert response.status_code == 409
        assert "이미 등록된 이메일" in response.json()["error"]["message"]


@pytest.mark.asyncio
class TestLogin:
    """로그인 테스트 클래스."""

    async def test_login_success(self, client: AsyncClient, test_user: User):
        """성공적인 로그인 시나리오 (OAuth2 Password Flow)."""
        data = {
            "username": test_user.email,
            "password": "Password123!"  # conftest.py의 test_user 비밀번호
        }
        response = await client.post("/api/v1/auth/login", data=data)  # form-data
        
        assert response.status_code == 200
        token_data = response.json()
        assert "access_token" in token_data
        assert "refresh_token" in token_data
        assert token_data["token_type"] == "bearer"

    async def test_login_wrong_password(self, client: AsyncClient, test_user: User):
        """잘못된 비밀번호 입력 시 401 에러."""
        data = {
            "username": test_user.email,
            "password": "WrongPassword"
        }
        response = await client.post("/api/v1/auth/login", data=data)

        assert response.status_code == 401
        assert "올바르지 않습니다" in response.json()["error"]["message"]


@pytest.mark.asyncio
class TestTokenRefresh:
    """토큰 갱신 테스트 클래스."""

    async def test_refresh_success(self, client: AsyncClient, test_user: User):
        """유효한 Refresh Token으로 새 토큰 발급."""
        # 1. 먼저 로그인하여 리프레시 토큰 획득
        login_data = {"username": test_user.email, "password": "Password123!"}
        login_res = await client.post("/api/v1/auth/login", data=login_data)
        refresh_token = login_res.json()["refresh_token"]

        # 2. 갱신 요청
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token}
        )

        assert response.status_code == 200
        new_tokens = response.json()
        assert "access_token" in new_tokens
        assert new_tokens["access_token"] != login_res.json()["access_token"]


@pytest.mark.asyncio
class TestLogout:
    """로그아웃 테스트 클래스."""

    async def test_logout_success(self, client: AsyncClient, test_user: User):
        """로그아웃 시 블랙리스트 등록 및 접근 차단."""
        # 1. 로그인
        login_data = {"username": test_user.email, "password": "Password123!"}
        login_res = await client.post("/api/v1/auth/login", data=login_data)
        headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        # 2. 로그아웃 수행
        logout_res = await client.post("/api/v1/auth/logout", headers=headers)
        assert logout_res.status_code == 204

        # 3. 동일한 토큰으로 다시 접근 시도 (차단되어야 함)
        protected_res = await client.get("/api/v1/users/me", headers=headers)
        # Note: 인프라 에이전트 단계에서 Redis 블랙리스트를 구현했다면 401이 나옴
        assert protected_res.status_code == 401
