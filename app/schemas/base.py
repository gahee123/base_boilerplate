"""
app/schemas/base.py
~~~~~~~~~~~~~~~~~~~
공통 Pydantic 스키마.

모든 응답 스키마의 기반 클래스와 페이지네이션 래퍼를 정의합니다.
Pydantic v2 패턴(ConfigDict)을 사용합니다.
"""
import math
from datetime import datetime, timezone
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class SuccessResponse(BaseModel, Generic[T]):
    """표준 성공 응답 래퍼"""
    success: bool = True
    data: T
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))


class BaseSchema(BaseModel):
    """모든 Pydantic 스키마의 기반 클래스.

    - from_attributes=True: SQLAlchemy 모델 → Pydantic 스키마 자동 변환 허용
    """

    model_config = ConfigDict(from_attributes=True)


class PaginationMeta(BaseModel):
    """페이지네이션 메타 정보.

    Attributes:
        total: 전체 레코드 수
        page: 현재 페이지 번호 (1부터 시작)
        size: 페이지당 레코드 수
        pages: 전체 페이지 수
    """

    total: int
    page: int
    size: int
    pages: int

    @classmethod
    def create(cls, *, total: int, page: int, size: int) -> "PaginationMeta":
        """total, page, size로부터 PaginationMeta를 계산하여 생성합니다."""
        pages = math.ceil(total / size) if size > 0 else 0
        return cls(total=total, page=page, size=size, pages=pages)


class PaginatedResponse(BaseModel, Generic[T]):
    """제네릭 페이지네이션 응답 래퍼.

    Usage:
        @router.get("/users", response_model=PaginatedResponse[UserResponse])
        async def list_users(...):
            return PaginatedResponse(
                data=users,
                meta=PaginationMeta.create(total=150, page=1, size=20),
            )
    """

    data: list[T]
    meta: PaginationMeta
