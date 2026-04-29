"""
app/core/database.py
~~~~~~~~~~~~~~~~~~~~
비동기 데이터베이스 엔진 및 세션 팩토리.

SQLAlchemy 2.0 async 패턴 기반.
PostgreSQL + asyncpg 드라이버를 사용합니다.
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# ── 비동기 엔진 ─────────────────────────────────────────────
# pool_pre_ping: 커넥션 풀에서 꺼낸 커넥션의 유효성을 미리 검사 (끊긴 커넥션 방지)
# echo: True면 실행되는 SQL을 로그로 출력 (디버그용)
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.is_debug,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# ── 세션 팩토리 ─────────────────────────────────────────────
# expire_on_commit=False: 커밋 후에도 객체 속성 접근 가능 (비동기 환경 필수)
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 의존성: 요청별 DB 세션을 생성하고 관리합니다.

    - 정상 완료 시 자동 커밋
    - 예외 발생 시 자동 롤백
    - 종료 시 세션 반환 (커넥션 풀로 복귀)

    Usage:
        @router.get("/users")
        async def get_users(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
