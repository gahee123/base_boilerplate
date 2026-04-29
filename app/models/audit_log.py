"""
app/models/audit_log.py
~~~~~~~~~~~~~~~~~~~~~~~
데이터 변경 이력을 저장하는 시스템 테이블.

특정 테이블의 데이터가 변경될 때마다 old_data와 new_data를
JSON 형태로 저장하여 추적할 수 있도록 지원합니다.
"""
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class AuditLog(BaseModel):
    """
    모든 데이터 변경 이력(Insert/Update/Delete)을 저장하는 모델.
    사용자(sub) ID가 존재하는 경우 user_id에 연결할 수도 있습니다.
    """
    __tablename__ = "audit_logs"

    target_table: Mapped[str] = mapped_column(String(100), nullable=False)
    target_id: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # INSERT, UPDATE, DELETE

    old_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    new_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    user_id: Mapped[UUID | None] = mapped_column(nullable=True)
