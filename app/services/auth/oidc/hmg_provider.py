import json
import logging
import urllib.parse

import httpx
import jwt
from uuid import uuid4
from jwt import PyJWKClient

from app.models.enums import HmgSite
from app.services.auth.oidc.base import BaseOIDCProvider, OIDCUserInfo
from app.utils.exceptions import Unauthorized
from app.services.auth.sso.crypto import hmg_crypto
from app.services.auth.sso.error_handler import HmgAuthorizeError, HmgHealthcheckError

logger = logging.getLogger(__name__)


class HMGOIDCProvider(BaseOIDCProvider):
    DEFAULT_SITE = HmgSite.HAE
    DEFAULT_UPFORM = "N"

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str, base_url: str, site: str | None = None, upform: str | None = None):
        super().__init__(client_id, client_secret, redirect_uri)
        self.base_url = base_url.rstrip("/")
        self.site = site or self.DEFAULT_SITE
        self.upform = upform or self.DEFAULT_UPFORM
        self.jwks_client = PyJWKClient(f"{self.base_url}/cert")

    async def _do_healthcheck_request(self, encrypted_data: dict) -> dict:
        json_data = json.dumps(encrypted_data, ensure_ascii=False)
        enc_str, enc_iv = hmg_crypto.encrypt(json_data)
        request_body = json.dumps({"str": enc_str, "iv": enc_iv})
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(f"{self.base_url}/healthcheck", content=request_body, headers={"Content-Type": "text/plain"}, timeout=5.0)
            except httpx.TimeoutException as e:
                raise HmgHealthcheckError(0) from e
            except httpx.RequestError as e:
                raise HmgHealthcheckError(5000) from e
        if resp.status_code != 200:
            raise HmgHealthcheckError(5000)
        try:
            response_body = hmg_crypto.decrypt(resp.text, enc_iv)
            return json.loads(response_body)
        except Exception:
            try:
                return resp.json()
            except Exception:
                raise HmgHealthcheckError(5000)

    async def _health_check(self, state: str, client_ip: str, upform: str | None = None, site: str | None = None) -> None:
        encrypted_data = {"state": state, "site": site or self.site, "svc": self.client_id, "back": self.redirect_uri, "upform": upform or self.upform, "userip": client_ip}
        response_dto = await self._do_healthcheck_request(encrypted_data)
        result = response_dto.get("result", False)
        sso_status_raw = response_dto.get("status")
        sso_status = int(sso_status_raw) if sso_status_raw else 5000
        if not result:
            if sso_status == 4000:
                encrypted_data["state"] = str(uuid4())
                retry_dto = await self._do_healthcheck_request(encrypted_data)
                if not retry_dto.get("result", False):
                    raise HmgHealthcheckError(4000)
                return
            raise HmgHealthcheckError(sso_status)

    async def get_login_url(self, state: str, nonce: str, code_challenge: str, client_ip: str = "127.0.0.1", upform: str | None = None, site: str | None = None) -> str:
        await self._health_check(state, client_ip, upform=upform, site=site)
        params = {"state": state, "client_id": self.client_id, "redirect_uri": self.redirect_uri, "scope": "openid", "response_type": "code", "code_challenge": code_challenge, "code_challenge_method": "S256"}
        if nonce:
            params["nonce"] = nonce
        return f"{self.base_url}/authorize?{urllib.parse.urlencode(params)}"

    async def process_callback(self, code: str, code_verifier: str, nonce: str, state: str = "") -> tuple[str, OIDCUserInfo]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.base_url}/token", data={"grant_type": "authorization_code", "client_id": self.client_id, "client_secret": self.client_secret, "code": code, "redirect_uri": self.redirect_uri, "code_verifier": code_verifier}, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=10.0)
        if resp.status_code != 200:
            error_data = resp.json()
            err_desc = error_data.get("error_description", "").upper()
            if err_desc:
                raise HmgAuthorizeError(err_desc)
            raise Unauthorized("SSO 토큰 교환에 실패했습니다.")
        token_data = resp.json()
        id_token = token_data.get("id_token")
        if not id_token:
            raise Unauthorized("ID 토큰이 반환되지 않았습니다.")
        try:
            signing_key = self.jwks_client.get_signing_key_from_jwt(id_token)
            decoded_id_token = jwt.decode(id_token, signing_key.key, algorithms=["RS256"], audience=self.client_id, issuer=self.base_url, options={"verify_exp": True})
        except jwt.ExpiredSignatureError:
            raise Unauthorized("SSO 세션 토큰이 만료되었습니다.")
        except jwt.InvalidTokenError:
            raise Unauthorized("유효하지 않은 SSO 토큰입니다.")
        if nonce and decoded_id_token.get("nonce") != nonce:
            raise Unauthorized("Nonce 불일치가 감지되었습니다.")
        user_info = self._extract_user_info(decoded_id_token)
        return id_token, user_info

    def _extract_user_info(self, decoded_id_token: dict) -> OIDCUserInfo:
        enc_info = decoded_id_token.get("info")
        enc_iv = decoded_id_token.get("iv")
        email, employee_id, full_name, department, department_code, site = "", decoded_id_token.get("sub", ""), "", "", "", ""
        if enc_info and enc_iv:
            try:
                decrypted_str = hmg_crypto.decrypt(enc_info, enc_iv)
                info_dto = json.loads(decrypted_str)
                site = info_dto.get("site", "")
                employee_id = info_dto.get("userid", employee_id)
                user_details = info_dto.get("userinfo", {})
                if user_details:
                    full_name = user_details.get("displayName", "")
                    email = user_details.get("mail", "")
                    department = user_details.get("department", "")
                    department_code = user_details.get("departmentCode", "")
            except Exception:
                email = decoded_id_token.get("email", "")
                full_name = decoded_id_token.get("name", "")
        else:
            email = decoded_id_token.get("email", "")
            full_name = decoded_id_token.get("name", "")
        uid = decoded_id_token.get("uid")
        if uid: employee_id = uid
        if not email and employee_id: email = self._generate_fallback_email(employee_id, site)
        if not full_name and employee_id: full_name = employee_id
        return OIDCUserInfo(email=email, employee_id=employee_id, full_name=full_name, department=department, department_code=department_code, site=site)

    @staticmethod
    def _generate_fallback_email(employee_id: str, site: str) -> str:
        domain_map = {"H101_W": "hyundai.com", "K101_W": "kia.com"}
        domain = domain_map.get(site, "hyundai-autoever.com")
        return f"{employee_id}@{domain}"
