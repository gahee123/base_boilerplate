# 🔐 HMG SSO 보안 및 에러 핸들링 유틸리티 산출물 보고서

> 생성일: 2026-04-24  
> 최종 수정: 2026-04-24 (Java(VTDM) 레퍼런스 정합성 보정 반영)  
> 커버 영역: HMG SSO 연동 Part 2 (보안 통신 인프라 확립)

---

## 1. 신규 구축 시스템 개요

HMG SSO의 Healthcheck API 및 인가(Authorize) 통신 과정에서 필수적으로 요구되는 **종단 간 암호화(E2E Encryption)** 계층과 **비즈니스 에러 통제** 계층을 성공적으로 도입하였습니다.

> **2026-04-24 업데이트**: 실제 HMG SSO 서버와 연동 검증된 Java(VTDM) 프로젝트(`docs/sso_reference_java_project/vtdm/`)를 참고하여 전면 정합성 보정을 실시했습니다. Java 코드가 실 SSO 서버 통신에서 사용한 암호화 규격, 페이로드 구조, ID Token 파싱 구조를 근거로 **HMG SSO 서버가 요구하는 프로토콜**에 맞추었습니다.

| 분류 | 파일명 | 역할 및 목적 |
|------|--------|--------------|
| **암복호화 (보안)** | `app/utils/sso/crypto.py` | AES-256-GCM 알고리즘 기반 양방향 암호화 — **HMG SSO 서버 암호화 규격 준수** (Java 검증 사례 참조) |
| **에러 통제 (UX)** | `app/utils/sso/error_handler.py` | 헬스체크 및 인사 권한 오류 상태 — **HMG SSO 에러 코드 체계 반영** (Java 구현 참조) |

---

## 2. 모듈 세부 명세서

### 2.1. `app/utils/sso/crypto.py` — AES-GCM 보안 유틸리티

**HMG SSO 서버가 요구하는 AES-256-GCM 암복호화 규격**을 준수한 클래스입니다. 규격 세부사항은 Java(VTDM) 프로젝트의 `AESGCMCipher.java`가 실 서버 통신에서 사용한 방식을 근거로 도출했습니다.

* **라이브러리**: `cryptography` 라이브러리의 `AESGCM` 프리미티브 사용.
* **Key 포맷**: `.env`에 등록된 `HMG_SSO_CIPHER_KEY`를 **64자 Hex 문자열**로 파싱하여 32바이트 AES-256 키를 생성합니다.
  * HMG SSO 규격: 정규식 `^[0-9a-f]{64}$` 검증 적용.
* **IV(초기화 벡터)**: **16바이트** (`GCM_IV_LENGTH = 16`) 사용.
* **Base64**: **URL-safe** 인코딩.
* **암호문 포맷**: Java 방식 `IV + Ciphertext` 결합 후 단일 인코딩.
  * `encrypt()`: IV(16) + Ciphertext를 결합하여 URL-safe Base64로 반환.
  * `decrypt()`: 결합된 데이터에서 앞 16바이트 IV를 분리 후 나머지를 복호화.
* **dict 편의 래퍼**: `encrypt_payload(dict)`, `decrypt_payload(str, str)` 유지하여 기존 인터페이스 호환.

### 2.2. `app/utils/sso/error_handler.py` — 전용 에러 핸들러

HMG SSO 서버가 반환하는 에러 코드 체계를 반영했습니다. 에러 코드 목록은 Java(VTDM) 프로젝트의 `HmgErrorUtil.java` 및 `HmgSsoServiceImpl.java`에서 참조했습니다.

* **`HmgHealthcheckError` 클래스**:
  * HMG SSO Healthcheck 응답 에러 코드 매핑 (Java 검증 사례 참조):
    `2000`(파라미터 없음), `2100`(필수 파라미터 누락), `3000`(등록되지 않은 회사), `3100`(등록되지 않은 서비스), `3200`(등록되지 않은 redirect_uri), `3300`(서비스에 연동되지 않은 회사), `4000`(사용된 state), `5000`(알 수 없는 오류).

* **`HmgAuthorizeError` 클래스**:
  * HMG SSO Authorize 에러 타입 전체 반영 (Java 검증 사례 참조):
    * `INVALID_REQUEST`, `UNSUPPORTED_RESPONSE_TYPE`, `INVALID_SCOPE`, `UNAUTHORIZED_CLIENT` → HTTP 400
    * `ACCESS_DENIED` 세부 사유 (HMG 인사 상태 코드):
      * `HEALTHCHECK NOT DONE` → HTTP 401
      * `BLOCKED` → HTTP 403 (권한 없는 사용자)
      * `RETIRED` → HTTP 403 (퇴직 처리)
      * `SUSPENDED` → HTTP 403 (정직 상태)
      * `REST` → HTTP 403 (휴직 중)
      * `EXPIRED` → HTTP 401 (비밀번호 만료)

### 2.3. `app/services/oidc/hmg_provider.py` — HMG OIDC 통신 엔진

HMG SSO 서버가 요구하는 OIDC 통신 프로토콜을 구현한 모듈입니다. 각 단계의 요청/응답 규격은 Java(VTDM)의 `HmgSsoServiceImpl.java` + `ProdJwtUtil.java`에서 실 서버 통신으로 검증된 방식을 참조했습니다.

