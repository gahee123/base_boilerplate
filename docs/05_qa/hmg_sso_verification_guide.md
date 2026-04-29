# HMG SSO 통합 인증 검증 가이드 (QA Guide)

본 문서는 HMG SSO(OIDC/PKCE) 연동 기능의 정상 작동 여부를 검증하기 위한 절차와 항목을 정의합니다.

## 1. 환경 구성 (Prerequisites)

검증을 진행하기 전 아래 서비스들이 정상 실행 중이어야 합니다.

- **FastAPI App**: 백엔드 API 서버 (포트 8000)
- **Redis**: SSO 세션(state, nonce) 및 인증 코드 관리
- **Mock SSO Server**: HMG SSO 실 서버를 대체하는 모의 서버 (포트 9092)
- **Database**: 유저 정보 동기화 확인용

### 로컬 실행 명령어
```powershell
# Docker Compose를 이용한 전체 스택 실행 (Mock SSO 포함)
wsl make up
```

---

## 2. 검증 항목 리스트 (Verification Checklist)

| 구분 | 검증 항목 | 기대 결과 | 중요도 |
| :--- | :--- | :--- | :---: |
| **로그인 시작** | Healthcheck 무결성 검증 | 백엔드와 SSO 서버 간 AES-GCM 암호화 통신 성공 | 필수 |
| | 인가 URL 리다이렉트 | `state`, `nonce`, `code_challenge` 포함 URL로 이동 | 필수 |
| **콜백 처리** | Authorization Code 교환 | SSO 서버로부터 ID Token 및 Access Token 정상 수신 | 필수 |
| | ID Token 서명 검증 | RS256 알고리즘 및 공개키(JWKS) 기반 위조 방지 확인 | 필수 |
| | 유저 정보 복호화 | ID Token 내 AES-GCM 암호화된 `info` 필드 파싱 성공 | 필수 |
| | 유저 DB 동기화 (Upsert) | 신규 가입 또는 기존 정보 업데이트 (부서/사이트 등) | 필수 |
| **보안 검증** | Replay Attack 방지 | 한 번 사용된 `state` 또는 `nonce` 재사용 시 차단 | 높음 |
| | PKCE 검증 | `code_verifier` 불일치 시 토큰 발급 차단 | 높음 |
| | 세션 만료 제어 | 로그인 시도 후 일정 시간(5분) 경과 시 콜백 차단 | 보통 |
| **최종 인증** | 내부 코드 교환 | 단기 코드를 Access(Body) / Refresh(Cookie)로 교환 | 필수 |
| **에러 케이스** | 유효하지 않은 사이트 | `site=INVALID` 요청 시 FE 에러 페이지 리다이렉트 | 보통 |
| | 인증 거부/취소 | 사용자가 SSO 페이지에서 취소 시 에러 처리 | 보통 |

---

## 3. 수동 검증 절차 (Manual Simulation)

프론트엔드 연동 전 백엔드 로직을 단독 검증할 때 아래 `curl` 절차를 따릅니다.

### Step 1: 로그인 진입 및 파라미터 획득
```powershell
# 사이트 코드(site)와 로그인 타입(upform)을 지정하여 호출
curl.exe -v "http://localhost:8000/api/v1/auth/hmg/login?site=HAE&upform=N"
```
- **체크포인트**: 응답 헤더 `location`에서 `state`와 `nonce` 값을 추출합니다.

### Step 2: 콜백 시뮬레이션 (Mock SSO 전용)
Mock SSO 서버는 `code` 값에 `nonce`를 포함시켜 전달해야 정상 작동합니다.
```powershell
# 추출한 state와 nonce를 대입
curl.exe -v "http://localhost:8000/api/v1/auth/hmg/callback?code=mock_code__{nonce}&state={state}"
```
- **체크포인트**: 응답 헤더 `location`에 `status=success`와 내부 인증용 `code`가 포함되었는지 확인합니다.

### Step 3: 최종 토큰 교환
```powershell
# Step 2에서 얻은 내부 code를 post body에 담아 호출
# (Windows PowerShell 환경에서는 따옴표 처리에 주의하세요)
wsl curl -v -X POST "http://localhost:8000/api/v1/auth/token" \
  -H "Content-Type: application/json" \
  -d '{"code": "{internal_code}"}'
```
- **체크포인트**: 
  - 응답 Body에 `access_token` 존재 확인
  - 응답 헤더 `set-cookie`에 `refresh_token` (HttpOnly) 존재 확인

---

## 4. 자동화 테스트 실행 (Automated Test)

CI/CD 또는 배포 전 회귀 테스트를 위해 아래 명령어를 실행합니다.

```powershell
# 컨테이너 내부에서 E2E 테스트 실행
wsl docker exec fastapi-app pytest tests/test_hmg_sso_e2e.py
```

---

## 5. 트러블슈팅 (Troubleshooting)

- **Nonce 불일치 에러**: Step 2 호출 시 `code` 파라미터에 `__` 구분자와 함께 실제 `nonce`를 넣었는지 확인하세요.
- **세션 만료 (SESSION_EXPIRED)**: 동일한 `state`로 콜백을 두 번 요청하면 보안 정책상 세션이 삭제됩니다. Step 1부터 다시 진행하세요.
- **DB Not Null 제약 위반**: `User` 모델에 필수 컬럼(email 등)이 추가되었습니다. 테스트 데이터 생성 시 누락되지 않도록 주의하세요.
