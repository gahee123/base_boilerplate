"""
app/services/user_group.py
~~~~~~~~~~~~~~~~~~~~~~~~~
부서(UserGroup) 관리 비즈니스 로직.
화이트리스트 상태 변경 시 소속 사용자들의 권한을 자동으로 동기화합니다.
"""
import logging
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.user import crud_user
from app.crud.user_group import crud_user_group
from app.models.user import User, UserGroup, UserRole
from app.schemas.base import PaginatedResponse
from app.schemas.user_group import UserGroupCreate, UserGroupUpdate
from app.utils.exceptions import NotFound

logger = logging.getLogger(__name__)


class UserGroupService:
    """부서 관리 서비스."""

    async def list_groups(
        self,
        db: AsyncSession,
        *,
        page: int = 1,
        size: int = 20,
    ) -> PaginatedResponse:
        """부서 목록 조회 (페이지네이션)."""
        return await crud_user_group.get_paginated(db, page=page, size=size)

    async def list_group_users(
        self,
        db: AsyncSession,
        *,
        group_id: UUID,
        page: int = 1,
        size: int = 20,
    ) -> PaginatedResponse:
        """특정 부서에 속한 사용자 목록 조회 (페이지네이션)."""
        group = await crud_user_group.get(db, id=group_id)
        if not group:
            raise NotFound("부서를 찾을 수 없습니다.")

        users, total = await crud_user.get_paginated_by_dept(
            db, dept_code=group.code, page=page, size=size
        )
        return PaginatedResponse(
            items=users, total=total, page=page, size=size, pages=(total // size) + 1
        )

    async def create_group(
        self, db: AsyncSession, *, obj_in: UserGroupCreate
    ) -> UserGroup:
        """신규 부서 생성 및 초기 권한 동기화."""
        group = await crud_user_group.create(db, obj_in=obj_in)
        
        # 화이트리스트로 생성된 경우 기존 유저들 즉시 승격
        if group.whitelisted:
            await self.sync_group_members_role(db, group=group)
            
        return group

    async def update_group(
        self, db: AsyncSession, *, group_id: UUID, obj_in: UserGroupUpdate
    ) -> UserGroup:
        """부서 정보 수정 및 화이트리스트 상태 변경 시 권한 동기화."""
        group = await crud_user_group.get(db, id=group_id)
        if not group:
            raise NotFound("부서를 찾을 수 없습니다.")

        old_whitelisted = group.whitelisted
        updated_group = await crud_user_group.update(db, db_obj=group, obj_in=obj_in)

        # 화이트리스트 상태가 변경된 경우에만 유저 동기화 실행
        if old_whitelisted != updated_group.whitelisted:
            await self.sync_group_members_role(db, group=updated_group)

        return updated_group

    async def delete_group(self, db: AsyncSession, *, group_id: UUID) -> None:
        """부서 삭제 (Soft Delete)."""
        group = await crud_user_group.remove(db, id=group_id)
        if not group:
            raise NotFound("부서를 찾을 수 없습니다.")

    async def sync_group_members_role(self, db: AsyncSession, *, group: UserGroup) -> int:
        """
        부서의 화이트리스트 상태에 따라 소속 사용자들의 역할을 일괄 변경합니다.
        
        - whitelisted=True: PERMISSION_REQUIRED -> USER
        - whitelisted=False: USER, ADMIN -> PERMISSION_REQUIRED (SUPERADMIN 제외)
        """
        if group.whitelisted:
            # 승격: 승인대기 상태인 유저만 USER로 변경
            stmt = (
                update(User)
                .where(
                    User.department_code == group.code,
                    User.role == UserRole.PERMISSION_REQUIRED
                )
                .values(role=UserRole.USER)
            )
            action = "승격 (Required -> User)"
        else:
            # 강등: 일반 유저 및 관리자를 승인대기로 변경 (SUPERADMIN은 시스템 보호를 위해 제외)
            stmt = (
                update(User)
                .where(
                    User.department_code == group.code,
                    User.role.in_([UserRole.USER, UserRole.ADMIN])
                )
                .values(role=UserRole.PERMISSION_REQUIRED)
            )
            action = "강등 (User/Admin -> Required)"

        result = await db.execute(stmt)
        count = result.rowcount
        
        if count > 0:
            logger.info(
                "부서 권한 동기화 완료: 그룹=%s(%s), 작업=%s, 영향받은 유저수=%d",
                group.name, group.code, action, count
            )
        
        return count


user_group_service = UserGroupService()
