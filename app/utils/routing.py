"""
app/utils/routing.py
~~~~~~~~~~~~~~~~~~~~
커스텀 라우팅 유틸리티 모듈.
API 엔드포인트의 반환값을 공통 규격으로 자동 래핑하는 기능을 제공합니다.
"""
import inspect
from functools import wraps
from typing import Any, Callable

from fastapi import APIRouter

from app.schemas.base import SuccessResponse


class AutoWrapRouter(APIRouter):
    """
    엔드포인트의 반환값을 SuccessResponse 구조로 자동 래핑하는 커스텀 라우터.
    Swagger(OpenAPI) 문서에도 래핑된 응답 구조를 자동으로 반영합니다.
    """

    def add_api_route(self, path: str, endpoint: Callable[..., Any], **kwargs: Any) -> None:
        response_model = kwargs.get("response_model")

        # response_model이 명시되어 있는 경우에만 래핑을 수행합니다.
        # (RedirectResponse 등 직접 Response 객체를 반환하는 경우는 제외)
        if response_model:
            origin = getattr(response_model, "__origin__", response_model)
            # 이미 SuccessResponse로 래핑되어 있지 않은 경우에만 적용
            if origin is not SuccessResponse:
                kwargs["response_model"] = SuccessResponse[response_model]

                is_coroutine = inspect.iscoroutinefunction(endpoint)

                # FastAPI의 의존성 주입(Dependency Injection)이 깨지지 않도록
                # @wraps를 사용하여 원래 함수의 시그니처를 보존합니다.
                if is_coroutine:
                    @wraps(endpoint)
                    async def async_wrapper(*args: Any, **kw: Any) -> Any:
                        result = await endpoint(*args, **kw)
                        return SuccessResponse(data=result)
                    endpoint_to_use = async_wrapper
                else:
                    @wraps(endpoint)
                    def sync_wrapper(*args: Any, **kw: Any) -> Any:
                        result = endpoint(*args, **kw)
                        return SuccessResponse(data=result)
                    endpoint_to_use = sync_wrapper
            else:
                endpoint_to_use = endpoint
        else:
            endpoint_to_use = endpoint

        kwargs.pop("endpoint", None)
        super().add_api_route(path, endpoint_to_use, **kwargs)
