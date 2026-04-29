"""
app/utils/rate_limit.py
~~~~~~~~~~~~~~~~~~~~~~~
Rate Limiting 미들웨어.

슬라이딩 윈도우 알고리즘 기반으로 클라이언트 IP별 요청 횟수를 제한합니다.
Redis 미연결 시 제한 없이 통과합니다 (graceful fallback).
"""
import logging
import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

from app.core.config import settings
from app.core.redis import get_redis

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """IP 기반 Rate Limiting 미들웨어.

    슬라이딩 윈도우 알고리즘으로 구현:
    - Redis Sorted Set에 타임스탬프를 기록
    - 윈도우 내 요청 수가 임계값을 초과하면 429 반환
    - 초과 시 Retry-After 헤더 포함

    Settings:
        RATE_LIMIT_MAX_REQUESTS: 윈도우 내 최대 요청 수 (기본 100)
        RATE_LIMIT_WINDOW_SECONDS: 윈도우 크기 (기본 60초)
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """요청마다 Rate Limit을 체크합니다."""
        # 헬스 체크 등 시스템 경로는 제외
        excluded_paths = {"/healthz/live", "/healthz/ready", "/docs", "/redoc", "/openapi.json"}
        if request.url.path in excluded_paths:
            return await call_next(request)

        redis = await get_redis()

        # Redis 미연결 시 제한 없이 통과 (graceful fallback)
        if redis is None:
            return await call_next(request)

        # 클라이언트 IP 추출
        client_ip = self._get_client_ip(request)
        rate_key = f"rl:{client_ip}"
        now = time.time()
        window_start = now - settings.RATE_LIMIT_WINDOW_SECONDS

        try:
            # 파이프라인으로 원자적 처리
            pipe = redis.pipeline()
            # 1. 윈도우 밖의 오래된 요청 제거
            pipe.zremrangebyscore(rate_key, 0, window_start)
            # 2. 현재 요청 추가
            pipe.zadd(rate_key, {str(now): now})
            # 3. 윈도우 내 요청 수 조회
            pipe.zcard(rate_key)
            # 4. TTL 설정 (윈도우 크기 + 여유 1초)
            pipe.expire(rate_key, settings.RATE_LIMIT_WINDOW_SECONDS + 1)
            results = await pipe.execute()

            request_count = results[2]

            if request_count > settings.RATE_LIMIT_MAX_REQUESTS:
                logger.warning(
                    "Rate limit 초과: ip=%s, count=%d/%d",
                    client_ip,
                    request_count,
                    settings.RATE_LIMIT_MAX_REQUESTS,
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "RATE_LIMITED",
                            "message": "요청 횟수가 초과되었습니다. 잠시 후 다시 시도해주세요.",
                            "detail": None,
                        },
                    },
                    headers={
                        "Retry-After": str(settings.RATE_LIMIT_WINDOW_SECONDS),
                        "X-RateLimit-Limit": str(settings.RATE_LIMIT_MAX_REQUESTS),
                        "X-RateLimit-Remaining": "0",
                    },
                )

            # 정상 요청 → 다음 미들웨어/핸들러로
            response = await call_next(request)
            remaining = max(0, settings.RATE_LIMIT_MAX_REQUESTS - request_count)
            response.headers["X-RateLimit-Limit"] = str(settings.RATE_LIMIT_MAX_REQUESTS)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            return response

        except Exception:
            logger.warning("Rate limit 처리 실패: ip=%s — 제한 없이 통과", client_ip)
            return await call_next(request)

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        """클라이언트 IP를 추출합니다.

        X-Forwarded-For 헤더가 있으면 첫 번째 IP를,
        없으면 request.client.host를 사용합니다.
        """
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"
