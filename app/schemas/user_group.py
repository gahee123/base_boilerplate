"""
app/schemas/user_group.py
~~~~~~~~~~~~~~~~~~~~~~~~~
부서(UserGroup) 관련 Pydantic 스키마.
요청과 응답 스키마를 정의합니다.
"""
from datetime import datetime
from uuid import UUID

from pydantic import ConfigDict, Field

from app.schemas.base import BaseSchema


class UserGroupCreate(BaseSchema):
    """신규 부서 생성 스키마"""
    code: str = Field(..., min_length=1, max_length=100, description="부서 코드 (HMG SSO departmentCode)")
    name: str = Field(..., min_length=1, max_length=100, description="부서 명칭")
    whitelisted: bool = Field(False, description="화이트리스트 등록 여부")


class UserGroupUpdate(BaseSchema):
    """부서 정보 수정 스키마"""
    name: str | None = Field(None, min_length=1, max_length=100, description="부서 명칭")
    whitelisted: bool | None = Field(None, description="화이트리스트 등록 여부")


class UserGroupResponse(BaseSchema):
    """부서 정보 응답 스키마"""
    id: UUID
    code: str
    name: str
    whitelisted: bool
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
