"""
app/api/v1/endpoints/user_groups.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
부서(UserGroup) 관리 관리자 API.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import requires_role
from app.models.user import User, UserRole
from app.schemas.base import PaginatedResponse
from app.schemas.user import UserResponse
from app.schemas.user_group import UserGroupCreate, UserGroupResponse, UserGroupUpdate
from app.services.user_group import user_group_service

router = APIRouter(prefix="/user-groups", tags=["Admin: User Groups"])


@router.get(
    "/",
    response_model=PaginatedResponse[UserGroupResponse],
    summary="부서 목록 조회",
    description="시스템에 등록된 전체 부서 목록을 페이지네이션으로 조회합니다. (Admin 전용)",
)
async def list_groups(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(requires_role(UserRole.ADMIN)),
) -> PaginatedResponse[UserGroupResponse]:
    """부서 목록 조회 (Admin 전용)."""
    return await user_group_service.list_groups(db, page=page, size=size)


@router.get(
    "/{group_id}/users",
    response_model=PaginatedResponse[UserResponse],
    summary="부서 내 사용자 목록 조회",
    description="특정 부서(UserGroup)에 속한 사용자 목록을 조회합니다. (Admin 전용)",
)
async def list_group_users(
    group_id: UUID,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(requires_role(UserRole.ADMIN)),
) -> PaginatedResponse[UserResponse]:
    """부서 내 사용자 목록 조회 (Admin 전용)."""
    return await user_group_service.list_group_users(
        db, group_id=group_id, page=page, size=size
    )


@router.post(
    "/",
    response_model=UserGroupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="신규 부서 등록",
    description="새로운 부서를 등록하고 화이트리스트 여부를 설정합니다. (Admin 전용)",
)
async def create_group(
    obj_in: UserGroupCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(requires_role(UserRole.ADMIN)),
) -> UserGroupResponse:
    """신규 부서 등록 (Admin 전용)."""
    group = await user_group_service.create_group(db, obj_in=obj_in)
    return UserGroupResponse.model_validate(group)


@router.patch(
    "/{group_id}",
    response_model=UserGroupResponse,
    summary="부서 정보 수정",
    description="부서 명칭이나 화이트리스트 상태를 수정합니다. 상태 변경 시 소속 유저 권한이 동기화됩니다. (Admin 전용)",
)
async def update_group(
    group_id: UUID,
    obj_in: UserGroupUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(requires_role(UserRole.ADMIN)),
) -> UserGroupResponse:
    """부서 정보 수정 (Admin 전용)."""
    group = await user_group_service.update_group(db, group_id=group_id, obj_in=obj_in)
    return UserGroupResponse.model_validate(group)


@router.delete(
    "/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="부서 삭제",
    description="부서를 Soft Delete합니다. (Admin 전용)",
)
async def delete_group(
    group_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(requires_role(UserRole.ADMIN)),
) -> None:
    """부서 삭제 (Admin 전용)."""
    await user_group_service.delete_group(db, group_id=group_id)
