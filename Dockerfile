# ============================================================
# Stage 1: Builder — 의존성 설치
# ============================================================
FROM python:3.11-slim AS builder

WORKDIR /build

# Poetry 설치
RUN pip install --no-cache-dir poetry==1.8.4

# 의존성 파일만 먼저 복사 (레이어 캐싱 최적화)
COPY pyproject.toml poetry.lock* ./

# requirements.txt 생성 (런타임 이미지에서 Poetry 불필요)
RUN poetry export -f requirements.txt --without-hashes --without dev -o requirements.txt

# 가상 환경 생성 및 의존성 설치
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -r requirements.txt

# ============================================================
# Stage 2: Dev — 로컬 개발 및 테스트 런타임 (Dev 의존성 포함)
# ============================================================
FROM builder AS dev
WORKDIR /code
COPY pyproject.toml poetry.lock* ./

# 개발 환경에서는 Poetry 자체를 사용하여 통째로 설치 (pytest, ruff 등 포함)
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ============================================================
# Stage 3: Runtime — 최소 크기 프로덕션 이미지
# ============================================================
FROM python:3.11-slim AS runtime

# 보안: non-root 사용자 생성
RUN groupadd -r appuser && useradd -r -g appuser -d /code -s /sbin/nologin appuser

WORKDIR /code

# Builder에서 설치한 가상환경 복사
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 앱 코드 복사
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# 로그 디렉터리 생성 및 소유권 설정
RUN mkdir -p /code/logs && chown -R appuser:appuser /code

# non-root 사용자로 전환
USER appuser

EXPOSE 8000

# 헬스 체크 (Docker가 컨테이너 상태 모니터링)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz/live')"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
