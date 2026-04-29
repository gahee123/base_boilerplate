"""
tests/test_users.py
~~~~~~~~~~~~~~~~~~~
사용자 관리 통합 테스트.
내 프로필 조회/수정 및 Admin 전용 관리 기능을 검증합니다.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole
from tests.conftest import get_auth_headers


@pytest.mark.asyncio
class TestUserProfile:
    """일반 사용자 프로필 관련 테스트."""

    async def test_get_my_profile_success(self, client: AsyncClient, test_user: User):
        """본인의 프로필 조회 (성공)."""
        headers = get_auth_headers(test_user)
        response = await client.get("/api/v1/users/me", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_user.email
        assert data["id"] == str(test_user.id)

    async def test_update_my_profile_success(self, client: AsyncClient, test_user: User, db_session: AsyncSession):
        """본인의 프로필 정보 수정 (성공)."""
        headers = get_auth_headers(test_user)
        payload = {"full_name": "수정된 이름"}

        response = await client.patch("/api/v1/users/me", json=payload, headers=headers)

        assert response.status_code == 200
        assert response.json()["full_name"] == payload["full_name"]

        # DB 반영 확인
        await db_session.refresh(test_user)
        assert test_user.full_name == payload["full_name"]

    async def test_get_profile_unauthorized(self, client: AsyncClient):
        """인증 없이 프로필 조회 시도 (실패)."""
        response = await client.get("/api/v1/users/me")
        assert response.status_code == 401


@pytest.mark.asyncio
class TestUserAdmin:
    """관리자 전용 사용자 관리 테스트."""

    async def test_list_users_as_admin(self, client: AsyncClient, admin_user: User, test_user: User):
        """관리자 권한으로 사용자 목록 조회 (성공)."""
        headers = get_auth_headers(admin_user)
        response = await client.get("/api/v1/users/", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "meta" in data
        assert len(data["data"]) >= 2  # admin + test_user

    async def test_list_users_as_normal_user(self, client: AsyncClient, test_user: User):
        """일반 사용자 권한으로 사용자 목록 조회 시도 (권한 부족 에러)."""
        headers = get_auth_headers(test_user)
        response = await client.get("/api/v1/users/", headers=headers)

        assert response.status_code == 403
        assert "권한이 필요합니다" in response.json()["error"]["message"]

    async def test_admin_update_user_role(self, client: AsyncClient, admin_user: User, test_user: User, db_session: AsyncSession):
        """관리자가 다른 사용자의 역할(Role)을 변경 (성공)."""
        headers = get_auth_headers(admin_user)
        payload = {"role": UserRole.ADMIN.value}

        response = await client.patch(f"/api/v1/users/{test_user.id}", json=payload, headers=headers)

        assert response.status_code == 200
        assert response.json()["role"] == UserRole.ADMIN.value

        await db_session.refresh(test_user)
        assert test_user.role == UserRole.ADMIN

    async def test_admin_delete_user_soft(self, client: AsyncClient, admin_user: User, test_user: User, db_session: AsyncSession):
        """관리자가 사용자를 삭제 (Soft Delete)."""
        headers = get_auth_headers(admin_user)

        response = await client.delete(f"/api/v1/users/{test_user.id}", headers=headers)
        assert response.status_code == 204

        # DB 확인 (Soft Delete이므로 레코드는 남아있지만 deleted_at이 있어야 함)
        # 단, CRUDBase에서 기본 필터링을 걸었으므로 직접 쿼리 필요
        result = await db_session.execute(
            select(User).filter(User.id == test_user.id)
        )
        deleted_user = result.scalar_one()
        assert deleted_user.deleted_at is not None
