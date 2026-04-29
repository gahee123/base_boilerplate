"""
app/crud/user.py
~~~~~~~~~~~~~~~~
사용자 CRUD.

CRUDBase를 상속하여 기본 CRUD 기능을 활용하고,
이메일 조회 등 User 전용 메서드를 추가합니다.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.user import User
from app.schemas.user import UserSyncCreate, UserAdminUpdate


class CRUDUser(CRUDBase[User, UserSyncCreate, UserAdminUpdate]):
    """사용자 CRUD 클래스.

    상속으로 포함되는 메서드:
        get, get_multi, get_paginated, create, update, remove

    추가 메서드:
        get_by_email: 이메일로 사용자 조회
    """

    async def get_by_email(
        self,
        db: AsyncSession,
        *,
        email: str,
    ) -> User | None:
        """이메일로 사용자를 조회합니다.

        Soft delete된 사용자는 제외합니다.
        로그인, 회원가입 중복 체크 등에 사용됩니다.
        """
        stmt = select(User).where(
            User.email == email,
            User.deleted_at.is_(None),
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_multi_by_roles(
        self,
        db: AsyncSession,
        *,
        roles: list[str],
    ) -> list[User]:
        """특정 역할(Role)들에 해당하는 사용자 목록을 조회합니다."""
        stmt = select(User).where(
            User.role.in_(roles),
            User.deleted_at.is_(None),
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())


    async def get_paginated_by_dept(
        self,
        db: AsyncSession,
        *,
        dept_code: str,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[User], int]:
        """특정 부서 코드에 속한 사용자 목록을 페이지네이션하여 조회합니다."""
        skip = (page - 1) * size
        stmt = select(User).where(
            User.department_code == dept_code,
            User.deleted_at.is_(None),
        )

        # 전체 개수 조회
        from sqlalchemy import func
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        # 데이터 조회
        result = await db.execute(stmt.offset(skip).limit(size))
        return list(result.scalars().all()), total


# ── 싱글톤 인스턴스 ──────────────────────────────────────────
crud_user = CRUDUser(User)
