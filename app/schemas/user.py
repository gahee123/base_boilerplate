"""
app/schemas/user.py
~~~~~~~~~~~~~~~~~~~
사용자 및 부서 관련 Pydantic 스키마.
요청과 응답 스키마를 정의합니다.
"""
from datetime import datetime
from uuid import UUID

from pydantic import ConfigDict, EmailStr, Field

from app.models.user import UserRole
from app.schemas.base import BaseSchema


class UserSyncCreate(BaseSchema):
    """SSO 로그인 시 사용자 정보 Upsert 스키마"""
    email: EmailStr
    employee_id: str
    full_name: str | None = None
    department: str | None = None
    site_code: str | None = None


class UserAdminUpdate(BaseSchema):
    """관리자용 역할 및 상태 업데이트 스키마"""
    role: UserRole | None = Field(None, description="사용자 역할(5단계)")
    is_active: bool | None = Field(None, description="계정 활성 여부")


class UserRejectRequest(BaseSchema):
    """사용자 승인 거절 요청 스키마"""
    reason: str = Field(..., min_length=2, max_length=200, description="거절 사유")


class UserResponse(BaseSchema):
    """클라이언트 전송용 사용자 정보 응답 스키마"""
    id: UUID
    email: EmailStr
    employee_id: str
    full_name: str | None = None
    department: str | None = None
    site_code: str | None = None
    role: UserRole
    is_active: bool
    last_login_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
