"""
app/models/user.py
~~~~~~~~~~~~~~~~~~
사용자 모델 및 부서(UserGroup) 모델, 역할 Enum.
"""
import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SQLAlchemyEnum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.audit import AuditableMixin
from app.models.base import BaseModel
from app.models.enums import UserRole


class UserGroup(BaseModel):
    """부서 정보(화이트리스트 통제용) 모델"""
    __tablename__ = "user_groups"

    code: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    whitelisted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class User(BaseModel, AuditableMixin):
    """HMG SSO 동기화 사용자 모델"""
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    employee_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 부서 명칭
    department_code: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True) # 부서 코드
    site_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    
    role: Mapped[UserRole] = mapped_column(
        SQLAlchemyEnum(UserRole, name="user_role", native_enum=False),
        default=UserRole.PERMISSION_REQUIRED,
        server_default="permission_required",
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true", nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
