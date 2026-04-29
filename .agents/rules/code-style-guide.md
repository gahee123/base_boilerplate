# 📏 코딩 컨벤션 & 스타일 가이드

> 이 문서는 **모든 워크플로 에이전트**가 코드를 생성할 때 반드시 준수해야 하는 공통 규칙입니다.  
> 개별 에이전트의 도메인 규칙보다 이 문서의 규칙이 **우선**합니다.

---

## 1. Python 기본 규칙

### 버전 및 호환성
- **Python 3.11+** 기준으로 작성
- 3.10 이하에서만 사용 가능한 패턴 금지
- `from __future__ import annotations` 사용 금지 (Pydantic v2 호환 이슈)

### 포매팅
- **Ruff** 기반 포매팅 (`ruff format`) 및 린트 (`ruff check`)
- 줄 길이: **100자**
- 들여쓰기: **스페이스 4칸** (탭 금지)
- 후행 콤마(trailing comma): 멀티라인 호출 시 **항상 포함**
- 문자열: **쌍따옴표(`"`)** 통일 (독스트링 포함)

### Import 규칙

```python
# ✅ 올바른 순서 (isort 기준):
# 1. 표준 라이브러리
import uuid
from datetime import datetime, timedelta

# 2. 서드파티
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

# 3. 로컬 (앱 내부)
from app.core.config import settings
from app.models.user import User
```

**금지 사항:**
```python
# ❌ 와일드카드 import
from app.models import *

# ❌ 상대 import (명시적 절대 경로만)
from ..core import config

# ❌ 미사용 import (ruff F401)
import os  # 사용하지 않으면 제거
```

### 타입 힌트

```python
# ✅ 모든 함수에 인자 타입 + 반환 타입 필수:
async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    ...

# ✅ Python 3.10+ 유니온 문법:
name: str | None = None       # ✅
name: Optional[str] = None    # ❌ (Optional 사용 금지)

# ✅ 컬렉션 내장 타입 사용:
items: list[str]              # ✅
items: List[str]              # ❌ (typing.List 사용 금지)
mapping: dict[str, int]       # ✅
mapping: Dict[str, int]       # ❌
```

---

## 2. FastAPI 규칙

### 라우터 정의

```python
# ✅ 올바른 패턴:
router = APIRouter(prefix="/users", tags=["Users"])

@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="사용자 조회",
    description="ID로 특정 사용자를 조회합니다.",
    status_code=status.HTTP_200_OK,
)
async def get_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> UserResponse:
    ...
```

**규칙:**
- `response_model` 항상 명시
- `summary`, `description` 항상 포함 (Swagger 문서용)
- `status_code` 기본값이 아닌 경우 명시 (201, 204 등)
- 핸들러 반환 타입 힌트도 추가 (IDE 지원)

### 의존성 주입

```python
# ✅ Depends()를 통한 주입만 허용:
async def my_endpoint(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    user: User = Depends(get_current_user),
):
    ...

# ❌ 전역 변수 직접 접근 금지:
async def my_endpoint():
    session = global_session  # ❌ 금지
```

### 앱 생명주기

```python
# ✅ lifespan context manager (FastAPI 0.109+):
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_redis()
    yield
    await close_redis()

app = FastAPI(lifespan=lifespan)

# ❌ deprecated 패턴:
@app.on_event("startup")     # ❌ 금지
@app.on_event("shutdown")    # ❌ 금지
```

---

## 3. SQLAlchemy 2.0 규칙

### 모델 정의

```python
# ✅ 2.0 스타일 (Mapped + mapped_column):
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, DateTime

class User(BaseModel):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")

# ❌ 1.x 스타일 금지:
class User(Base):
    email = Column(String(255))    # ❌ Column() 직접 사용 금지
```

### 세션 & 쿼리

```python
# ✅ 비동기 세션 + select 문:
from sqlalchemy import select

async def get_by_email(db: AsyncSession, email: str) -> User | None:
    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

# ❌ 금지 패턴:
db.query(User).filter(...)        # ❌ Legacy Query API
session.execute(text("SELECT *")) # ❌ Raw SQL (불가피한 경우 제외)
```

### 마이그레이션

```python
# Alembic autogenerate 사용:
# alembic revision --autogenerate -m "add users table"
# alembic upgrade head

# ⚠️ 모델 변경 시 반드시 마이그레이션 파일 생성
# ⚠️ 마이그레이션 파일은 수동 확인 후 적용 (autogenerate가 완벽하지 않음)
```

