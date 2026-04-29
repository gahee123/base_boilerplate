"""
app/services/oidc/hmg_provider.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
HMG SSO 전용 OIDC 공급자 구현체.

HMG SSO 서버의 통신 프로토콜을 구현합니다.
각 단계의 요청/응답 규격은 Java(VTDM) 프로젝트의 실 서버 통신 방식을 참조했습니다.
보안 Healthcheck, PKCE(S256), RS256 서명 검증, AES-GCM 복호화,
인사 상태 에러 핸들링을 총괄합니다.
"""
import json
import logging
import urllib.parse
import uuid
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient

from app.models.enums import HmgSite
from app.services.oidc.base import BaseOIDCProvider, OIDCUserInfo
from app.utils.exceptions import Unauthorized
from app.utils.sso.crypto import hmg_crypto
from app.utils.sso.error_handler import HmgAuthorizeError, HmgHealthcheckError

logger = logging.getLogger(__name__)


class HMGOIDCProvider(BaseOIDCProvider):
    """
    HMG SSO 전용 OIDC 프로바이더.

    HMG SSO 서버의 통신 프로토콜을 구현합니다.
    규격 세부사항은 Java(VTDM) 프로젝트의 실 서버 검증 사례를 참조했습니다.
    - Healthcheck: 6개 필드 AES-GCM 암호화, text/plain 전송
    - Authorize: PKCE S256, scope=openid
    - Callback: RS256 + AES-GCM(info/iv) 중첩 구조 파싱
    """

    # HMG 전용 기본값 정의 (Enum 사용)
    DEFAULT_SITE = HmgSite.HAE
    DEFAULT_UPFORM = "N"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        base_url: str,
        site: str | None = None,
        upform: str | None = None,
    ):
        super().__init__(client_id, client_secret, redirect_uri)
        # base_url에 /SPI 경로가 포함된 것을 전제 (Java HmgUrlBuilder 방식)
        self.base_url = base_url.rstrip("/")

        # 주입된 값이 없으면 클래스 기본값(상수) 사용
        self.site = site or self.DEFAULT_SITE
        self.upform = upform or self.DEFAULT_UPFORM

        # 토큰 전자서명을 검증하기 위한 공개키(JWKS) Endpoint
        # Java: HmgUrlBuilder.Endpoints.CERT = "/cert"
        self.jwks_client = PyJWKClient(f"{self.base_url}/cert")

    # ── Healthcheck ───────────────────────────────────────────

    async def _health_check(
        self,
        state: str,
        client_ip: str,
        upform: str | None = None,
        site: str | None = None
    ) -> None:
        """
        로그인 URL 발급 전 HMG SSO와 백엔드 간 무결성 교차 검증.

        Java(VTDM) HmgSsoServiceImpl.performHealthcheck() 호환:
        - 6개 필드 (state, site, svc, back, upform, userip) 를 JSON 직렬화 후 AES-GCM 암호화
        - text/plain Content-Type 전송
        - 응답 본문 전체를 AES-GCM 복호화하여 결과 확인
        """
        # Java: HealthCheckEncryptedDataDto 구조 그대로
        encrypted_data = {
            "state": state,
            "site": site or self.site,
            "svc": self.client_id,
            "back": self.redirect_uri,
            "upform": upform or self.upform,
            "userip": client_ip,
        }

        logger.info("Healthcheck 요청 데이터: %s", encrypted_data)

        # Java: AES-GCM 암호화 → HealthCheckRequestDto { str, iv }
        json_data = json.dumps(encrypted_data, ensure_ascii=False)
        enc_str, enc_iv = hmg_crypto.encrypt(json_data)

        # Java: { "str": <암호문>, "iv": <IV> } — 필드명 주의 (data가 아닌 str)
        request_body = json.dumps({"str": enc_str, "iv": enc_iv})

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/healthcheck",
                    content=request_body,
                    headers={"Content-Type": "text/plain"},
                    timeout=5.0,
                )
            except httpx.RequestError as e:
                raise HmgHealthcheckError(5000) from e

        if resp.status_code != 200:
            raise HmgHealthcheckError(resp.status_code)

        # Java: 응답 본문 전체를 AES-GCM 복호화
        try:
            response_body = hmg_crypto.decrypt(resp.text, enc_iv)
            response_dto = json.loads(response_body)
        except Exception:
            # 복호화 실패 시 JSON 직접 파싱을 시도 (Mock SSO 등 비암호화 환경 대응)
            try:
                response_dto = resp.json()
            except Exception:
                raise HmgHealthcheckError(5000)

        logger.info("Healthcheck 응답: %s", response_dto)

        result = response_dto.get("result", False)
        status = response_dto.get("status")

        if not result:
            status_code = int(status) if status else 5000
            raise HmgHealthcheckError(status_code)

    # ── Authorize (Step 1) ────────────────────────────────────

    async def get_login_url(
        self,
        state: str,
        nonce: str,
        code_challenge: str,
        client_ip: str = "127.0.0.1",
        upform: str | None = None,
        site: str | None = None,
    ) -> str:
        """
        인가(Authorization) 1단계: Healthcheck 통과 후 리다이렉트 URL 조립.

        Java(VTDM) HmgSsoServiceImpl.generateAuthUrl() 호환.
        """
        # HMG 단독 로직: Healthcheck 선행
        # 메뉴얼: healthcheck에서 사용한 랜덤 세션값(state)을 authorize에서도 사용해야 함
        await self._health_check(
            state,
            client_ip,
            upform=upform,
            site=site
        )

        # Java: AuthorizeRequestDto → HmgUrlBuilder.buildAuthorizeUrl()
        params = {
            "state": state,
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": "openid",
            "response_type": "code",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        # Java 레퍼런스: nonce는 선택적
        if nonce:
            params["nonce"] = nonce

        query_string = urllib.parse.urlencode(params)
        return f"{self.base_url}/authorize?{query_string}"

    # ── Callback (Step 2) ─────────────────────────────────────

    async def process_callback(
        self,
        code: str,
        code_verifier: str,
        nonce: str,
        state: str = "",
    ) -> tuple[str, OIDCUserInfo]:
        """
        인가(Authorization) 2단계:
        1) Authorization Code → Token 요청 (PKCE 적용)
        2) ID Token 보안 서명 검증 (RS256, exp, iss, aud, nonce)
        3) AES-GCM 복호화 → Java JwtTokenDto 중첩 구조 파싱

        Java(VTDM) HmgSsoServiceImpl.processCallback() +
                   ProdJwtUtil.validateAndParseToken() 호환.
        """
        # --- 1) 토큰 요청 ---
        # Java: HmgSsoServiceImpl.requestToken()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                    "code_verifier": code_verifier,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10.0,
            )

        if resp.status_code != 200:
            error_data = resp.json()
            err_desc = error_data.get("error_description", "").upper()
            if err_desc:
                # Java: HmgErrorUtil.AuthorizeResponse — 인사 연계 에러 캐치
                raise HmgAuthorizeError(err_desc)
            raise Unauthorized("SSO 토큰 교환에 실패했습니다.")

        token_data = resp.json()
        id_token = token_data.get("id_token")
        if not id_token:
            raise Unauthorized("ID 토큰이 반환되지 않았습니다.")

        # --- 2) ID Token 디코딩 및 보안 서명 검증 ---
        # Java: ProdJwtUtil.validateAndParseToken()
        try:
            signing_key = self.jwks_client.get_signing_key_from_jwt(id_token)
            decoded_id_token = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.client_id,
                issuer=self.base_url,
                options={"verify_exp": True},
            )
        except jwt.ExpiredSignatureError:
            raise Unauthorized("SSO 세션 토큰이 만료되었습니다.")
        except jwt.InvalidTokenError:
            raise Unauthorized("위조되었거나 유효하지 않은 SSO 토큰입니다.")

        # Replay Attack 방지 (nonce 비교) — Java 레퍼런스에 없지만 Python이 더 안전
        if nonce and decoded_id_token.get("nonce") != nonce:
            raise Unauthorized(
                "Nonce 불일치: 재전송 공격(Replay Attack)이 감지되었습니다."
            )

        # --- 3) AES-GCM 페이로드 추출 ---
        # Java: ProdJwtUtil.extractUserInfo()
        # 필드명은 "info"와 "iv" (Java JwtPayloadDto 기준)
        user_info = self._extract_user_info(decoded_id_token)

        return id_token, user_info

    def _extract_user_info(self, decoded_id_token: dict[str, Any]) -> OIDCUserInfo:
        """
        Java ProdJwtUtil.extractUserInfo() 호환 — 중첩 구조 파싱.

        Java ID Token Payload 구조 (JwtTokenDto.JwtPayloadDto):
          - info: AES-GCM 암호화된 사용자/회사 정보 (문자열)
          - iv:   암호화 초기화 벡터
          - sub:  유니크 ID (longuserid)
          - uid:  실사번 (옵션)

        복호화 후 구조 (JwtTokenDto.UserInfoDto):
          - site:     회사코드 (H199_W 등)
          - sitename: 회사명
          - userid:   사번
          - userinfo (JwtTokenDto.UserDetailsDto):
              - displayName:      사용자명
              - mail:             이메일
              - userPrincipalName: AD UPN
              - objectGUID:       AD GUID
              - department:       팀명
              - departmentCode:   팀코드 (옵션)
        """
        enc_info = decoded_id_token.get("info")
        enc_iv = decoded_id_token.get("iv")

        email = ""
        employee_id = decoded_id_token.get("sub", "")
        full_name = ""
        department = ""
        department_code = ""
        site = ""

        if enc_info and enc_iv:
            try:
                decrypted_str = hmg_crypto.decrypt(enc_info, enc_iv)
                info_dto = json.loads(decrypted_str)

                # Java: UserInfoDto 최상위 필드
                site = info_dto.get("site", "")
                employee_id = info_dto.get("userid", employee_id)

                # Java: UserInfoDto.userinfo (UserDetailsDto) 중첩 구조
                user_details = info_dto.get("userinfo", {})
                if user_details:
                    full_name = user_details.get("displayName", "")
                    email = user_details.get("mail", "")
                    department = user_details.get("department", "")
                    department_code = user_details.get("departmentCode", "")

            except Exception:
                logger.warning(
                    "ID Token 내 info 필드 AES-GCM 복호화 실패 — "
                    "표준 claim 폴백 시도"
                )
                # 복호화 실패 시 표준 OIDC claim 폴백
                email = decoded_id_token.get("email", "")
                full_name = decoded_id_token.get("name", "")
        else:
            # info/iv가 없는 경우: 표준 OIDC claim 기반 동작 (개발 환경)
            email = decoded_id_token.get("email", "")
            full_name = decoded_id_token.get("name", "")

        # Java: payload.uid (실사번, 옵션)
        uid = decoded_id_token.get("uid")
        if uid:
            employee_id = uid

        # 이메일 폴백: mail이 없으면 site 기반 도메인 자동 생성
        # (Java ProdJwtAuthenticationFilter.getUserEmail() 참조)
        if not email and employee_id:
            email = self._generate_fallback_email(employee_id, site)

        # 이름 폴백: displayName이 없으면 userid 사용
        # (Java ProdJwtAuthenticationFilter.getUserName() 참조)
        if not full_name and employee_id:
            full_name = employee_id

        return OIDCUserInfo(
            email=email,
            employee_id=employee_id,
            full_name=full_name,
            department=department,
            department_code=department_code,
            site=site,
        )

    @staticmethod
    def _generate_fallback_email(employee_id: str, site: str) -> str:
        """
        mail 필드가 없을 때 site 기반으로 이메일을 자동 생성합니다.

        Java ProdJwtAuthenticationFilter.getUserEmail() 동일 로직:
          H101_W → @hyundai.com
          K101_W → @kia.com
          그 외  → @hyundai-autoever.com
        """
        domain_map = {
            "H101_W": "hyundai.com",
            "K101_W": "kia.com",
        }
        domain = domain_map.get(site, "hyundai-autoever.com")
        return f"{employee_id}@{domain}"
