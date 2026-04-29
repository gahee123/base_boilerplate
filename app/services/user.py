"""
app/services/user.py
~~~~~~~~~~~~~~~~~~~~
사용자 조회 및 관리 비즈니스 로직.

HMG SSO 전환으로 인해 로컬 비밀번호 및 프로필 수정 기능은 제거되었습니다.
Admin의 역할/상태 변경 기능만 제공합니다.
"""
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.user import crud_user
from app.models.user import User, UserRole
from app.schemas.base import PaginatedResponse
from app.schemas.user import UserAdminUpdate, UserRejectRequest
from app.utils.exceptions import BadRequest, Forbidden, NotFound


class UserService:
    """사용자 서비스.

    일반 사용자 프로필 조회와 Admin 사용자 상태 관리 로직을 제공합니다.
    """

    async def get_me(self, *, current_user: User) -> User:
        """내 프로필 조회.
        이미 인증 의존성에서 DB 조회가 완료된 user 객체를 반환합니다.
        """
        return current_user

    async def list_admins(self, db: AsyncSession) -> list[User]:
        """관리자(Admin, SuperAdmin) 목록 조회."""
        return await crud_user.get_multi_by_roles(
            db, roles=[UserRole.ADMIN, UserRole.SUPERADMIN]
        )

    async def list_pending_users(self, db: AsyncSession) -> list[User]:
        """승인 대기(PERMISSION_REQUESTED) 상태인 사용자 목록 조회."""
        return await crud_user.get_multi_by_roles(
            db, roles=[UserRole.PERMISSION_REQUESTED]
        )

    async def list_users(
        self,
        db: AsyncSession,
        *,
        page: int = 1,
        size: int = 20,
    ) -> PaginatedResponse:
        """사용자 목록 조회 (Admin 전용, 페이지네이션)."""
        return await crud_user.get_paginated(db, page=page, size=size)

    async def get_user(self, db: AsyncSession, *, user_id: UUID) -> User:
        """특정 사용자 조회 (Admin 전용)."""
        user = await crud_user.get(db, id=user_id)
        if not user:
            raise NotFound("사용자를 찾을 수 없습니다.")
        return user

    async def update_user(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        user_in: UserAdminUpdate,
        current_user: User,
    ) -> User:
        """특정 사용자 수정 (Admin 전용).

        - Admin은 role, is_active 등 시스템 상태 필드만 수정할 수 있습니다.
        - 관리자(ADMIN, SUPERADMIN) 권한으로의 승격이나 강등은 SUPERADMIN만 가능합니다.
        """
        user = await crud_user.get(db, id=user_id)
        if not user:
            raise NotFound("사용자를 찾을 수 없습니다.")

        update_data = user_in.model_dump(exclude_unset=True)

        # 권한(role) 변경 시 보안 검증
        if "role" in update_data:
            new_role = update_data["role"]
            # 1. 대상 유저가 이미 관리자이거나, 새로운 역할이 관리자급인 경우 -> SUPERADMIN만 수정 가능
            is_target_admin = user.role in [UserRole.ADMIN, UserRole.SUPERADMIN]
            is_new_role_admin = new_role in [UserRole.ADMIN, UserRole.SUPERADMIN]

            if (is_target_admin or is_new_role_admin) and current_user.role != UserRole.SUPERADMIN:
                raise Forbidden("관리자 권한 변경은 SuperAdmin만 가능합니다.")

        return await crud_user.update(db, db_obj=user, obj_in=update_data)

    async def delete_user(self, db: AsyncSession, *, user_id: UUID) -> User:
        """특정 사용자 삭제 — Soft delete (Admin 전용)."""
        user = await crud_user.remove(db, id=user_id)
        if not user:
            raise NotFound("사용자를 찾을 수 없습니다.")
        return user

    async def approve_user(self, db: AsyncSession, *, user_id: UUID) -> User:
        """사용자 승인 처리 (PERMISSION_REQUESTED -> USER)."""
        user = await crud_user.get(db, id=user_id)
        if not user:
            raise NotFound("사용자를 찾을 수 없습니다.")

        if user.role != UserRole.PERMISSION_REQUESTED:
            raise BadRequest(
                f"현재 사용자 상태가 {user.role} 입니다. "
                "사용자가 '권한 신청'을 완료한(PERMISSION_REQUESTED) 상태에서만 승인이 가능합니다."
            )

        # 역할 업데이트 및 활성화
        update_data = {"role": UserRole.USER, "is_active": True}
        return await crud_user.update(db, db_obj=user, obj_in=update_data)

    async def request_permission(self, db: AsyncSession, *, current_user: User) -> User:
        """사용권한 신청 (PERMISSION_REQUIRED -> PERMISSION_REQUESTED)."""
        if current_user.role != UserRole.PERMISSION_REQUIRED:
            raise BadRequest(f"현재 권한 상태({current_user.role})에서는 신청할 수 없습니다.")

        update_data = {"role": UserRole.PERMISSION_REQUESTED}
        return await crud_user.update(db, db_obj=current_user, obj_in=update_data)

    async def reject_user(
        self, db: AsyncSession, *, user_id: UUID, reject_in: UserRejectRequest
    ) -> User:
        """사용자 승인 거절 (비활성화 및 로그 기록)."""
        user = await crud_user.get(db, id=user_id)
        if not user:
            raise NotFound("사용자를 찾을 수 없습니다.")

        # 거절 사유는 감사 로그(AuditableMixin)에 남게 됩니다. (role/is_active 변경 이력)
        # 실제 운영 환경에서는 별도의 'rejection_reason' 컬럼이 있으면 좋으나, 현재는 비활성화로 처리합니다.
        update_data = {"is_active": False}
        return await crud_user.update(db, db_obj=user, obj_in=update_data)


user_service = UserService()
