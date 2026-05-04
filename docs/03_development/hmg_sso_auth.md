# 🔐 HMG SSO & Dual Token 인증 시스템 개발 가이드

## 1. 개요
본 프로젝트는 HMG SSO 연동을 기반으로 하며, 보안성과 사용자 경험을 모두 충족하기 위해 **Access Token (Response Body + HttpOnly Cookie) + Refresh Token (HttpOnly Cookie)** 전략을 채택하고 있습니다.

## 2. 인증 아키텍처 (Authentication Flow)

전체 인증 과정은 크게 3단계로 진행됩니다.

### Step 1: HMG SSO 로그인 및 신분 확인
1.  **로그인 시작**: 사용자가 `/auth/hmg/login` 호출.
2.  **Healthcheck**: 백엔드에서 HMG 서버로 사전 무결성 검증 수행.
3.  **PKCE 준비**: 백엔드가 `code_verifier` 생성 후 `code_challenge(S256)`를 HMG 인가 URL에 포함.
4.  **OIDC 인증**: 사용자가 HMG 로그인 페이지에서 인증 완료.
5.  **Callback**: HMG가 백엔드로 `code` 전달. 백엔드는 PKCE 및 nonce 검증 후 유저 정보로 교환하여 DB 동기화.
    *   **실패 시**: 프론트엔드로 리다이렉트하며 `?error={코드}&message={메시지}`를 포함합니다.

### Step 2: 내부 인증 코드(Auth Code) 발급
1.  **임시 코드 생성**: 백엔드는 유저 확인 후, 60초간 유효한 임시 `auth_code`를 생성하여 Redis에 저장.
2.  **FE 리다이렉트**: 프론트엔드 콜백 페이지로 리다이렉트 (예: `{FRONTEND_URL}/sso-callback?code={auth_code}`).

### Step 3: 최종 토큰 교환 및 세션 수립
1.  **토큰 교환**: 프론트엔드가 URL의 `code`를 추출하여 `POST /auth/token` 호출.
2.  **토큰 발급**:
    *   **Access Token**: API 응답 Body 및 `HttpOnly` 쿠키로 **동시에** 전달 (5분 수명).
    *   **Refresh Token**: `HttpOnly` 쿠키로 설정 (7일 수명).

## 3. API 상세 명세

### 3.1. 로그인 시작 (Login Initiation)
- **URL**: `GET /api/v1/auth/{provider}/login`
  - HMG SSO: `GET /api/v1/auth/hmg/login`
- **Query Parameters**:
  | 필드명 | 타입 | 필수 | 설명 | 값 예시 |
  | :--- | :--- | :--- | :--- | :--- |
  | **site** | string | Y | 대상 사이트(고객사) 코드 | `HMC`, `HAE`, `KMC`, `HKMC`, `ALL` |
  | **upform** | string | N | 업폼(양식) 적용 여부 (기본값: `N`) | `Y`, `N` |
- **Response**: `{ "login_url": "https://hmg-sso.../SPI/authorize?state=...&code_challenge=...&..." }`
- **Description**: HMG SSO 인증 페이지 URL을 반환합니다. Healthcheck를 수행하고 `state`, `nonce`, `code_verifier`를 Redis에 저장합니다.

### 3.2. 토큰 교환 (Token Exchange)
- **URL**: `POST /api/v1/auth/token`
- **Request Body**: `{ "code": "string" }`
- **Response**:
  ```json
  {
    "access_token": "eyJhbG...",
    "token_type": "bearer"
  }
  ```
- **Side Effect**:
  - `access_token` HttpOnly 쿠키 설정 (5분 수명)
  - `refresh_token` HttpOnly 쿠키 설정 (7일 수명)

### 3.3. 토큰 갱신 (Token Refresh)
- **URL**: `POST /api/v1/auth/refresh`
- **Cookie**: `refresh_token` (자동 전송)
- **Response**: `{ "access_token": "eyJhbG...", "token_type": "bearer" }`
- **Description**: Access Token 만료 시(401 에러) 호출. 쿠키의 Refresh Token을 사용하여 새로운 Access Token을 발급하며, **동시에 Refresh Token 쿠키도 7일로 다시 갱신**됩니다.

### 3.4. 내 정보 조회 (Get Me)
- **URL**: `GET /api/v1/users/me`
- **Header**: `Authorization: Bearer <access_token>`
- **Description**: 현재 로그인한 사용자의 프로필 정보를 반환.
  - 신규 가입 유저 (`PERMISSION_REQUIRED` 권한)는 `403 AUTH_007` 반환.

### 3.5. 로그아웃 (Logout)
- **URL**: `POST /api/v1/auth/logout`
- **Header 또는 Cookie**: `Authorization: Bearer <access_token>` 또는 `access_token` 쿠키
- **Description**: 서버 세션 무효화, 토큰 JTI를 Redis 블랙리스트에 등록, 모든 쿠키 삭제.
  - `Authorization` 헤더와 쿠키 중 하나만 있어도 정상 처리됩니다.

## 4. 보안 구현 상세

| 항목 | 구현 방식 | 목적 |
| :--- | :--- | :--- |
| **Healthcheck** | AES-GCM 암호화 통신 | HMG SSO 서버와 백엔드 간 사전 무결성 검증 |
| **PKCE (S256)** | `hashlib.sha256` + `base64url` 직접 구현 (RFC 7636) | Authorization Code 가로채기 방지 |
| **Nonce 검증** | Redis 저장 후 ID Token의 nonce와 대조 | Replay Attack (재사용 공격) 방지 |
| **Dual Token** | Access(Body+Cookie) + Refresh(HttpOnly Cookie) | XSS 및 CSRF 공격 동시 방어 |
| **Secret Key 분리** | `ACCESS_TOKEN_SECRET_KEY` / `REFRESH_TOKEN_SECRET_KEY` 독립 관리 | Refresh Token 탈취 시 Access Token 위조 불가 |
| **Redis 캐시** | 60s TTL Auth Code | 임시 코드의 일회성 및 단기성 보장 |
| **JTI 블랙리스트** | JTI 기반 Redis 저장 (잔여 만료시간 TTL) | 로그아웃된 토큰의 재사용 차단 |
| **세션 슬라이딩** | `session:{user_id}` Redis 키, 요청마다 TTL 갱신 | 비활동 세션 자동 만료 |

## 5. 프론트엔드 구현 가이드
1.  로그인 버튼 클릭 시 `/api/v1/auth/hmg/login?site={site}&upform=N` 호출 → `login_url` 획득 후 리다이렉트.
2.  HMG 인증 완료 후 백엔드 콜백 처리, 프론트엔드로 `{FRONTEND_URL}/sso-callback?code={code}` 리다이렉트.
3.  리다이렉트된 URL에서 `code` 쿼리 파라미터 추출.
4.  추출한 코드로 `POST /api/v1/auth/token` 요청 → `access_token` 획득.
5.  획득한 `access_token`은 전역 상태(Store) 혹은 변수에 저장 (HttpOnly 쿠키에도 자동 설정).
6.  모든 API 요청 헤더에 `Authorization: Bearer {access_token}` 포함.
7.  401 에러 발생 시 자동 인터셉터를 통해 `POST /api/v1/auth/refresh` 호출 시도.
8.  `403 AUTH_007` 응답 시 권한 요청 페이지로 이동.
