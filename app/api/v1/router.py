"""
app/api/v1/router.py
~~~~~~~~~~~~~~~~~~~~
API v1 라우터 통합.

모든 v1 엔드포인트를 하나의 라우터로 묶어
main.py에서 한 번에 등록합니다.
"""
from fastapi import APIRouter

from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.notifications import router as notifications_router
from app.api.v1.endpoints.superset import router as superset_router
from app.api.v1.endpoints.user_groups import router as user_groups_router
from app.api.v1.endpoints.users import router as users_router

api_v1_router = APIRouter()

api_v1_router.include_router(auth_router)
api_v1_router.include_router(users_router)
api_v1_router.include_router(user_groups_router)
api_v1_router.include_router(notifications_router)
api_v1_router.include_router(superset_router)
