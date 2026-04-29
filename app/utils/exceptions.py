"""
app/utils/exceptions.py
~~~~~~~~~~~~~~~~~~~~~~~
커스텀 예외 클래스 계층 및 Global Exception Handler.

모든 비즈니스 에러는 AppException을 상속한 커스텀 예외를 사용합니다.
HTTPException은 엔드포인트 계층에서만 허용하고,
Service/CRUD 계층에서는 반드시 이 모듈의 예외를 사용합니다.
"""
import traceback
from datetime import datetime, timezone

import sentry_sdk
import structlog
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings


class AppException(Exception):
    """애플리케이션 예외 기반 클래스.

    모든 비즈니스 로직 예외의 부모 클래스.
    Global Exception Handler에서 일관된 JSON 응답으로 변환됩니다.
    """

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"
    message: str = "내부 서버 오류가 발생했습니다."

    def __init__(self, message: str | None = None, detail: str | None = None) -> None:
        self.message = message or self.__class__.message
        self.detail = detail
        super().__init__(self.message)


class BadRequest(AppException):
    """400 — 잘못된 요청."""

    status_code = 400
    error_code = "BAD_REQUEST"
    message = "잘못된 요청입니다."


class Unauthorized(AppException):
    """401 — 인증 실패 (토큰 없음/만료/무효)."""

    status_code = 401
    error_code = "UNAUTHORIZED"
    message = "인증이 필요합니다."


class Forbidden(AppException):
    """403 — 권한 부족."""

    status_code = 403
    error_code = "FORBIDDEN"
    message = "권한이 부족합니다."


class NotFound(AppException):
    """404 — 리소스 없음."""

    status_code = 404
    error_code = "NOT_FOUND"
    message = "요청한 리소스를 찾을 수 없습니다."


class Conflict(AppException):
    """409 — 리소스 충돌 (중복 이메일 등)."""

    status_code = 409
    error_code = "CONFLICT"
    message = "이미 존재하는 리소스입니다."


class ValidationError(AppException):
    """422 — 검증 실패."""

    status_code = 422
    error_code = "VALIDATION_ERROR"
    message = "입력값이 올바르지 않습니다."


class RateLimitExceeded(AppException):
    """429 — 호출 횟수 초과."""

    status_code = 429
    error_code = "RATE_LIMITED"
    message = "요청 횟수가 초과되었습니다. 잠시 후 다시 시도해주세요."


class InternalServerError(AppException):
    """500 — 내부 서버 오류."""

    status_code = 500
    error_code = "INTERNAL_ERROR"
    message = "내부 서버 오류가 발생했습니다."


# ── Global Exception Handlers ──────────────────────────────
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """AppException 계열 예외를 일관된 JSON으로 변환합니다."""
    trace_id = structlog.contextvars.get_contextvars().get("request_id")
    
    content = {
        "statusCode": exc.status_code,
        "message": exc.message,
        "error": exc.error_code,
        "path": request.url.path,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "traceId": trace_id
    }
    
    # 개발 환경에서만 에러 상세 내용 노출
    if settings.APP_ENV in ("local", "development") and exc.detail:
        content["stack"] = exc.detail
        
    return JSONResponse(status_code=exc.status_code, content=content)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """처리되지 않은 예외를 안전하게 500 응답으로 변환합니다.

    ⚠️ 내부 스택 트레이스는 절대 클라이언트에 노출하지 않습니다.
    (서버 로그에만 기록 및 Sentry 전송)
    """
    sentry_sdk.capture_exception(exc)
    trace_id = structlog.contextvars.get_contextvars().get("request_id")
    
    content = {
        "statusCode": 500,
        "message": "내부 서버 오류가 발생했습니다.",
        "error": "INTERNAL_ERROR",
        "path": request.url.path,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "traceId": trace_id
    }
    
    # 개발 환경에서만 시스템 스택 트레이스 노출
    if settings.APP_ENV in ("local", "development"):
        content["stack"] = traceback.format_exc()
        
    return JSONResponse(status_code=500, content=content)


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """FastAPI의 RequestValidationError를 400(Bad Request) 응답으로 변환합니다."""
    trace_id = structlog.contextvars.get_contextvars().get("request_id")
    
    errors = exc.errors()
    message = "잘못된 요청 형식입니다. 필수 파라미터를 확인해주세요."
    if errors:
        loc = " -> ".join([str(x) for x in errors[0].get("loc", [])])
        message = f"입력 검증 실패: {errors[0].get('msg')} (위치: {loc})"

    content = {
        "statusCode": 400,
        "message": message,
        "error": "BAD_REQUEST",
        "path": request.url.path,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "traceId": trace_id
    }
    
    if settings.APP_ENV in ("local", "development"):
        content["stack"] = str(errors)
        
    return JSONResponse(status_code=400, content=content)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Starlette의 HTTPException(예: 404, 405)을 규격에 맞게 변환합니다."""
    trace_id = structlog.contextvars.get_contextvars().get("request_id")
    
    # 404 Not Found 등에 대한 기본 에러 코드 매핑
    error_code_map = {
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED"
    }
    error_code = error_code_map.get(exc.status_code, "HTTP_EXCEPTION")
    
    content = {
        "statusCode": exc.status_code,
        "message": str(exc.detail),
        "error": error_code,
        "path": request.url.path,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "traceId": trace_id
    }
    
    return JSONResponse(status_code=exc.status_code, content=content)
