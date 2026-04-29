# 💻 Agent 03: 백엔드 개발 — Phase 4 유틸리티 구현 보고서

> 생성일: 2026-04-15  
> 에이전트: 백엔드 개발 (`03_backend_dev.md`)  
> 커버 태스크: TASK-017 ~ TASK-021

---

## 구현 파일 목록

| TASK | 파일 | 줄 수 | 핵심 내용 |
|------|------|:-----:|----------|
| TASK-017 | `app/utils/exceptions.py` | ~120 | AppException 등 전역 예외 정의 및 핸들러 |
| TASK-018 | `app/utils/cache.py` | ~95 | `@cached(ttl=60)` Redis 캐싱 데코레이터 |
| TASK-019 | `app/utils/rate_limit.py` | ~120 | RateLimitMiddleware (슬라이딩 윈도우) |
| TASK-020 | `app/utils/logging.py` | ~145 | structlog JSON 로깅 + RequestIDMiddleware |
| TASK-021 | `app/main.py`, `exceptions.py` | - | Sentry_sdk.init 및 capture_exception 적용 브릿징 |
| TASK-022 | `app/utils/sse.py` | ~60 | SSE(Server-Sent Events) 스트리밍 제네레이터 |

---

## 각 파일 상세 설명

### TASK-017: `app/utils/exceptions.py` — 전역 예외 처리
- 통합 런타임 제어를 위해 `AppException` 기반의 구조적 커스텀 예외들을 구현했습니다.
- 클라이언트에 대한 일관성있는 JSON 에러 포맷 (`code`, `message`, `detail`)을 반환합니다.

### TASK-018: `app/utils/cache.py` — 캐싱 데코레이터

**사용법:**
```python
@router.get("/items")
@cached(ttl=300)
async def get_items(request: Request, redis=Depends(get_redis)):
    # 첫 요청: DB 조회 → Redis에 저장 (5분간)
    # 이후 요청: Redis에서 즉시 반환
```

**동작 원리:**
1. 캐시 키: `cache:/api/v1/items:쿼리파라미터해시`
2. 캐시 히트 → JSON 역직렬화하여 즉시 반환
3. 캐시 미스 → 원본 함수 실행 → 결과를 JSON으로 Redis에 저장
4. Pydantic 모델은 `model_dump()` → JSON 자동 변환
5. Redis 없으면 → 캐시 무시, 원본 함수 그냥 실행

### TASK-019: `app/utils/rate_limit.py` — Rate Limiting

**알고리즘: 슬라이딩 윈도우 (Redis Sorted Set)**
1. 클라이언트 IP로 키 생성: `rl:192.168.1.1`
2. Sorted Set에 현재 타임스탬프 추가
3. 윈도우 밖의 오래된 요청 제거
4. 윈도우 내 요청 수가 `MAX_REQUESTS`(100) 초과 → 429 반환

**응답 헤더:**
- `X-RateLimit-Limit: 100` — 최대 허용 횟수
- `X-RateLimit-Remaining: 87` — 남은 횟수
- `Retry-After: 60` — 초과 시 언제 다시 가능한지

**제외 경로:** `/healthz/live`, `/healthz/ready`, `/docs`, `/redoc`, `/openapi.json`

### TASK-020: `app/utils/logging.py` — 로깅 + Request ID

**structlog 설정:**
- `json` 포맷: ELK/CloudWatch 등 외부 시스템 연동용
- `text` 포맷: 로컬 개발 시 가독성 높은 컬러 출력

**로그 출력 대상 (2중):**
- **stdout**: 터미널/Docker 로그 연동 (`LOG_FORMAT`에 따라 json 또는 text)
- **파일**: `logs/app.log` → 항상 JSON 포맷 (머신 파싱용)
  - 자정마다 새 파일 생성 (`app.log.2026-04-15`)
  - 30일 보관 후 자동 삭제
  - `LOG_FILE_PATH=""` 으로 파일 로깅 비활성화 가능

**RequestID 미들웨어:**
- 요청 헤더에 `X-Request-ID`가 있으면 재사용, 없으면 UUID 생성
- 응답 헤더에 `X-Request-ID` 반환
- structlog contextvars에 바인딩 → **해당 요청의 모든 로그에 자동 포함**

**로그 출력 예시:**
```json
{
  "event": "요청 완료",
  "request_id": "550e8400-...",
  "method": "GET",
  "path": "/api/v1/users/me",
  "status_code": 200,
  "duration_ms": 12.5,
  "timestamp": "2026-04-15T12:00:00Z"
}
```

### TASK-021: Sentry 연동 에러 트래킹 보조 (`exceptions.py`, `main.py`)

- `main.py` 부트스트랩: `settings.SENTRY_DSN`이 존재할 때 `sentry_sdk.init`으로 모니터링 활성화.
- `unhandled_exception_handler()`: 예상치 못한 서버 오류(`500 Internal Server Error`) 발생 시, 클라이언트에는 포장된 메시지만 보내고 `sentry_sdk.capture_exception(exc)`을 호출하여 Sentry 대시보드로 Stacktrace를 전송. 

### main.py 수정사항

```
미들웨어 실행 순서 (위→아래):
  CORS → RequestID → RateLimit → 엔드포인트

Startup 순서:
  setup_logging() → init_redis()
```

### config.py 추가 환경 변수

| 변수명 | 기본값 | 설명 |
|--------|--------|------|
| `LOG_FILE_PATH` | `"logs/app.log"` | 로그 파일 경로 (빈 문자열이면 비활성) |
| `SENTRY_DSN` | `None` | Sentry 이벤트 전송/트래킹 DSN 키 |
| `NOTIFICATIONS_SSE_CHANNEL` | `"notifications:sse"` | 실시간 알림용 Redis Pub/Sub 채널명 |

### 🛠️ 신규 추가 항목: TASK-022 (SSE & Redis Pub/Sub)

**분산 환경 실시간 전송 프로세스:**
1. 클라이언트가 `/api/v1/notifications/sse`로 접속하여 서버와 연결 유지.
2. 여러 대의 앱 서버 인스턴스가 독립적으로 구동되더라도, 모두 동일한 Redis 채널을 구독(Subscribe).
3. 알림 이벤트 발생 시 어느 서버에서든 Redis로 발행(Publish)하면, 물리적으로 다른 서버에 연결된 클라이언트에게도 실시간 메시지가 스트리밍됨.

**주요 구현 디테일:**
- **Keep-alive (Heartbeat)**: 15초 간격으로 하트비트 세션을 유지하여 프록시/로드밸런서의 타임아웃 방지.
- **User Targeting**: 메시지 페이로드에 `target_user_id`를 포함하여, 해당 유저 세션에게만 선별적으로 전송 가능.
- **Auto Cleanup**: 세션 종료 시 Redis 리소스를 자동으로 반환하는 `finally` 블록 처리.
