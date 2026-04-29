import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token
from app.models.user import User, UserGroup, UserRole
from app.services.oidc.base import OIDCUserInfo
from app.services.superset import superset_service
from app.utils.exceptions import Forbidden

logger = logging.getLogger(__name__)


class AuthService:
    """인가 기반 유저 동기화 및 토큰 발급 비즈니스 로직."""

    async def sso_sync_user(
        self, db: AsyncSession, user_info: OIDCUserInfo
    ) -> User:
        """
        SSO 로그인 수신 정보를 바탕으로 유저를 검색하거나 신규 생성합니다.
        부서(department) 코드를 UserGroup 테이블에서 확인하여 화이트리스트면 즉시 USER 권한 부여, 아니면 대기.
        """
        stmt = select(User).where(User.employee_id == user_info["employee_id"])
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        department = user_info.get("department", "")
        department_code = user_info.get("department_code", "")
        target_role = UserRole.PERMISSION_REQUIRED
        
        # departmentCode 기준으로 UserGroup 조회
        group_key = department_code or department
        if group_key:
            group_stmt = select(UserGroup).where(UserGroup.code == group_key)
            group_result = await db.execute(group_stmt)
            dept_group = group_result.scalar_one_or_none()
            if dept_group and dept_group.whitelisted:
                target_role = UserRole.USER

        if not user:
            # Create
            user = User(
                email=user_info["email"],
                employee_id=user_info["employee_id"],
                full_name=user_info.get("full_name", ""),
                department=department,
                department_code=department_code,
                site_code=user_info.get("site_code", ""),
                role=target_role,
                is_active=True,
                last_login_at=datetime.now(UTC),
            )
            db.add(user)
            logger.info("신규 HMG SSO 유저 자동 가입: %s (부서: %s, 코드: %s)", user.employee_id, department, department_code)
        else:
            # Update (동기화)
            user.full_name = user_info.get("full_name", "")
            user.department = department
            user.department_code = department_code
            user.site_code = user_info.get("site_code", "")

            # 운영자 등 상위 권한을 지닌 경우 강등 방지 처리
            if user.role == UserRole.PERMISSION_REQUIRED and target_role == UserRole.USER:
                user.role = target_role
                
            user.last_login_at = datetime.now(UTC)
            logger.info("기존 HMG SSO 유저 로그인: %s", user.employee_id)
        
        await db.flush()
        await db.refresh(user)

        # ── Superset JIT Provisioning ──
        # 유저가 생성되거나 업데이트된 후 Superset에도 계정을 동기화합니다.
        # 실패하더라도 메인 서비스 로그인에는 지장이 없도록 예외 처리를 내부에서 소화합니다.
        await superset_service.sync_user(
            username=user.employee_id,
            first_name=user.full_name or "User",
            last_name=user.employee_id,
            email=user.email
        )

        if not user.is_active:
            raise Forbidden("계정이 시스템 정책에 의해 비활성화된 상태입니다.")
            
        return user

    def create_session_token(self, user: User) -> str:
        """HttpOnly 쿠키 및 API 통신용 Access Token 단일 발급."""
        return create_access_token(user.id, user.role.value)

    async def activate_session(self, redis: object, user_id: str) -> None:
        """
        로그인 성공 시 Redis에 활동 세션 키를 생성합니다.
        Sliding Window 비활동 만료의 기준점입니다.

        키 구조: session:{user_id} = "1", TTL = SESSION_IDLE_TIMEOUT_MINUTES
        """
        if redis is None:
            logger.warning("Redis 미연결: 비활동 세션 관리 비활성")
            return

        ttl = settings.SESSION_IDLE_TIMEOUT_MINUTES * 60
        await redis.set(f"session:{user_id}", "1", ex=ttl)  # type: ignore
        logger.info("세션 활성화: user_id=%s (TTL: %d분)", user_id, settings.SESSION_IDLE_TIMEOUT_MINUTES)

    async def touch_session(self, redis: object, user_id: str) -> bool:
        """
        API 요청 시 세션 TTL을 리셋합니다 (Sliding Window).

        Returns:
            True: 세션 유효 (TTL 리셋됨)
            False: 세션 만료 (비활동 시간 초과)
        """
        if redis is None:
            # Redis 없으면 비활동 만료 비활성 — JWT exp만 적용
            return True

        session_key = f"session:{user_id}"
        exists = await redis.exists(session_key)  # type: ignore
        if not exists:
            return False

        # TTL 리셋 (Sliding Window)
        ttl = settings.SESSION_IDLE_TIMEOUT_MINUTES * 60
        await redis.expire(session_key, ttl)  # type: ignore
        return True

    async def logout(
        self, redis: object | None, token_jti: str, token_exp: datetime, user_id: str = ""
    ) -> None:
        """
        강제 로그아웃 처리.
        1) Access Token의 jti를 Redis 블랙리스트에 등록
        2) 활동 세션 키를 삭제
        """
        if redis is None:
            logger.warning("Redis 미연결: 백엔드 블랙리스트 등재 생략")
            return

        # 블랙리스트 등재
        now = datetime.now(UTC)
        ttl = int((token_exp - now).total_seconds())
        if ttl > 0:
            await redis.set(f"bl:{token_jti}", "1", ex=ttl)  # type: ignore
            logger.info("SSO 중앙 로그아웃: 세션 JTI=%s (잔여 TTL: %d초)", token_jti, ttl)

        # 활동 세션 키 삭제
        if user_id:
            await redis.delete(f"session:{user_id}")  # type: ignore
            logger.info("활동 세션 삭제: user_id=%s", user_id)


auth_service = AuthService()
