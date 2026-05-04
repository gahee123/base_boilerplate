"""
tests/conftest.py
~~~~~~~~~~~~~~~~~
pytest 공유 fixture.

테스트용 DB 엔진, 세션, httpx 비동기 클라이언트,
그리고 사전 정의된 테스트용 사용자(일반/관리자)를 제공합니다.
"""
import asyncio
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.core.redis import close_redis, init_redis
from app.main import app
from app.models.base import Base
from app.models.user import User, UserRole


@pytest.fixture(autouse=True)
async def redis_setup():
    """각 테스트마다 Redis 커넥션을 초기화합니다."""
    await init_redis()
    yield
    await close_redis()

# ── 테스트 환경 설정 ──────────────────────────────────────────

# 테스트 전용 DB URL (기존 DB 이름 뒤에 _test 접미사 추가)
# 예: app_db -> app_db_test
_db_parts = settings.DATABASE_URL.split("/")
_db_name = _db_parts[-1]
TEST_DATABASE_URL = "/".join(_db_parts[:-1]) + f"/{_db_name}_test"


@pytest.fixture
async def engine():
    """테스트용 DB 엔진 (세션 스코프).
    
    테스트 시작 시 테이블을 생성하고, 종료 시 모두 삭제합니다.
    """
    # asyncpg는 DB가 없으면 자동 생성을 지원하지 않으므로,
    # 실제 환경에서는 테스트 DB가 미리 생성되어 있어야 합니다.
    test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield test_engine

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await test_engine.dispose()


@pytest.fixture
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    """테스트용 DB 세션 (각 테스트마다 독립된 트랜잭션).
    
    테스트가 끝나면 자동으로 롤백하여 DB 상태를 유지합니다.
    """
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session, session.begin():
        yield session
        # 명시적 롤백 (테스트 후 데이터 정리)
        await session.rollback()


@pytest.fixture
async def client(db_session) -> AsyncGenerator[AsyncClient, None]:
    """FastAPI 테스트를 위한 비동기 httpx 클라이언트.

    app의 get_db 의존성을 테스트용 db_session으로 교체(override)합니다.
    async generator 방식으로 override해야 FastAPI가 세션 라이프사이클을
    올바르게 관리합니다 (트랜잭션 충돌 방지).
    """
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ── 테스트용 데이터 Fixture ────────────────────────────────────

@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """사전 생성된 일반 사용자 fixture."""
    user = User(
        email="test@example.com",
        hashed_password=hash_password("Password123!"),
        full_name="테스트 유저",
        role=UserRole.USER,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def admin_user(db_session: AsyncSession) -> User:
    """사전 생성된 관리자 사용자 fixture."""
    user = User(
        email="admin@example.com",
        hashed_password=hash_password("AdminPass123!"),
        full_name="관리자 유저",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


# ── 헬스 유틸리티 ──

def get_auth_headers(user: User) -> dict[str, str]:
    """사용자의 인증 헤더(Bearer 토큰)를 생성합니다."""
    token = create_access_token(user_id=user.id, role=user.role.value)
    return {"Authorization": f"Bearer {token}"}
