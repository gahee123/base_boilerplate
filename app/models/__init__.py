"""
app/models/__init__.py
~~~~~~~~~~~~~~~~~~~~~~
SQLAlchemy 모델 패키지.

Alembic이 모든 모델의 metadata를 감지하려면
여기서 모든 모델을 import해야 합니다.
"""
from app.models.audit_log import AuditLog
from app.models.base import Base, BaseModel
from app.models.enums import HmgLoginType, HmgSiteCode, UserRole
from app.models.user import User, UserGroup
from app.models.user_dashboard import UserDashboard

__all__ = [
    "Base",
    "BaseModel",
    "User",
    "UserGroup",
    "UserDashboard",
    "UserRole",
    "AuditLog",
    "HmgSiteCode",
    "HmgLoginType",
]
