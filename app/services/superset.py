"""
app/services/superset.py
~~~~~~~~~~~~~~~~~~~~~~~~
Apache Superset REST API 연동 및 JIT(Just-In-Time) 유저 관리 서비스.
"""
import logging
from typing import Any, dict, Optional

import httpx

from app.core.config import settings
from app.utils.exceptions import InternalServerError

logger = logging.getLogger(__name__)


class SupersetService:
    """
    Apache Superset REST API와 통신하여 유저를 동기화하고 대시보드 권한을 관리합니다.
    """

    def __init__(self):
        self.base_url = settings.SUPERSET_BASE_URL.rstrip("/")
        self._admin_token: Optional[str] = None

    async def _get_admin_token(self) -> str:
        """관리자 계정으로 로그인하여 Access Token을 획득합니다."""
        url = f"{self.base_url}/api/v1/security/login"
        payload = {
            "username": settings.SUPERSET_ADMIN_USER,
            "password": settings.SUPERSET_ADMIN_PASSWORD,
            "provider": "db",
            "refresh": True,
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json=payload, timeout=10.0)
                response.raise_for_status()
                data = response.json()
                self._admin_token = data["access_token"]
                return self._admin_token
            except Exception as e:
                logger.error("Superset 관리자 로그인 실패: %s", str(e))
                raise InternalServerError(f"Superset 연동 오류: {str(e)}")

    async def _get_headers(self) -> dict[str, str]:
        """API 호출에 필요한 인증 헤더를 반환합니다."""
        token = await self._get_admin_token()
        return {"Authorization": f"Bearer {token}"}

    async def sync_user(self, username: str, first_name: str, last_name: str, email: str) -> bool:
        """
        Superset에 유저가 존재하는지 확인하고, 없으면 Alpha 역할로 자동 생성합니다 (JIT).
        """
        # 1. 유저 존재 확인 (Username 기반)
        # Superset API는 유저 검색 시 필터링을 지원합니다.
        url = f"{self.base_url}/api/v1/security/users/"
        headers = await self._get_headers()
        
        async with httpx.AsyncClient() as client:
            try:
                # 유저 목록 검색 (Username 필터)
                search_url = f"{url}?q=(filters:!((col:username,opr:eq,value:{username})))"
                response = await client.get(search_url, headers=headers)
                response.raise_for_status()
                data = response.json()
                
                if data["count"] > 0:
                    logger.info("Superset 유저 확인 완료: %s", username)
                    return True

                # 2. 유저 생성 (없을 경우)
                # Alpha 역할 ID를 찾아야 하지만, 보통 Alpha 역할은 고정되어 있으므로 Role Name으로 시도합니다.
                # 참고: API를 통한 유저 생성 시 Role ID 리스트가 필요할 수 있습니다.
                role_url = f"{self.base_url}/api/v1/security/roles/?q=(filters:!((col:name,opr:eq,value:{settings.SUPERSET_USER_ROLE})))"
                role_resp = await client.get(role_url, headers=headers)
                role_data = role_resp.json()
                
                if role_data["count"] == 0:
                    logger.error("Superset에 '%s' 역할이 존재하지 않습니다.", settings.SUPERSET_USER_ROLE)
                    return False
                
                alpha_role_id = role_data["result"][0]["id"]

                create_payload = {
                    "active": True,
                    "first_name": first_name,
                    "last_name": last_name,
                    "username": username,
                    "email": email,
                    "roles": [alpha_role_id],
                    "password": "TemporaryPassword123!", # SSO 연동 시 실제로는 쓰이지 않음
                }
                
                create_resp = await client.post(url, json=create_payload, headers=headers)
                create_resp.raise_for_status()
                logger.info("Superset 신규 유저 생성 성공: %s (Role: %s)", username, settings.SUPERSET_USER_ROLE)
                return True
                
            except Exception as e:
                logger.error("Superset 유저 동기화 실패 (%s): %s", username, str(e))
                return False

    async def clone_dashboard(self, dashboard_id: int, new_title: str, owner_id: int) -> Optional[int]:
        """
        기존 대시보드를 복제하여 새로운 유저 전용 대시보드를 만듭니다.
        """
        # 주의: Superset 공식 API에는 'Copy' 엔드포인트가 특정 버전에만 있을 수 있습니다.
        # 일반적으로는 GET으로 스키마를 가져와서 POST로 다시 쏘는 방식을 사용합니다.
        url = f"{self.base_url}/api/v1/dashboard/{dashboard_id}"
        headers = await self._get_headers()
        
        async with httpx.AsyncClient() as client:
            try:
                # 1. 원본 대시보드 데이터 가져오기
                get_resp = await client.get(url, headers=headers)
                get_resp.raise_for_status()
                source_data = get_resp.json()["result"]
                
                # 2. 필수 필드만 추출하여 신규 생성 페이로드 구성
                new_payload = {
                    "dashboard_title": new_title,
                    "slug": f"custom-{owner_id}-{dashboard_id}",
                    "owners": [owner_id],
                    "position_json": source_data.get("position_json"),
                    "css": source_data.get("css"),
                    "json_metadata": source_data.get("json_metadata"),
                    "published": True
                }
                
                create_resp = await client.post(f"{self.base_url}/api/v1/dashboard/", json=new_payload, headers=headers)
                create_resp.raise_for_status()
                new_db_id = create_resp.json()["id"]
                logger.info("Superset 대시보드 복제 성공: %s -> %s", dashboard_id, new_db_id)
                return int(new_db_id)
                
            except Exception as e:
                logger.error("Superset 대시보드 복제 실패: %s", str(e))
                return None


superset_service = SupersetService()
