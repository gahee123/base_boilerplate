"""
app/models/user_dashboard.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
유저별 개인화 대시보드 매핑 모델.
"""
from sqlalchemy import ForeignKey, Integer, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.audit_log import AuditableMixin


class UserDashboard(Base, AuditableMixin):
    """
    유저가 커스텀한 Superset 대시보드 정보를 저장합니다.
    """
    __tablename__ = "user_dashboards"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    superset_dashboard_id: Mapped[int] = mapped_column(Integer, nullable=False)
    is_customized: Mapped[bool] = mapped_column(Boolean, default=False)
    dashboard_title: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # AuditableMixin 설정을 통해 변경 이력 추적
    __audit_exclude__ = {"created_at", "updated_at"}
