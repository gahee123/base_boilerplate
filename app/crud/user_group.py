"""
app/crud/user_group.py
~~~~~~~~~~~~~~~~~~~~~~
UserGroup 모델에 대한 CRUD 연산 클래스.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.user import UserGroup
from app.schemas.user_group import UserGroupCreate, UserGroupUpdate


class CRUDUserGroup(CRUDBase[UserGroup, UserGroupCreate, UserGroupUpdate]):
    """부서(UserGroup) CRUD 클래스."""

    async def get_by_code(self, db: AsyncSession, *, code: str) -> UserGroup | None:
        """코드로 부서를 조회합니다."""
        stmt = select(self.model).where(self.model.code == code)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()


crud_user_group = CRUDUserGroup(UserGroup)