---

## 4. Pydantic v2 규칙

### 스키마 정의

```python
# ✅ v2 스타일:
from pydantic import BaseModel, ConfigDict, Field, EmailStr

class UserCreate(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "email": "user@example.com",
                    "password": "SecureP@ss123",
                }
            ]
        },
    )

    email: EmailStr = Field(..., description="사용자 이메일")
    password: str = Field(..., min_length=8, max_length=100)

# ❌ v1 스타일 금지:
class UserCreate(BaseModel):
    class Config:          # ❌ 금지
        orm_mode = True    # ❌ 금지 (from_attributes 사용)

# ❌ validator 데코레이터 금지:
@validator("email")        # ❌ 금지
# ✅ 대신:
@field_validator("email")  # ✅ v2 방식
@model_validator(mode="after")  # ✅ v2 방식
```

### 스키마 분리 원칙

모든 리소스에 대해 아래 패턴으로 스키마를 분리합니다:

| 스키마 | 용도 | 포함 필드 |
|--------|------|----------|
| `{Resource}Create` | POST 요청 바디 | 생성 시 필요한 필드만 |
| `{Resource}Update` | PATCH 요청 바디 | 모든 필드 Optional |
| `{Resource}Response` | 응답 (단건) | DB 필드 중 노출 가능한 것만 |
| `{Resource}ListResponse` | 응답 (목록) | `PaginatedResponse[{Resource}Response]` |

```python
# ⚠️ 민감 필드는 Response 스키마에서 반드시 제외:
# - hashed_password
# - refresh_token
# - internal_notes
```

---

## 5. 비동기 규칙

### 전 계층 async 일관성

```python
# ✅ 엔드포인트 → 서비스 → CRUD → DB 전부 async:
# Endpoint
@router.get("/users/{id}")
async def get_user(id: UUID, service: UserService = Depends()):
    return await service.get_user(id)

# Service
class UserService:
    async def get_user(self, id: UUID) -> User:
        return await self.crud.get(id=id)

# CRUD
class UserCRUD:
    async def get(self, db: AsyncSession, *, id: UUID) -> User | None:
        result = await db.execute(select(User).where(User.id == id))
        return result.scalar_one_or_none()

# ❌ async 체인 중간에 동기 호출 금지:
def sync_function():      # ❌ 이벤트 루프 블로킹
    time.sleep(1)          # ❌ asyncio.sleep() 사용
    requests.get(url)      # ❌ httpx.AsyncClient 사용
```

### CPU-bound 작업

```python
# CPU 집약적 작업은 run_in_executor로 오프로드:
import asyncio

async def hash_password_async(password: str) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, hash_password, password)
```

---

## 6. 에러 처리 규칙

### 커스텀 예외 사용

```python
# ✅ 비즈니스 로직에서 커스텀 예외:
from app.utils.exceptions import NotFound, Conflict, Unauthorized

async def get_user(self, id: UUID) -> User:
    user = await self.crud.get(id=id)
    if not user:
        raise NotFound(f"사용자를 찾을 수 없습니다: {id}")
    return user

# ❌ 금지 패턴:
raise Exception("not found")          # ❌ bare Exception 금지
raise HTTPException(status_code=404)   # ❌ Service/CRUD 계층에서 HTTPException 금지
                                        #    (HTTPException은 Endpoint 계층에서만 허용)
```

### 에러 응답 포맷

```python
# 모든 에러는 아래 JSON 구조로 통일:
{
    "error": {
        "code": "NOT_FOUND",                    # 머신 리더블 코드
        "message": "사용자를 찾을 수 없습니다.",    # 사람이 읽는 메시지
        "detail": null                           # 추가 정보 (선택)
    },
    "meta": {
        "request_id": "uuid-string",
        "timestamp": "ISO 8601"
    }
}
```

---

## 7. 네이밍 컨벤션

