# HMG SSO 통합 인증 검증 가이드 (QA Guide)

본 문서는 HMG SSO(OIDC/PKCE) 연동 기능의 정상 작동 여부를 검증하기 위한 절차와 항목을 정의합니다.

---

## 1. 환경 구성 (Prerequisites)

검증을 진행하기 전 아래 서비스들이 정상 실행 중이어야 합니다.

- **FastAPI App**: 백엔드 API 서버 (포트 8000)
- **Redis**: SSO 세션(state, nonce, code_verifier) 및 인증 코드 관리
- **Mock SSO Server**: HMG SSO 실 서버를 대체하는 모의 서버 (포트 9092)
- **Database**: 유저 정보 동기화 확인용

```powershell
# Docker Compose를 이용한 전체 스택 실행 (Mock SSO 포함)
wsl make up
```

> **WSL IP 확인**: Windows 호스트에서 직접 `localhost:8000`에 접근이 안 되는 경우,
> `wsl hostname -I` 명령으로 WSL IP를 확인하여 `scratch/test_sso_flow.py`의 `BASE_URL`에 반영하세요.

---

## 2. 검증 항목 리스트 (Verification Checklist)

| 구분 | 검증 항목 | 기대 결과 | 중요도 |
| :--- | :--- | :--- | :---: |
| **로그인 시작** | Healthcheck 무결성 검증 | 백엔드와 SSO 서버 간 AES-GCM 암호화 통신 성공 | 필수 |
| | 인가 URL 파라미터 검증 | `state`, `nonce`, `code_challenge(S256)` 포함 URL 반환 | 필수 |
| **콜백 처리** | Authorization Code 교환 | SSO 서버로부터 ID Token 정상 수신 후 내부 코드 발급 | 필수 |
| | ID Token 서명 검증 | RS256 알고리즘 및 공개키(JWKS) 기반 위조 방지 확인 | 필수 |
| | 유저 정보 복호화 | ID Token 내 AES-GCM 암호화된 `info` 필드 파싱 성공 | 필수 |
| | 유저 DB 동기화 (Upsert) | 신규 가입 또는 기존 정보 업데이트 (부서/사이트 등) | 필수 |
| **보안 검증** | Replay Attack 방지 | 한 번 사용된 `state` 재사용 시 `INVALID_STATE` 에러 리다이렉트 | 높음 |
| | PKCE 검증 | 잘못된 code 사용 시 `AUTH_FAILED` 에러 리다이렉트 | 높음 |
| **최종 인증** | 내부 코드 교환 | 단기 코드를 Access Token(Body) / Refresh Token(HttpOnly Cookie)으로 교환 | 필수 |
| | Access Token 검증 | 발급된 토큰으로 보호 API 인증 통과 | 필수 |
| | Refresh Token 갱신 | Refresh Token으로 새 Access Token 발급 및 토큰 교체 확인 | 필수 |
| | 로그아웃 + 블랙리스트 | 로그아웃 후 기존 토큰 재사용 시 401 차단 | 필수 |
| **에러 케이스** | 유효하지 않은 state | 존재하지 않는 state로 콜백 시 `INVALID_STATE` 에러 리다이렉트 | 높음 |

---

## 3. 검증 방법 (두 가지)

### 방법 A. 통합 검증 스크립트 (`scratch/test_sso_flow.py`)

실제 실행 중인 도커 스택에 HTTP 요청을 보내 **전체 플로우를 엔드-투-엔드로 검증**합니다.
QA 가이드 체크리스트의 모든 항목을 자동으로 검증하며 결과를 출력합니다.

```powershell
# WSL IP 확인 (필요시)
wsl hostname -I

# scratch/test_sso_flow.py 상단의 BASE_URL을 WSL IP로 설정 후 실행
$env:PYTHONIOENCODING='utf-8'; python scratch/test_sso_flow.py
```

**검증 항목 (28건)**

