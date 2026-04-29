# 🔐 HMG SSO & Dual Token 인증 시스템 개발 가이드

## 1. 개요
본 프로젝트는 HMG SSO 연동을 기반으로 하며, 보안성과 사용자 경험을 모두 충족하기 위해 **Access Token (In-Memory) + Refresh Token (HttpOnly Cookie)** 전략을 채택하고 있습니다.

## 2. 인증 아키텍처 (Authentication Flow)

전체 인증 과정은 크게 3단계로 진행됩니다.

### Step 1: HMG SSO 로그인 및 신분 확인
1.  **로그인 시작**: 사용자가 `/auth/hmg/login` 호출.
2.  **Healthcheck**: 백엔드에서 HMG 서버로 사전 무결성 검증 수행.
3.  **OIDC 인증**: 사용자가 HMG 로그인 페이지에서 인증 완료.
4.  **Callback**: HMG가 백엔드로 `code` 전달. 백엔드는 이를 유저 정보로 교환 후 DB 동기화.
    *   **실패 시**: 프론트엔드로 리다이렉트하며 `?error={코드}&message={메시지}`를 포함합니다.

### Step 2: 내부 인증 코드(Auth Code) 발급
1.  **임시 코드 생성**: 백엔드는 유저 확인 후, 60초간 유효한 임시 `auth_code`를 생성하여 Redis에 저장.
2.  **FE 리다이렉트**: 프론트엔드 콜백 페이지로 리다이렉트 (예: `/callback?code=UUID`).

### Step 3: 최종 토큰 교환 및 세션 수립
1.  **토큰 교환**: 프론트엔드가 URL의 `code`를 추출하여 `POST /auth/token` 호출.
2.  **토큰 발급**: 
    *   **Access Token**: API 응답 Body로 전달 (5분 수명).
    *   **Refresh Token**: `HttpOnly` 쿠키로 설정 (7일 수명).

## 3. API 상세 명세

### 3.1. 로그인 시작 (Login Initiation)
- **URL**: `GET /api/v1/auth/hmg/login`
- **Query Parameters**:
  | 필드명 | 타입 | 필수 | 설명 | 값 예시 |
  | :--- | :--- | :--- | :--- | :--- |
  | **site** | string | Y | 대상 사이트(고객사) 코드 | `HMC`, `HAE`, `KMC`, `HKMC`, `ALL` |
  | **upform** | string | Y | 업폼(양식) 적용 여부 | `Y`, `N` |
- **Description**: HMG SSO 인증 페이지로 리다이렉트하기 전, Healthcheck를 수행하고 인증 세션을 생성합니다.

### 3.2. 토큰 교환 (Token Exchange)
- **URL**: `POST /api/v1/auth/token`
- **Request Body**: `{ "code": "string" }`
- **Response**: 
  ```json
  {
    "access_token": "eyJhbG...",
    "token_type": "Bearer",
    "expires_in": 300
  }
  ```
- **Side Effect**: `refresh_token` 쿠키 설정 (7일 수명).

### 3.2. 토큰 갱신 (Token Refresh)
- **URL**: `POST /api/v1/auth/refresh`
- **Description**: Access Token 만료 시(401 에러) 호출. 쿠키의 Refresh Token을 사용하여 새로운 Access Token을 발급하며, **동시에 Refresh Token 쿠키도 7일로 다시 갱신**됩니다.

### 3.3. 내 정보 조회 (Get Me)
- **URL**: `GET /api/v1/auth/me`
- **Header**: `Authorization: Bearer <access_token>`
- **Description**: 현재 로그인한 사용자의 프로필 정보를 반환.

### 3.4. 로그아웃 (Logout)
- **URL**: `POST /api/v1/auth/logout`
- **Description**: 서버 세션 무효화, 토큰 블랙리스트 등록 및 모든 쿠키 삭제.

## 4. 보안 구현 상세

| 항목 | 구현 방식 | 목적 |
| :--- | :--- | :--- |
| **Healthcheck** | AES-GCM 암호화 통신 | HMG SSO 서버와 백엔드 간 사전 무결성 검증 |
| **PKCE (S256)** | Code Challenge/Verifier | Authorization Code 가로채기 방지 |
| **Dual Token** | In-Memory + HttpOnly Cookie | XSS 및 CSRF 공격 동시 방어 |
| **Redis 캐시** | 60s TTL Auth Code | 임시 코드의 일회성 및 단기성 보장 |
| **블랙리스트** | JTI 기반 Redis 저장 | 로그아웃된 토큰의 재사용 차단 |

## 5. 프론트엔드 구현 가이드
1.  로그인 버튼 클릭 시 `/api/v1/auth/hmg/login`으로 페이지 이동.
2.  리다이렉트된 URL에서 `code` 쿼리 파라미터 추출.
3.  추출한 코드로 `/api/v1/auth/token` 요청을 보내 `access_token` 획득.
4.  획득한 `access_token`은 전역 상태(Store) 혹은 변수에 저장.
5.  모든 API 요청 헤더에 `Authorization: Bearer {token}` 포함.
6.  401 에러 발생 시 자동 인터셉터를 통해 `/auth/refresh` 호출 시도.
