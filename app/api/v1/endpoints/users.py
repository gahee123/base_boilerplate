"""
app/api/v1/endpoints/users.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
사용자 관리 엔드포인트.
일반 사용자 프로필, 관리자용 유저 관리, 그리고 슈퍼 어드민용 권한 관리 API를 제공합니다.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_active_user, requires_role
from app.models.user import User, UserRole
from app.schemas.base import PaginatedResponse
from app.schemas.user import UserAdminUpdate, UserRejectRequest, UserResponse
from app.services.user import user_service

router = APIRouter(prefix="/users")


# ── [Tag: Users] 일반 사용자 (내 프로필) ───────────────────────────
@router.get(
    "/me",
    response_model=UserResponse,
    tags=["Users"],
    summary="내 프로필 조회",
    description="현재 로그인한 사용자의 프로필 정보를 반환합니다.",
)
async def get_me(
    current_user: User = Depends(get_current_active_user),
) -> UserResponse:
    return await user_service.get_me(current_user=current_user)


@router.post(
    "/me/request-permission",
    response_model=UserResponse,
    tags=["Users"],
    summary="사용 권한 신청",
    description="최초 로그인 후 '승인 대기(PERMISSION_REQUIRED)' 상태인 사용자가 시스템 이용 권한을 요청합니다.",
)
async def request_permission(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> UserResponse:
    user = await user_service.request_permission(db, current_user=current_user)
    return UserResponse.model_validate(user)


# ── [Tag: Admin: Users] 관리자용 사용자 관리 ───────────────────────
@router.get(
    "/",
    response_model=PaginatedResponse[UserResponse],
    tags=["Admin: Users"],
    summary="전체 사용자 목록 조회",
    description="시스템의 전체 사용자 목록을 조회합니다. (Admin 전용)",
)
async def list_users(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(requires_role(UserRole.ADMIN)),
) -> PaginatedResponse[UserResponse]:
    return await user_service.list_users(db, page=page, size=size)


@router.get(
    "/pending",
    response_model=list[UserResponse],
    tags=["Admin: Users"],
    summary="승인 대기자 목록 조회",
    description="권한 신청을 완료하여 승인 대기(PERMISSION_REQUESTED) 상태인 사용자 목록을 조회합니다. (Admin 전용)",
)
async def list_pending_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(requires_role(UserRole.ADMIN)),
) -> list[UserResponse]:
    users = await user_service.list_pending_users(db)
    return [UserResponse.model_validate(u) for u in users]


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    tags=["Admin: Users"],
    summary="특정 사용자 상세 조회",
)
async def get_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(requires_role(UserRole.ADMIN)),
) -> UserResponse:
    return await user_service.get_user(db, user_id=user_id)


@router.post(
    "/{user_id}/approve",
    response_model=UserResponse,
    tags=["Admin: Users"],
    summary="사용자 승인",
)
async def approve_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(requires_role(UserRole.ADMIN)),
) -> UserResponse:
    return await user_service.approve_user(db, user_id=user_id)


@router.post(
    "/{user_id}/reject",
    response_model=UserResponse,
    tags=["Admin: Users"],
    summary="사용자 거절",
)
async def reject_user(
    user_id: UUID,
    reject_in: UserRejectRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(requires_role(UserRole.ADMIN)),
) -> UserResponse:
    return await user_service.reject_user(db, user_id=user_id, reject_in=reject_in)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Admin: Users"],
    summary="사용자 삭제 (Soft Delete)",
)
async def delete_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(requires_role(UserRole.ADMIN)),
) -> None:
    await user_service.delete_user(db, user_id=user_id)


# ── [Tag: Admin: Permissions] 슈퍼 어드민용 권한 관리 ───────────────
@router.get(
    "/admins/list",
    response_model=list[UserResponse],
    tags=["Admin: Permissions"],
    summary="관리자 목록 조회",
    description="시스템 관리자(Admin, SuperAdmin) 명단만 조회합니다. (Admin 전용)",
)
async def list_admins(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(requires_role(UserRole.ADMIN)),
) -> list[UserResponse]:
    users = await user_service.list_admins(db)
    return [UserResponse.model_validate(u) for u in users]


@router.patch(
    "/{user_id}/role",
    response_model=UserResponse,
    tags=["Admin: Permissions"],
    summary="사용자 권한/상태 수정",
    description="사용자의 역할을 변경하거나 계정을 활성/비활성화합니다. 관리자 권한 부여는 SuperAdmin만 가능합니다.",
)
async def update_user_role(
    user_id: UUID,
    user_in: UserAdminUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(requires_role(UserRole.ADMIN)),
) -> UserResponse:
    user = await user_service.update_user(
        db, user_id=user_id, user_in=user_in, current_user=current_user
    )
    return UserResponse.model_validate(user)
