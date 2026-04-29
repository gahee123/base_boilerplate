# 🤖 FastAPI Boilerplate — 멀티 에이전트 워크플로 시스템

## 개요

이 디렉터리는 **FastAPI 백엔드 보일러플레이트**를 체계적으로 구축하기 위한 **역할별 AI 에이전트 정의 파일**을 포함합니다.  
각 에이전트는 특정 도메인에 대한 전문 지식과 워크플로를 갖추고 있으며, 순차적으로 호출하여 프로젝트를 완성합니다.

---

## 공통 문서

| 문서 | 파일 | 설명 |
|------|------|------|
| **코딩 컨벤션** | `rules/code-style-guide.md` | 모든 에이전트가 준수하는 코딩 규칙, 네이밍, 보안, Git 컨벤션 |

---

## 에이전트 구성

| 순서 | 에이전트 | 파일 | 역할 |
|:----:|----------|------|------|
| 1 | **PM / 기획** | `workflows/01_pm_planner.md` | 요구사항 분석, 태스크 분해, 일정 관리 |
| 2 | **아키텍트** | `workflows/02_architect.md` | 시스템 구조 설계, DB 스키마, API 규격 |
| 3 | **백엔드 개발** | `workflows/03_backend_dev.md` | FastAPI 핵심 코드 구현 |
| 4 | **인증/보안** | `workflows/04_auth_security.md` | JWT, RBAC, 암호화, 보안 미들웨어 |
| 5 | **DevOps** | `workflows/05_devops.md` | Docker, CI/CD, 환경 설정 |
| 6 | **QA/테스트** | `workflows/06_qa_testing.md` | 테스트 전략, Pytest 코드, 품질 검증 |
| 7 | **문서화/리뷰** | `workflows/07_docs_review.md` | API 문서, 코드 리뷰, README |

---

## 사용 방법

### 순차 워크플로 (권장)

```
1️⃣ PM 에이전트     → 요구사항 확정 & 태스크 분해
2️⃣ 아키텍트 에이전트 → 구조 설계 & 기술 명세
3️⃣ 백엔드 개발      → 핵심 코드 구현
4️⃣ 인증/보안        → Auth 모듈 전문 구현
5️⃣ DevOps          → 컨테이너 & 배포 환경
6️⃣ QA/테스트        → 테스트 코드 & 검증
7️⃣ 문서화/리뷰      → 최종 문서 & 코드 리뷰
```

### 에이전트 호출 방법

1. 대화에서 해당 에이전트 파일을 `@` 멘션하거나 첨부합니다
2. 에이전트의 지시사항을 읽고 해당 역할에 맞는 전문적인 응답을 제공합니다
3. 에이전트 간 산출물은 다음 에이전트의 입력으로 전달됩니다

---

## 대상 기술 스택

| 분류 | 기술 |
|------|------|
| Framework | FastAPI |
| ORM | SQLAlchemy 2.0 + Alembic |
| Auth | PyJWT + Passlib (bcrypt) |
| Validation | Pydantic v2 |
| Task Queue | Arq (Redis 기반) |
| Database | PostgreSQL + Redis |
| Container | Docker + Docker Compose |
| Env Mgmt | Poetry |

## 대상 프로젝트 구조

```
app/
├── api/               # API 엔드포인트 (v1, v2)
├── core/              # 공통 설정 (DB, Redis, JWT)
├── crud/              # 공통 CRUD 로직
├── models/            # SQLAlchemy DB 모델
├── schemas/           # Pydantic DTO
├── services/          # 비즈니스 로직
├── utils/             # 공통 유틸리티
└── main.py            # 앱 진입점
alembic/               # DB 마이그레이션
tests/                 # Pytest
pyproject.toml         # Poetry 의존성
docker-compose.yml     # 컨테이너 오케스트레이션
```
