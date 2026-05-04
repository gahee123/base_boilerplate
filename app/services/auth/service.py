import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security.jwt import create_access_token, create_refresh_token
from app.models.user import User, UserGroup, UserRole
from app.services.auth.oidc.base import OIDCUserInfo
from app.utils.exceptions import Forbidden

logger = logging.getLogger(__name__)


class AuthService:
    """인가 기반 유저 동기화 및 토큰 발급 비즈니스 로직."""

    async def sso_sync_user(
        self, db: AsyncSession, user_info: OIDCUserInfo
    ) -> User:
        """SSO 로그인 수신 정보를 바탕으로 유저를 검색하거나 신규 생성합니다."""
        stmt = select(User).where(User.employee_id == user_info["employee_id"])
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        department = user_info.get("department", "")
        department_code = user_info.get("department_code", "")
        target_role = UserRole.PERMISSION_REQUIRED
        
        group_key = department_code or department
        if group_key:
            group_stmt = select(UserGroup).where(UserGroup.code == group_key)
            group_result = await db.execute(group_stmt)
            dept_group = group_result.scalar_one_or_none()
            if dept_group and dept_group.whitelisted:
                target_role = UserRole.USER

        if not user:
            user = User(
                email=user_info["email"],
                employee_id=user_info["employee_id"],
                full_name=user_info.get("full_name", ""),
                department=department,
                department_code=department_code,
                site=user_info.get("site", ""),
                role=target_role,
                is_active=True,
                last_login_at=datetime.now(UTC),
            )
            db.add(user)
            logger.info("신규 HMG SSO 유저 자동 가입: %s (부서: %s)", user.employee_id, department)
        else:
            user.full_name = user_info.get("full_name", "")
            user.department = department
            user.department_code = department_code
            user.site = user_info.get("site", "")

            if user.role == UserRole.PERMISSION_REQUIRED and target_role == UserRole.USER:
                user.role = target_role
                
            user.last_login_at = datetime.now(UTC)
            logger.info("기존 HMG SSO 유저 로그인: %s", user.employee_id)
        
        await db.flush()
        if not user.is_active:
            raise Forbidden("계정이 시스템 정책에 의해 비활성화된 상태입니다.")
            
        return user

    async def generate_auth_code(self, redis: object, user_id: UUID) -> str:
        """FE 리다이렉트용 단기 임시 코드를 생성합니다."""
        code = str(uuid4())
        if redis:
            await redis.set(f"auth_code:{code}", str(user_id), ex=settings.AUTH_CODE_EXPIRE_SECONDS)
        return code

    async def exchange_auth_code(self, redis: object, code: str) -> UUID | None:
        """임시 코드를 유저 ID로 교환하고 코드를 삭제합니다."""
        if not redis:
            return None
        
        user_id_str = await redis.get(f"auth_code:{code}")
        if user_id_str:
            await redis.delete(f"auth_code:{code}")
            return UUID(user_id_str.decode() if isinstance(user_id_str, bytes) else user_id_str)
        return None

    def create_tokens(self, user: User) -> dict[str, str]:
        """Access Token과 Refresh Token 쌍을 생성합니다."""
        access_token = create_access_token(user.id, user.role.value)
        refresh_token = create_refresh_token(user.id)
        return {
            "access_token": access_token,
            "refresh_token": refresh_token
        }

    async def activate_session(self, redis: object, user_id: str) -> None:
        """로그인 성공 시 Redis에 활동 세션 키를 생성합니다."""
        if redis is None:
            return
        ttl = settings.SESSION_IDLE_TIMEOUT_MINUTES * 60
        await redis.set(f"session:{user_id}", "1", ex=ttl)

    async def touch_session(self, redis: object, user_id: str) -> bool:
        """API 요청 시 세션 TTL을 리셋합니다."""
        if redis is None:
            return True
        session_key = f"session:{user_id}"
        exists = await redis.exists(session_key)
        if not exists:
            return False
        ttl = settings.SESSION_IDLE_TIMEOUT_MINUTES * 60
        await redis.expire(session_key, ttl)
        return True

    async def logout(
        self, redis: object | None, token_jti: str, token_exp: datetime, user_id: str = ""
    ) -> None:
        """강제 로그아웃 처리."""
        if redis is None:
            return
        now = datetime.now(UTC)
        ttl = int((token_exp - now).total_seconds())
        if ttl > 0:
            await redis.set(f"bl:{token_jti}", "1", ex=ttl)
        if user_id:
            await redis.delete(f"session:{user_id}")


auth_service = AuthService()
