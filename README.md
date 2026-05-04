# 🚀 FastAPI Enterprise Boilerplate

[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=flat&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-DC382D?style=flat&logo=redis&logoColor=white)](https://redis.io/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker&logoColor=white)](https://www.docker.com/)

엔터프라이즈 환경에서 즉시 사용 가능한 **고성능, 확장형 백엔드 보일러플레이트**입니다. 단순한 기능 나열을 넘어, 아키텍처적 유연성과 강력한 보안(SSO), 분석 도구(Superset) 연동을 핵심 가치로 제공합니다.

---

## 📐 아키텍처 활용 전략 (Architecture Strategy)
본 프로젝트의 기능들은 개발자가 비즈니스 요구사항에 따라 유연하게 확장할 수 있도록 세 가지 전략으로 제공됩니다.

*   **🏗️ [Base] (Interface/Inheritance)**: 표준 인터페이스와 기본 틀을 제공합니다. 상속을 통해 새로운 요구사항(예: 신규 SSO 공급자, 새로운 알림 채널)을 즉시 추가할 수 있습니다.
*   **📐 [Abstracted] (Hidden Logic)**: 복잡한 내부 로직은 추상화되어 있습니다. 개발자는 데코레이터(`@requires_role`, `@cached`)만으로 고급 기능을 즉시 누릴 수 있습니다.
*   **✅ [Implemented] (Ready-to-Use)**: 즉시 동작하는 완성형 모듈입니다. 설정값(`env`) 입력만으로 HMG SSO, Superset 연동, SSE 알림 엔진 등이 활성화됩니다.

---

## 🌟 핵심 기능 (Key Features)

### 🔐 인증 및 보안 (Enterprise Auth)
*   **HMG SSO**: 실제 동작이 검증된 HMG 전용 프로토콜(AES-GCM/RS256 + PKCE) 연동 완료.
*   **5단계 RBAC**: `superadmin`부터 `initial_lock`까지 세분화된 권한 제어 엔진.
*   **외부 시스템 인증**: 외부 시스템 호출을 위한 전용 API Key(Access/Secret) 발급 및 HMAC 서명 검증 체계.

### 📊 데이터 분석 및 모니터링 (BI & Observability)
*   **Superset JIT**: 사용자 로그인 시 Superset 계정 자동 생성 및 개인 대시보드 복제/매핑 기능.
*   **Audit Log**: 모든 DB 테이블의 변경 이력(Diff)을 자동 추적하여 기록하는 감사 시스템.
*   **PLG Stack**: Promtail + Loki + Grafana 기반의 구조화 로깅 및 시각화 인프라.

### 📡 실시간 알림 및 통신 (Notification Engine)
*   **SSE 실시간 엔진**: Redis Pub/Sub 기반으로 분산 서버 환경에서도 유저별 실시간 알림 스트리밍 지원.
*   **다채널 Factory**: Email, SMS, Push 등 다양한 알림 채널을 인터페이스 하나로 통합 관리.

---

## 🚀 빠른 시작 (Quick Start)

### 1. 환경 설정
```bash
# 의존성 설치
poetry install

# 환경 변수 설정
cp .env.example .env
# .env 내 HMG_SSO_*, SUPERSET_* 등의 필수 변수를 설정하세요.
```

### 2. 로컬 실행 (Docker Compose)
```bash
# Windows (PowerShell)
.\scripts\deploy_local.ps1

# Mac / Linux / WSL
make up
```

### 3. 접속 정보
*   **API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
*   **Health Check**: [http://localhost:8000/healthz/ready](http://localhost:8000/healthz/ready)

---

## 📘 핵심 문서 (Core Documentation)

프로젝트의 상세 사양은 새로 정리된 `docs` 폴더를 참조하세요.

*   [🛡️ 기능 감사 리포트 (달성도)](./docs/06_docs/feature_audit_report.md)
*   [✅ HMG SSO 검증 가이드](./docs/05_qa/hmg_sso_verification_guide.md)
*   [📊 로깅 아키텍처 설계](./docs/02_design/logging_architecture_plan.md)

---

## 📄 라이선스
본 프로젝트는 **MIT License**를 따릅니다.