| 구분 | 검증 항목 |
| :--- | :--- |
| [1] 로그인 시작 | HTTP 200, login_url, state/nonce/code_challenge(S256) 포함, Healthcheck 통과 |
| [2] 콜백 처리 | 307 리다이렉트, 내부 코드 발급, RS256·AES-GCM·DB 동기화 (콜백 성공 전제) |
| [3] 보안 검증 | Replay Attack 차단, PKCE 검증 (nonce 불일치 차단) |
| [4] 최종 인증 | Access Token(Body) + Refresh Token(HttpOnly Cookie) 발급 |
| [5] Access Token | 서명 검증 통과 (401 아님 확인) |
| [6] Refresh | 새 토큰 발급 및 토큰 갱신 확인 |
| [7] 로그아웃 | 블랙리스트 JTI 등록 + 재접근 401 차단 |
| [8] 에러 케이스 | 유효하지 않은 state 에러 리다이렉트 |

**최신 실행 결과**: `총 28건 중 ✅ 28건 통과 / ❌ 0건 실패`

---

### 방법 B. pytest E2E 자동화 테스트 (`tests/test_hmg_sso_e2e.py`)

외부 서버 없이 **pytest + respx Mock**으로 격리된 환경에서 실행하는 회귀 테스트입니다.
CI/CD 파이프라인 또는 배포 전 회귀 검증에 사용합니다.

```powershell
# 컨테이너 내부에서 E2E 테스트 실행
wsl docker exec fastapi-app poetry run pytest tests/test_hmg_sso_e2e.py -v
```

**테스트 케이스 (2건)**

| 테스트 함수 | 검증 내용 |
| :--- | :--- |
| `test_hmg_sso_full_flow_success` | 로그인 시작 → SSO 콜백 → 토큰 교환 전체 플로우 (respx Mock 사용, RS256 서명 포함) |
| `test_hmg_sso_refresh_and_logout` | Refresh Token 갱신 + 로그아웃 후 쿠키 삭제 확인 |

**최신 실행 결과**: `2 passed, 1 warning in 0.23s`

> **참고**: `1 warning`은 `passlib`의 Python 3.13 deprecated 경고로 기능에는 영향 없음.

---

## 4. 두 검증 방법 비교

| 구분 | `scratch/test_sso_flow.py` | `tests/test_hmg_sso_e2e.py` |
| :--- | :--- | :--- |
| **실행 대상** | 실제 실행 중인 도커 서버 | pytest 인메모리 가상 서버 |
| **SSO 서버** | 실제 `mock-hmg-sso` 컨테이너(포트 9092) | `respx`로 HTTP 요청 인터셉트 |
| **DB / Redis** | 실제 PostgreSQL, Redis 컨테이너 | `conftest.py` 픽스처 (트랜잭션 롤백) |
| **외부 의존성** | 도커 스택 전체 필요 | 불필요 |
| **용도** | 배포 후 헬스체크, QA 시나리오 전체 검증 | CI/CD 회귀 방지, PR 검증 |
| **실행 환경** | Windows PowerShell (Python 필요) | `fastapi-app` 컨테이너 내부 |

---

## 5. 트러블슈팅 (Troubleshooting)

- **`localhost:8000` 연결 거부**: Windows 호스트에서 WSL Docker에 직접 접근이 안 될 수 있습니다.
  `wsl hostname -I`로 WSL IP를 확인하고 `scratch/test_sso_flow.py`의 `BASE_URL`을 해당 IP로 변경하세요.

- **Nonce 불일치 에러**: `sso_state:{state}` Redis 키에 저장된 nonce와 Mock SSO가 code에 담아 보낸 nonce가 일치해야 합니다.
  수동 테스트 시 Step 2의 `code=mock_code__{nonce}`에 실제 nonce 값을 정확히 대입하세요.

- **세션 만료 (INVALID_STATE)**: 동일한 `state`로 콜백을 두 번 요청하면 보안 정책상 세션이 삭제됩니다.
  Step 1부터 새 `state`를 발급받아 다시 진행하세요.

- **Logout 401**: `get_current_user`에서 Redis `session:{user_id}` 키가 없으면 401이 반환됩니다.
  테스트에서 직접 유저를 생성하는 경우 `auth_service.activate_session(redis, user_id)`를 반드시 호출해야 합니다.

- **pytest Exit code 1 (WSL 환경)**: `wsl docker exec ... poetry run pytest` 실행 시 PowerShell이 WSL의
  `Skipping virtualenv creation` stderr를 에러로 처리합니다. pytest 자체 결과(`passed/failed`)만 확인하면 됩니다.