| 대상 | 규칙 | 예시 | 반례 |
|------|------|------|------|
| 파일명 | `snake_case.py` | `user_service.py` | `UserService.py` |
| 클래스 | `PascalCase` | `UserService` | `user_service` |
| 함수/메서드 | `snake_case` | `get_user_by_email` | `getUserByEmail` |
| 상수 | `UPPER_SNAKE_CASE` | `JWT_ALGORITHM` | `jwtAlgorithm` |
| 환경 변수 | `UPPER_SNAKE_CASE` | `DATABASE_URL` | `database_url` |
| DB 테이블 | 복수형 `snake_case` | `users` | `User`, `user` |
| DB 컬럼 | `snake_case` | `created_at` | `createdAt` |
| API 경로 | 복수형 `kebab-case` | `/api/v1/users` | `/api/v1/user` |
| Pydantic 모델 | `PascalCase` + 접미사 | `UserCreate`, `UserResponse` | `CreateUser` |
| CRUD 클래스 | `CRUD` + 리소스명 | `CRUDUser` | `UserCrud` |

---

## 8. 파일 구조 규칙

### 모듈 독스트링

모든 Python 파일은 **모듈 독스트링**으로 시작합니다:

```python
"""
app/services/auth.py
~~~~~~~~~~~~~~~~~~~~
인증 비즈니스 로직.

OAuth2 Password Flow 기반 JWT 인증 서비스.
"""
```

### __init__.py 규칙

```python
# ✅ 패키지 진입점에 대표 클래스/함수만 re-export:
# app/crud/__init__.py
from app.crud.base import CRUDBase
from app.crud.user import crud_user

__all__ = ["CRUDBase", "crud_user"]

# ❌ 비어있는 __init__.py도 허용하지만, import 편의를 위해 re-export 권장
```

### 파일 길이

- 단일 파일 **300줄 이내** 권장
- 초과 시 기능별로 분리 (예: `user_service.py` → `user_service.py` + `user_validators.py`)

---

## 9. 보안 규칙

### 절대 금지 사항

| 항목 | 규칙 |
|------|------|
| 비밀번호 | 평문 저장/로깅 **절대 금지** |
| JWT Secret | 소스 코드에 하드코딩 **절대 금지** |
| SQL Injection | Raw SQL 사용 최소화, 파라미터 바인딩 필수 |
| 민감 정보 로깅 | password, token 등을 로그에 **절대 출력 금지** |
| 에러 메시지 | 내부 스택 트레이스를 클라이언트 응답에 **절대 노출 금지** |
| CORS | `"*"` (전체 허용) **프로덕션 금지** (개발 환경에서만 허용) |

### 인증 실패 응답

```python
# ✅ 어떤 것이 틀렸는지 구분하지 않음 (Timing Attack 방지):
raise Unauthorized("이메일 또는 비밀번호가 올바르지 않습니다.")

# ❌ 금지:
raise Unauthorized("이메일이 존재하지 않습니다.")     # ❌ 이메일 존재 여부 노출
raise Unauthorized("비밀번호가 틀렸습니다.")          # ❌ 이메일 유효성 노출
```

---

## 10. Git 컨벤션

### 커밋 메시지

[Conventional Commits](https://www.conventionalcommits.org/) 형식:

```
<type>(<scope>): <description>

feat(auth): JWT refresh token 로직 구현
fix(crud): 페이지네이션 off-by-one 에러 수정
refactor(core): Redis 연결 풀 초기화 개선
docs(readme): 빠른 시작 가이드 추가
test(auth): 로그인 실패 케이스 테스트 추가
chore(docker): Python 3.12 이미지로 업그레이드
```

| Type | 용도 |
|------|------|
| `feat` | 새 기능 |
| `fix` | 버그 수정 |
| `refactor` | 기능 변경 없는 코드 정리 |
| `docs` | 문서 변경 |
| `test` | 테스트 추가/수정 |
| `chore` | 빌드/환경 설정 변경 |

### .gitignore

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.venv/

# Environment
.env
!.env.example

# IDE
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db

# Test & Coverage
.pytest_cache/
htmlcov/
.coverage

# Caches
.mypy_cache/
.ruff_cache/
```

---

## 부록: Ruff 설정

```toml
# pyproject.toml 에 포함:
[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = [
    "E",    # pycodestyle errors
    "W",    # pycodestyle warnings
    "F",    # pyflakes
    "I",    # isort
    "N",    # pep8-naming
    "UP",   # pyupgrade (Python 3.11+ 패턴 강제)
    "B",    # flake8-bugbear
    "A",    # flake8-builtins
    "SIM",  # flake8-simplify
    "TCH",  # flake8-type-checking
    "RUF",  # ruff-specific rules
]
ignore = [
    "B008",  # Depends() in function args (FastAPI 패턴)
]

[tool.ruff.lint.isort]
known-first-party = ["app"]

[tool.ruff.format]
quote-style = "double"
```
