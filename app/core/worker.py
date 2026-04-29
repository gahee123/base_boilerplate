"""
app/core/worker.py
~~~~~~~~~~~~~~~~~~
Arq Worker 설정 및 백그라운드 작업 정의.

이 모듈은 `arq app.core.worker.WorkerSettings` 명령어로 실행됩니다.
비동기 작업(메일 발송, 대량 데이터 처리 등)을 처리합니다.
"""
import asyncio
import logging

from arq.connections import RedisSettings

from app.core.config import settings
from app.core.redis import close_redis, init_redis
from app.utils.logging import setup_logging

logger = logging.getLogger(__name__)

async def sample_background_task(ctx: dict, name: str) -> str:
    """샘플 백그라운드 작업."""
    logger.info("백그라운드 작업 시작: %s", name)
    await asyncio.sleep(2)  # 무거운 작업 시뮬레이션
    return f"Hello, {name}! Task completed."


async def startup(ctx: dict) -> None:
    """Worker 시작 시 초기화 (DB 연결 등)."""
    setup_logging(service_name="worker")
    await init_redis()
    logger.info("Worker startup complete")


async def shutdown(ctx: dict) -> None:
    """Worker 종료 시 정리."""
    await close_redis()
    logger.info("Worker shutdown complete")


# Redis 설정
# redis://[:password]@host:port/db
from urllib.parse import urlparse
_url = urlparse(settings.REDIS_URL)

redis_settings = RedisSettings(
    host=_url.hostname or "localhost",
    port=_url.port or 6379,
    database=int(_url.path[1:]) if _url.path else 0,
    password=_url.password
)

class WorkerSettings:
    """Arq Worker 설정 클래스."""

    redis_settings = redis_settings
    functions = [sample_background_task]
    on_startup = startup
    on_shutdown = shutdown
    job_timeout = settings.ARQ_JOB_TIMEOUT
    max_jobs = 10
