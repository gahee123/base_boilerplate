"""
app/utils/cache.py
~~~~~~~~~~~~~~~~~~
Redis 캐싱 데코레이터.

API 응답을 Redis에 캐싱하여 동일 요청의 DB 조회를 생략합니다.
Redis 미연결 시 캐시를 무시하고 원본 함수를 실행합니다 (graceful fallback).
"""
import functools
import hashlib
import json
import logging
from typing import Any

from fastapi import Request

logger = logging.getLogger(__name__)


def cached(ttl: int = 60, prefix: str = "cache"):
    """API 응답 캐싱 데코레이터.

    요청 경로 + 쿼리 파라미터로 캐시 키를 생성하고,
    Redis에 JSON 직렬화하여 저장합니다.

    Args:
        ttl: 캐시 유효 시간 (초, 기본 60초)
        prefix: Redis 키 접두사

    Usage:
        @router.get("/items")
        @cached(ttl=300)
        async def get_items(request: Request, ...):
            ...

    ⚠️ 주의사항:
        - 핸들러 함수의 첫 번째 인자 또는 `request` 키워드 인자로
          FastAPI Request 객체가 필요합니다.
        - 반환값은 JSON 직렬화 가능해야 합니다 (dict, list, Pydantic model).
        - 사용자별로 다른 응답을 반환하는 API에는 적합하지 않습니다.
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Request 객체 추출
            request: Request | None = kwargs.get("request")
            if request is None:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            # Redis 클라이언트 추출
            redis = kwargs.get("redis")

            # Redis 없거나 Request 없으면 캐시 없이 실행
            if redis is None or request is None:
                return await func(*args, **kwargs)

            # 캐시 키 생성: prefix:path:query_hash
            query_str = str(sorted(request.query_params.items()))
            query_hash = hashlib.md5(query_str.encode()).hexdigest()[:12]
            cache_key = f"{prefix}:{request.url.path}:{query_hash}"

            # 캐시 히트 체크
            try:
                cached_data = await redis.get(cache_key)
                if cached_data is not None:
                    logger.debug("캐시 히트: %s", cache_key)
                    return json.loads(cached_data)
            except Exception:
                logger.warning("캐시 읽기 실패: %s", cache_key)

            # 캐시 미스 → 원본 함수 실행
            result = await func(*args, **kwargs)

            # 결과를 캐시에 저장
            try:
                # Pydantic 모델이면 dict로 변환
                if hasattr(result, "model_dump"):
                    cache_value = json.dumps(result.model_dump(), default=str)
                else:
                    cache_value = json.dumps(result, default=str)

                await redis.set(cache_key, cache_value, ex=ttl)
                logger.debug("캐시 저장: %s (ttl=%ds)", cache_key, ttl)
            except Exception:
                logger.warning("캐시 저장 실패: %s", cache_key)

            return result

        return wrapper

    return decorator
