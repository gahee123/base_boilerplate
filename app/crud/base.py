"""
app/crud/base.py
~~~~~~~~~~~~~~~~
Generic CRUD 기반 클래스.

반복되는 단순 CRUD 로직을 추상화하여, 모델별 CRUD 클래스를
몇 줄만으로 생성할 수 있습니다.

Usage:
    class CRUDUser(CRUDBase[User, UserCreate, UserUpdate]):
        pass

    crud_user = CRUDUser(User)
    user = await crud_user.get(db, id=user_id)
"""
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import BaseModel
from app.schemas.base import PaginatedResponse, PaginationMeta

ModelType = TypeVar("ModelType", bound=BaseModel)
CreateSchemaType = TypeVar("CreateSchemaType", bound=PydanticBaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=PydanticBaseModel)


class CRUDBase(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """제네릭 CRUD 기반 클래스.

    타입 파라미터:
        ModelType: SQLAlchemy 모델 (BaseModel 상속)
        CreateSchemaType: 생성용 Pydantic 스키마
        UpdateSchemaType: 수정용 Pydantic 스키마

    제공 메서드:
        get()          — ID로 단건 조회
        get_multi()    — 목록 조회 (skip/limit)
        get_paginated() — 페이지네이션 조회
        create()       — 생성
        update()       — 수정
        remove()       — Soft delete
    """

    def __init__(self, model: type[ModelType]) -> None:
        self.model = model

    async def get(self, db: AsyncSession, *, id: UUID) -> ModelType | None:
        """ID로 단건 조회합니다.

        Soft delete된 레코드(deleted_at IS NOT NULL)는 제외합니다.
        """
        stmt = select(self.model).where(
            self.model.id == id,
            self.model.deleted_at.is_(None),
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_multi(
        self,
        db: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 20,
    ) -> list[ModelType]:
        """목록 조회합니다 (offset/limit 방식).

        Soft delete된 레코드는 제외합니다.
        """
        stmt = (
            select(self.model)
            .where(self.model.deleted_at.is_(None))
            .offset(skip)
            .limit(limit)
            .order_by(self.model.created_at.desc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_paginated(
        self,
        db: AsyncSession,
        *,
        page: int = 1,
        size: int = 20,
    ) -> PaginatedResponse:
        """페이지네이션 조회합니다.

        Args:
            page: 페이지 번호 (1부터 시작)
            size: 페이지당 레코드 수

        Returns:
            PaginatedResponse: data(목록) + meta(페이지 정보)
        """
        # 전체 개수 조회
        count_stmt = (
            select(func.count())
            .select_from(self.model)
            .where(self.model.deleted_at.is_(None))
        )
        total_result = await db.execute(count_stmt)
        total = total_result.scalar_one()

        # 데이터 조회
        skip = (page - 1) * size
        items = await self.get_multi(db, skip=skip, limit=size)

        return PaginatedResponse(
            data=items,
            meta=PaginationMeta.create(total=total, page=page, size=size),
        )

    async def create(
        self,
        db: AsyncSession,
        *,
        obj_in: CreateSchemaType,
    ) -> ModelType:
        """새 레코드를 생성합니다.

        Pydantic 스키마의 필드를 모델 컬럼에 매핑하여 저장합니다.
        """
        obj_data = obj_in.model_dump()
        db_obj = self.model(**obj_data)
        db.add(db_obj)
        await db.flush()
        await db.refresh(db_obj)
        return db_obj

    async def update(
        self,
        db: AsyncSession,
        *,
        db_obj: ModelType,
        obj_in: UpdateSchemaType | dict[str, Any],
    ) -> ModelType:
        """기존 레코드를 수정합니다.

        obj_in에서 값이 설정된 필드만(exclude_unset=True) 업데이트합니다.
        """
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)

        db.add(db_obj)
        await db.flush()
        await db.refresh(db_obj)
        return db_obj

    async def remove(self, db: AsyncSession, *, id: UUID) -> ModelType | None:
        """Soft delete: deleted_at 타임스탬프를 기록합니다.

        물리 삭제가 아닌 논리 삭제를 수행합니다.
        이후 get()/get_multi()에서 자동으로 제외됩니다.
        """
        db_obj = await self.get(db, id=id)
        if db_obj is None:
            return None

        db_obj.deleted_at = datetime.now(UTC)  # type: ignore[assignment]
        db.add(db_obj)
        await db.flush()
        await db.refresh(db_obj)
        return db_obj