* **비동기 I/O**: `httpx.AsyncClient`를 도입해 모든 Rest API 호출 시 Event Loop Blocking 0% 달성.
* **Healthcheck (HMG SSO 규격)**:
  * 암호화 대상 데이터: `state`, `site`, `svc`, `back`, `upform`, `userip` — 6개 필드
  * Content-Type: `text/plain`
  * 요청 body 필드명: `str`, `iv`
  * 응답 처리: body 전체를 AES-GCM 복호화 후 결과 파싱
* **Authorize URL 생성**:
  * PKCE S256 코드 챌린지 적용
  * scope: `openid`
  * nonce: 선택적
* **Token 교환**:
  * `application/x-www-form-urlencoded` Content-Type
  * 6개 파라미터: `code`, `client_id`, `client_secret`, `redirect_uri`, `grant_type`, `code_verifier`
* **ID Token 검증**:
  * RS256 서명 검증 (JWKS endpoint: `{base_url}/cert`)
  * 만료 시간(exp), 발급자(iss), 대상(aud) 검증
  * **추가 보안**: `nonce` 검증 (Replay Attack 방지)
* **사용자 정보 추출 (HMG SSO 토큰 구조)**:
  * ID Token payload 내 `info`/`iv` 필드에서 AES-GCM 복호화
  * 복호화 후 **중첩 구조** 파싱: `site`, `userid`, `userinfo.mail`, `userinfo.displayName` 등
  * `uid` (실사번, 옵션) 지원

### 2.4. 통합 인증 라우터 및 비즈니스 연동

로컬 패스워드 인증을 과감히 폐기하고, HMG PKCE 챌린지 및 화이트리스트 동기화 모듈로 개편했습니다.

* **Client IP 추출**:
  * `X-Forwarded-For`, `X-Real-IP` 헤더 대응
  * IPv6 루프백 (`::1`) → IPv4 (`127.0.0.1`) 변환
* **Callback 에러 처리 (HMG SSO 에러 파라미터 규격)**:
  * `error`, `error_description` 쿼리 파라미터 수신
  * `_parse_error_message()` — HMG 인사 상태별 메시지 파싱
  * 에러 시 프론트엔드 `?status=fail&message=...` 리다이렉트
* **`sso_sync_user` (유저 자동 등록/동기화)**:
  * `department_code` 기반 `UserGroup` 조회
  * 화이트리스트 팀이면 `USER`, 아니면 `PERMISSION_REQUIRED` 등급 부여
* **Redis PKCE 방어**:
  * `state`, `code_challenge`, `code_verifier`, `nonce` 4대 보안 키워드를 `os.urandom(32)` 기반으로 생성
  * Redis(TTL 300초) 캐시에 보관, 콜백 수신 시 소비 후 즉시 파괴
* **HttpOnly 쿠키 + 로그아웃**:
  * `access_token` (자체 JWT) + `id_token_hint` (HMG 토큰) 쿠키 동시 삽입
  * 로그아웃 시: Redis 블랙리스트 등재 + 쿠키 삭제 + `hmg_logout_url` 반환

### 2.5. HMG SSO 연동 시 추가 적용한 보안 강화 기능

| 기능 | 구현 방식 | 의의 |
|------|----------|------|
| `audience` 검증 | JWT `aud` 클레임 대조 | 토큰 대상 서비스 확인 |
| `nonce` 검증 | Redis state에 저장 후 대조 | Replay Attack 방지 |
| Redis 토큰 블랙리스트 | `jti` 기반 TTL 등재 | 로그아웃 후 토큰 재사용 차단 |
| 자체 JWT 전략 | Callback 시 1회만 HMG 검증, 이후 자체 JWT 사용 | 요청당 RS256+AES-GCM 부하 제거 |

---

## 3. 환경변수 종합 명세

| 환경변수 | 형식 | 설명 | 예시 |
|---------|------|------|------|
| `HMG_SSO_BASE_URL` | URL (끝에 `/SPI` 포함) | HMG SSO 기본 URL | `https://scaportal.hmg-corp.io/SPI` |
| `HMG_SSO_CLIENT_ID` | 문자열 | 서비스코드 | `your_client_id` |
| `HMG_SSO_CLIENT_SECRET` | 문자열 | 서비스 PW | `your_client_secret` |
| `HMG_SSO_CIPHER_KEY` | 64자 Hex 문자열 | AES-256-GCM 키 | `0a1b2c3d...` (64자) |
| `HMG_SSO_CALLBACK_URI` | URL | 인증 완료 후 리턴 URL | `https://yourdomain.com/api/v1/auth/hmg-sso/callback` |
| `HMG_SSO_FRONTEND_LOGIN_CALLBACK_URL` | URL | 로그인 성공 시 프론트엔드 리다이렉트 | `https://yourdomain.com/dashboard` |
| `HMG_SSO_POST_LOGOUT_REDIRECT_URI` | URL | 로그아웃 후 리다이렉트 | `https://yourdomain.com` |
| `HMG_SSO_SITE_CODE` | 문자열 | 회사코드 | `H199_W` (현대오토에버) |
| `HMG_SSO_LOGIN_TYPE` | `simple` 또는 `manual` | 로그인 방식 | `simple` |
| `LOGIN_SESSION_TIMEOUT_MINUTES` | 정수 | 세션 유효 시간 (분) | `30` |
