"""
app/core/redis.py
~~~~~~~~~~~~~~~~~
Redis 비동기 커넥션 풀.

redis.asyncio 패키지 사용 (aioredis는 deprecated).
앱 시작 시 init_redis(), 종료 시 close_redis()를 호출합니다.
"""
import logging

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── 전역 커넥션 풀 ───────────────────────────────────────────
_redis_pool: aioredis.Redis | None = None


async def init_redis() -> None:
    """Redis 커넥션 풀을 초기화합니다.

    FastAPI lifespan의 startup 단계에서 호출됩니다.
    """
    global _redis_pool
    try:
        _redis_pool = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=20,
        )
        # 연결 테스트
        await _redis_pool.ping()
        logger.info("Redis 연결 성공: %s", settings.REDIS_URL)
    except Exception:
        logger.warning("Redis 연결 실패: %s — 캐싱/Rate Limit 비활성화", settings.REDIS_URL)
        _redis_pool = None


async def close_redis() -> None:
    """Redis 커넥션 풀을 정리합니다.

    FastAPI lifespan의 shutdown 단계에서 호출됩니다.
    """
    global _redis_pool
    if _redis_pool is not None:
        try:
            # aioredis 5.0+ 에서는 aclose() 권장
            if hasattr(_redis_pool, "aclose"):
                await _redis_pool.aclose()
            else:
                await _redis_pool.close()
            logger.info("Redis 연결 종료")
        except RuntimeError:
            # 테스트 종료 시 루프가 이미 닫힌 경우 무시
            pass
        finally:
            _redis_pool = None


async def get_redis() -> aioredis.Redis | None:
    """FastAPI 의존성: Redis 클라이언트를 반환합니다.

    Redis가 연결되지 않은 경우 None을 반환합니다 (graceful fallback).

    Usage:
        @router.get("/items")
        async def get_items(redis: Redis | None = Depends(get_redis)):
            if redis:
                cached = await redis.get("key")
            ...
    """
    return _redis_pool
