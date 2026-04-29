# 🚀 통합 로깅 아키텍처 (PLG Stack) 구축 보고서

> 생성일: 2026-04-23  
> 에이전트: Antigravity (Coding Assistant)  
> 커버 이슈: 중앙 집중식 구조화 로깅 시스템 구축

---

## 1. 개요
애플리케이션의 가시성(Observability)을 확보하고 분산 환경(API, Worker)에서의 트러블슈팅 효율을 높이기 위해 **structlog + Grafana Loki + Promtail + Grafana** 기반의 통합 로깅 인프라를 구축하였습니다.

---

## 2. 적용 기술 사양

| 구성 요소 | 기술 | 역할 |
|-----------|------|------|
| **Logging Library** | `structlog` | JSON 포맷의 구조화 로그 생성 및 컨텍스트 바인딩 |
| **Log Collector** | `Promtail` | 로그 파일 실시간 수집 및 라벨링 (Loki로 전송) |
| **Log Storage** | `Grafana Loki` | 인덱스 최적화 로그 저장소 (31일 보관 정책) |
| **Visualization** | `Grafana` | LogQL을 이용한 로그 검색 및 분석 대시보드 |

---

## 3. 주요 구현 내용

### 3.1 애플리케이션 계층 (Python)
- **서비스별 식별자 부여**: `setup_logging(service_name=...)` 기능을 추가하여 로그 발생 소스(api, worker)를 명확히 구분.
- **컨텍스트 바인딩**: `request_id`, `method`, `path`, `service` 등의 필드를 JSON 루트에 포함시켜 상관관계 추적 용이성 확보.
- **로그 분리 저장**: Docker 환경에서 API는 `app.log`, Worker는 `worker.log`에 각각 기록하여 파일 경합 방지.

### 3.2 인프라 계층 (Docker)
- **Loki 설정**: 로컬 파일 시스템 기반 저장소 및 데이터 보관 주기(Retention) 설정.
- **Promtail 파이프라인**: JSON 로그를 파싱하여 로그 내의 `level`과 `service` 필드를 Loki의 라벨로 변환하도록 설정.
- **Grafana 자동화**: 프로비저닝 설정을 통해 Loki 데이터 소스를 실행 시 자동으로 등록.

---

## 4. 로컬 실행 및 확인 방법

### 4.1 서비스 기동
```bash
docker-compose up -d
```

### 4.2 로그 확인 (Grafana)
1. `http://localhost:3000` 접속 (Anonymous 로그인 허용 설정됨).
2. 좌측 메뉴 **Explore** 선택.
3. 데이터 소스를 **Loki**로 선택.
4. `Log browser`에서 서비스별 확인 가능:
   - API 로그: `{job="fastapi", service="api"}`
   - Worker 로그: `{job="fastapi", service="worker"}`

---

## 5. 결론 및 향후 계획
이번 작업을 통해 구조화된 로깅 시스템의 기반을 마련했습니다. 향후 실제 운영 환경(K8s)에서는 배포 자동화 파이프라인(Helm)에 해당 스택을 통합하여 클러스터 수준의 Observability를 완성할 예정입니다.
