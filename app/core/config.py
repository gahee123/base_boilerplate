"""
app/core/config.py
~~~~~~~~~~~~~~~~~~
애플리케이션 환경 설정.

pydantic-settings 기반으로 .env 파일에서 환경 변수를 로드합니다.
모든 설정값은 이 모듈의 `settings` 싱글톤을 통해서만 접근해야 합니다.
"""
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """애플리케이션 전역 설정.

    .env 파일 또는 시스템 환경 변수에서 값을 로드합니다.
    대소문자를 구분하지 않으며, 모든 설정값은 이 클래스에 집중합니다.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────
    APP_NAME: str = "FastAPI Boilerplate"
    APP_ENV: str = "development"  # development | staging | production
    APP_DEBUG: bool = True
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    # ── Database (PostgreSQL) ────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/app_db"

    # ── Redis ────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    NOTIFICATIONS_SSE_CHANNEL: str = "notifications:sse"
    ARQ_JOB_TIMEOUT: int = 60

    # ── JWT Authentication ───────────────────────────────────
    JWT_SECRET_KEY: str = "CHANGE-THIS-IN-PRODUCTION-USE-LONG-RANDOM-STRING"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 5  # 5분 (보안 강화)
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    AUTH_CODE_EXPIRE_SECONDS: int = 60         # 임시 인증 코드 수명

    # ── CORS ─────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8080"]

    # ── Rate Limiting ────────────────────────────────────────
    RATE_LIMIT_MAX_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # ── Logging ──────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json | text
    LOG_FILE_PATH: str = "logs/app.log"  # 로그 파일 경로 (빈 문자열이면 파일 로깅 비활성)
    LOG_BACKUP_COUNT: int = 30  # 로그 보관 기간 (일 단위)

    # ── Audit & Resilience ───────────────────────────────────
    AUDIT_LOG_ENABLED: bool = True
    SENTRY_DSN: str | None = None

    # ── HMG SSO Auth ─────────────────────────────────────────
    HMG_SSO_BASE_URL: str | None = None
    HMG_SSO_CLIENT_ID: str | None = None
    HMG_SSO_CLIENT_SECRET: str | None = None
    HMG_SSO_CIPHER_KEY: str | None = None  # AES-GCM 암복호화를 위한 사전 공유키 (64자 Hex 문자열)
    HMG_SSO_CALLBACK_URI: str | None = None
    HMG_SSO_POST_LOGOUT_REDIRECT_URI: str | None = None
    HMG_SSO_FRONTEND_LOGIN_CALLBACK_URL: str | None = None
    LOGIN_SESSION_TIMEOUT_MINUTES: int = 30   # 쿠키 max-age (브라우저 보관 시간)
    SESSION_IDLE_TIMEOUT_MINUTES: int = 30    # 비활동 세션 만료 (Redis Sliding Window TTL)

    # ── Apache Superset Integration ──────────────────────────
    SUPERSET_BASE_URL: str = "http://localhost:8088"
    SUPERSET_ADMIN_USER: str = "admin"
    SUPERSET_ADMIN_PASSWORD: str = "admin"
    SUPERSET_DEFAULT_DASHBOARD_ID: int = 1  # 템플릿으로 사용할 대시보드 ID
    SUPERSET_USER_ROLE: str = "Alpha"       # 모든 유저에게 부여할 기본 역할 (편집 가능)

    # ── Validators ───────────────────────────────────────────
    @field_validator("APP_ENV")
    @classmethod
    def validate_app_env(cls, v: str) -> str:
        """APP_ENV는 development, staging, production 중 하나만 허용."""
        allowed = {"development", "staging", "production"}
        if v not in allowed:
            raise ValueError(f"APP_ENV must be one of {allowed}, got '{v}'")
        return v

    @field_validator("LOG_FORMAT")
    @classmethod
    def validate_log_format(cls, v: str) -> str:
        """LOG_FORMAT은 json 또는 text만 허용."""
        allowed = {"json", "text"}
        if v not in allowed:
            raise ValueError(f"LOG_FORMAT must be one of {allowed}, got '{v}'")
        return v

    @property
    def is_production(self) -> bool:
        """프로덕션 환경 여부."""
        return self.APP_ENV == "production"

    @property
    def is_debug(self) -> bool:
        """디버그 모드 여부 (프로덕션에서는 항상 False)."""
        if self.is_production:
            return False
        return self.APP_DEBUG


# ── 싱글톤 인스턴스 ──────────────────────────────────────────
settings = Settings()
