"""
app/models/base.py
~~~~~~~~~~~~~~~~~~
공통 DB 모델 기반 클래스.

모든 테이블이 상속하는 UUID PK, 타임스탬프, Soft Delete 필드를 정의합니다.
SQLAlchemy 2.0 Mapped 패턴을 사용합니다.
"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy DeclarativeBase.

    모든 모델 클래스의 최상위 기반. metadata와 registry를 관리합니다.
    Alembic에서 `Base.metadata`를 target_metadata로 사용합니다.
    """

    pass


class TimestampMixin:
    """생성/수정 시각 자동 관리 Mixin.

    - created_at: INSERT 시 자동 설정 (DB 서버 시각)
    - updated_at: INSERT 및 UPDATE 시 자동 갱신
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    """Soft Delete Mixin.

    - deleted_at: NULL이면 활성 레코드, 값이 있으면 삭제된 레코드.
    - 물리 삭제 대신 이 컬럼에 시각을 기록하여 데이터 복구 가능.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )


class BaseModel(Base, TimestampMixin, SoftDeleteMixin):
    """모든 테이블이 상속하는 추상 기반 모델.

    포함 필드:
    - id: UUID PK (auto-generated)
    - created_at: 생성 시각
    - updated_at: 수정 시각
    - deleted_at: Soft delete 시각

    Usage:
        class User(BaseModel):
            __tablename__ = "users"
            email: Mapped[str] = mapped_column(String(255), unique=True)
    """

    __abstract__ = True

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
