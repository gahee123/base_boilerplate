"""
app/api/v1/endpoints/superset.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Superset 대시보드 연동 및 개인화 관리 API.
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_active_user
from app.models.user import User
from app.models.user_dashboard import UserDashboard
from app.services.superset import superset_service
from app.utils.exceptions import BadRequest, NotFound

router = APIRouter(prefix="/superset", tags=["Superset Integration"])


@router.get("/dashboard", summary="사용자별 대시보드 ID 조회")
async def get_dashboard(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    현재 사용자가 볼 수 있는 가장 최신의 대시보드 ID를 반환합니다.
    개인화된 대시보드가 있으면 그것을, 없으면 기본 마스터 대시보드를 반환합니다.
    """
    stmt = select(UserDashboard).where(UserDashboard.user_id == str(current_user.id))
    result = await db.execute(stmt)
    user_dash = result.scalar_one_or_none()

    if user_dash:
        return {
            "dashboard_id": user_dash.superset_dashboard_id,
            "is_customized": user_dash.is_customized,
            "title": user_dash.dashboard_title,
        }

    # 개인화된 대시보드가 없는 경우 기본값 반환
    return {
        "dashboard_id": settings.SUPERSET_DEFAULT_DASHBOARD_ID,
        "is_customized": False,
        "title": "Master Template Dashboard",
    }


@router.post("/dashboard/customize", status_code=status.HTTP_201_CREATED, summary="개인 대시보드 생성 (복제)")
async def customize_dashboard(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    기본 마스터 대시보드를 복제하여 해당 사용자의 개인 전용 대시보드를 생성합니다.
    """
    # 이미 개인 대시보드가 있는지 확인
    stmt = select(UserDashboard).where(UserDashboard.user_id == str(current_user.id))
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise BadRequest("이미 개인화된 대시보드를 보유하고 있습니다.")

    # 1. Superset API를 통해 대시보드 복제
    # 주의: Superset 내에서 소유자(Owner)를 지정하려면 해당 유저의 Superset 내부 ID를 알아야 합니다.
    # 여기서는 단순화를 위해 사번 기반 검색을 사용하거나, 수동 매핑 로직이 필요할 수 있습니다.
    new_title = f"{current_user.full_name or current_user.employee_id}의 대시보드"
    
    # 2. 복제 실행 (실제로는 Superset API 응답에 따라 처리)
    # owner_id는 Superset 내부 유저 ID이므로, 실제 연동 시에는 sync_user에서 받아온 ID를 사용해야 함.
    # 일단은 관리자 소유로 생성하고 나중에 변경하는 등의 로직 가능.
    new_dash_id = await superset_service.clone_dashboard(
        dashboard_id=settings.SUPERSET_DEFAULT_DASHBOARD_ID,
        new_title=new_title,
        owner_id=1 # 임시: 실제 구현시에는 유저의 Superset ID 조회 필요
    )

    if not new_dash_id:
        raise BadRequest("Superset 대시보드 복제 중 오류가 발생했습니다.")

    # 3. 우리 DB에 매핑 정보 저장
    user_dash = UserDashboard(
        user_id=str(current_user.id),
        superset_dashboard_id=new_dash_id,
        is_customized=True,
        dashboard_title=new_title
    )
    db.add(user_dash)
    await db.commit()

    return {
        "dashboard_id": new_dash_id,
        "title": new_title
    }
