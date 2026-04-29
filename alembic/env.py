"""
alembic/env.py
~~~~~~~~~~~~~~
Alembic 마이그레이션 환경 설정.

비동기(asyncpg) URL을 동기(psycopg2) URL로 변환하여
Alembic이 DB에 접속할 수 있도록 합니다.
"""
import os
import sys
from logging.config import fileConfig

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.core.config import settings
from app.models.base import Base

# ── 모든 모델 import (autogenerate가 감지하려면 필수) ──────
from app.models.user import User  # noqa: F401

# Alembic Config 객체
config = context.config

# 로깅 설정
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# autogenerate 대상 메타데이터
target_metadata = Base.metadata


def get_url() -> str:
    """async URL → sync URL 변환.

    asyncpg는 Alembic에서 직접 사용 불가하므로,
    psycopg2 드라이버로 변환합니다.
    """
    return settings.DATABASE_URL.replace("+asyncpg", "+psycopg2")


def run_migrations_offline() -> None:
    """'Offline' 모드: DB 연결 없이 SQL 스크립트만 생성.

    Usage:
        alembic revision --autogenerate -m "설명" --sql
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """'Online' 모드: DB에 직접 연결하여 마이그레이션 실행.

    Usage:
        alembic upgrade head
    """
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
