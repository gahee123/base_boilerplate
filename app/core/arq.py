"""
app/core/arq.py
~~~~~~~~~~~~~~~
Arq (Redis 기반 분산 작업 큐) 클라이언트.

애플리케이션에서 백그라운드 작업을 예약할 때 사용합니다.
"""
# RedisSettings 파싱
from urllib.parse import urlparse

from arq.connections import RedisSettings, create_pool

from app.core.config import settings

_url = urlparse(settings.REDIS_URL)

arq_redis_settings = RedisSettings(
    host=_url.hostname or "localhost",
    port=_url.port or 6379,
    database=int(_url.path[1:]) if _url.path else 0,
    password=_url.password
)

_arq_pool = None

async def get_arq_pool():
    """Arq 커넥션 풀을 반환합니다 (싱글톤)."""
    global _arq_pool
    if _arq_pool is None:
        _arq_pool = await create_pool(arq_redis_settings)
    return _arq_pool

async def enqueue_job(function_name: str, *args, **kwargs):
    """작업을 큐에 추가합니다."""
    pool = await get_arq_pool()
    return await pool.enqueue_job(function_name, *args, **kwargs)
