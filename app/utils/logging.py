"""
app/utils/logging.py
~~~~~~~~~~~~~~~~~~~~
구조화 로깅 설정 및 Request ID 미들웨어.

structlog 기반 JSON 로깅으로 로그를 구조화하고,
모든 요청에 고유 request_id를 부여하여 추적성을 확보합니다.
"""
import logging
import sys
import time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from uuid import uuid4

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.config import settings


def setup_logging(service_name: str | None = None) -> None:
    """structlog 기반 로깅을 초기화합니다.

    Args:
        service_name: 로그에 기록될 서비스 이름 (예: 'api', 'worker').

    settings.LOG_FORMAT에 따라 JSON 또는 텍스트 형식으로 출력합니다.
    FastAPI lifespan의 startup 단계에서 호출됩니다.
    """
    # 공통 프로세서
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if service_name:
        # 서비스 이름을 모든 로그에 강제로 삽입
        shared_processors.insert(0, lambda _l, _m, ed: ed.update(service=service_name) or ed)

    # 포맷별 렌더러 선택
    if settings.LOG_FORMAT == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # 표준 라이브러리 로거 설정
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # 파일 핸들러 (LOG_FILE_PATH가 설정된 경우)
    if settings.LOG_FILE_PATH:
        log_path = Path(settings.LOG_FILE_PATH)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # 파일 로그는 항상 JSON 포맷 (머신 파싱용)
        json_formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.JSONRenderer(),
            ],
        )
        file_handler = TimedRotatingFileHandler(
            str(log_path),
            when="midnight",     # 자정마다 새 파일
            interval=1,          # 매일
            backupCount=settings.LOG_BACKUP_COUNT,      # 설정된 보관 기간 후 자동 삭제
            encoding="utf-8",
        )
        file_handler.suffix = "%Y-%m-%d"  # app.log.2026-04-15
        file_handler.setFormatter(json_formatter)
        root_logger.addHandler(file_handler)

    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    # 외부 라이브러리 로그 레벨 조정
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.DEBUG if settings.is_debug else logging.WARNING,
    )


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Request ID 미들웨어.

    모든 요청에 UUID 기반 request_id를 부여합니다.
    - 요청 헤더에 X-Request-ID가 있으면 재사용
    - 없으면 새로 생성
    - 응답 헤더에 X-Request-ID로 반환
    - structlog contextvars에 바인딩하여 모든 로그에 자동 포함

    Usage:
        로그에서 특정 요청을 추적할 때:
        {"event": "사용자 조회", "request_id": "550e8400-...", ...}
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """요청마다 request_id를 생성하고 로그 컨텍스트에 바인딩합니다."""
        # Request ID 추출 또는 생성
        request_id = request.headers.get("X-Request-ID", str(uuid4()))

        # structlog 컨텍스트에 바인딩
        # 기존 컨텍스트(예: service) 유지하면서 request_id 등을 추가
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        logger = structlog.get_logger()

        # 요청 시작 로그
        start_time = time.time()
        await logger.ainfo(
            "요청 시작",
            client_ip=self._get_client_ip(request),
        )

        # 요청 처리
        response = await call_next(request)

        # 요청 완료 로그
        duration_ms = round((time.time() - start_time) * 1000, 2)
        await logger.ainfo(
            "요청 완료",
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        # 응답 헤더에 Request ID 추가
        response.headers["X-Request-ID"] = request_id
        return response

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        """클라이언트 IP를 추출합니다."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"
