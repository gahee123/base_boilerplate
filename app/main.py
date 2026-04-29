"""
app/main.py
~~~~~~~~~~~
FastAPI 앱 진입점.

앱 생명주기(lifespan), 미들웨어, 라우터 등록을 관리합니다.
"""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.redis import close_redis, get_redis, init_redis
from app.utils.exceptions import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.utils.logging import RequestIDMiddleware, setup_logging
from app.utils.rate_limit import RateLimitMiddleware

# ── Sentry 초기화 ─────────────────────────────────────────────
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.APP_ENV,
        traces_sample_rate=1.0 if settings.is_debug else 0.1,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """앱 생명주기 관리.

    Startup:
        - Redis 커넥션 풀 초기화

    Shutdown:
        - Redis 커넥션 풀 정리
    """
    # ── Startup ──
    setup_logging(service_name="api")
    await init_redis()
    yield
    # ── Shutdown ──
    await close_redis()


app = FastAPI(
    title=settings.APP_NAME,
    description="""
## 🚀 FastAPI Backend Boilerplate

프로덕션 레디 FastAPI 백엔드 보일러플레이트입니다. 
현대적이고 확장 가능한 아키텍처를 기반으로 설계되었습니다.

### 🌟 주요 기능
- **인증/보안**: JWT 인증, OIDC(SSO) 통합 인터페이스, RBAC 시스템.
- **아키텍처**: Generic CRUD, Layered Architecture, 플러그형 감사 로그(Audit).
- **기능**: 다채널 알림(Notification) 팩토리.
- **성능/유틸리티**: 슬라이딩 윈도우 기반 Rate Limit & 분산 Redis 캐싱.
- **DevOps**: Helm Chart 배포, Docker 컨테이너라이제이션.
- **로깅**: structlog 구조화 로깅, Sentry 연동.

### 🔑 인증 방법
1. `/api/v1/auth/register`에서 계정을 생성합니다.
2. `/api/v1/auth/login`에서 `username`(이메일)과 `password`를 입력하여 토큰을 발급받습니다.
3. 이 페이지 상단의 **Authorize** 버튼을 누르고 `Bearer {발급받은_액세스_토큰}`을 입력합니다.
    """,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
    openapi_tags=[
        {
            "name": "Authentication",
            "description": "회원가입, 로그인, 토큰 갱신, 로그아웃",
        },
        {
            "name": "Users",
            "description": "일반 사용자 본인 관련 기능 (내 프로필 등)",
        },
        {
            "name": "Admin: Users",
            "description": "관리자용 전체 사용자 조회 및 가입 승인 관리",
        },
        {
            "name": "Admin: User Groups",
            "description": "관리자용 부서 정보(화이트리스트) 관리 및 자동 동기화",
        },
        {
            "name": "Admin: Permissions",
            "description": "슈퍼 어드민 전용 권한 관리 및 관리자 승격/해임",
        },
        {
            "name": "Notifications",
            "description": "다채널(Email, SMS, Push) 알림 발송 Factory",
        },
        {
            "name": "System",
            "description": "헬스 체크(Liveness/Readiness) 및 서버 상태 모니터링",
        },
    ],
    contact={
        "name": "Project Support",
        "url": "https://github.com/your-username/fastapi-boilerplate",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
)

# ── 미들웨어 등록 ───────────────────────────────────────────
# 실행 순서: CORS → RequestID → RateLimit (등록은 역순)
# Starlette 미들웨어는 나중에 등록한 것이 먼저 실행됩니다.

app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 예외 핸들러 등록 ────────────────────────────────────────
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(AppException, app_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, unhandled_exception_handler)  # type: ignore[arg-type]

# ── 라우터 등록 ─────────────────────────────────────────────
app.include_router(api_v1_router, prefix="/api/v1")


# ── 헬스 체크 프로브 (Health Probes) ────────────────────────────────
@app.get(
    "/healthz/live",
    tags=["System"],
    summary="Liveness Probe",
    description="애플리케이션 프로세스가 활성화되어 동작 중인지 확인합니다.",
)
async def liveness_probe() -> dict[str, str]:
    """K8s Liveness 제어용 엔드포인트."""
    return {"status": "ok"}


@app.get(
    "/healthz/ready",
    tags=["System"],
    summary="Readiness Probe",
    description="애플리케이션이 트래픽을 처리할 준비가 되었는지 외부 의존성(Redis 등)을 점검합니다.",
)
async def readiness_probe() -> dict[str, str]:
    """K8s Readiness 제어용 엔드포인트: Redis 상태까지 점검합니다."""
    redis = await get_redis()
    if redis is None:
        return {"status": "unready", "detail": "Redis connection failed"}

    try:
        await redis.ping()
    except Exception:
        return {"status": "unready", "detail": "Redis ping failed"}

    return {"status": "ready"}
