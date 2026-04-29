import json
import time
import urllib.parse
from unittest.mock import patch, MagicMock

import jwt
import pytest
import respx
import redis.asyncio as aioredis
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User
from app.utils.sso.crypto import hmg_crypto

# RSA 키 생성
from cryptography.hazmat.primitives.asymmetric import rsa
PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC_KEY = PRIVATE_KEY.public_key()

@pytest.mark.asyncio
async def test_hmg_sso_full_flow_success(client: AsyncClient, db_session: AsyncSession, redis_setup):
    """
    [검증 항목 1, 2, 3] 로그인 시작 -> 콜백 -> 토큰 교환 성공 시나리오
    """
    mock_settings = {
        "HMG_SSO_BASE_URL": "http://mock-sso/SPI",
        "HMG_SSO_CLIENT_ID": "verify_svc",
        "HMG_SSO_CALLBACK_URI": "http://testserver/api/v1/auth/hmg/callback",
        "HMG_SSO_CIPHER_KEY": "0000000000000000000000000000000000000000000000000000000000000000"
    }
    
    with patch.multiple(settings, **mock_settings), \
         patch("app.services.oidc.hmg_provider.PyJWKClient.get_signing_key_from_jwt") as mock_key_grabber:
        
        mock_key_grabber.return_value = MagicMock(key=PUBLIC_KEY)
        
        with respx.mock(base_url="http://mock-sso/SPI", assert_all_called=False) as respx_mock:
            # Healthcheck Handler
            def healthcheck_handler(request):
                content = json.loads(request.content)
                req_iv = content.get("iv")
                enc_str, _ = hmg_crypto.encrypt(json.dumps({"result":True, "status":"200"}), iv_b64=req_iv)
                return Response(200, text=enc_str)
            respx_mock.post("/healthcheck").side_effect = healthcheck_handler

            # 1. 로그인 시작
            resp = await client.get("/api/v1/auth/hmg/login?site=HMC&upform=N")
            assert resp.status_code == 307
            
            target_url = resp.headers["location"]
            q_params = urllib.parse.parse_qs(urllib.parse.urlparse(target_url).query)
            state_val = q_params["state"][0]
            nonce_val = q_params["nonce"][0]

            # Token Exchange Handler
            def token_handler(request):
                user_dto = {"site":"HMC", "userid":"V123", "userinfo":{"displayName":"테스터", "mail":"v123@h.com"}}
                info_enc, iv_enc = hmg_crypto.encrypt_payload(user_dto)
                token = jwt.encode({
                    "iss":"http://mock-sso/SPI", "sub":"V123", "aud":"verify_svc", 
                    "exp":int(time.time())+60, "info":info_enc, "iv":iv_enc, "nonce": nonce_val
                }, PRIVATE_KEY, algorithm="RS256")
                return Response(200, json={"id_token": token, "access_token": "at"})
            respx_mock.post("/token").side_effect = token_handler

            # 2. 콜백 수신 (임시 코드 발급)
            resp = await client.get(f"/api/v1/auth/hmg/callback?code=mock_c&state={state_val}")
            assert resp.status_code == 307
            auth_code = urllib.parse.parse_qs(urllib.parse.urlparse(resp.headers["location"]).query)["code"][0]

            # 3. 토큰 교환
            token_resp = await client.post("/api/v1/auth/token", json={"code": auth_code})
            assert token_resp.status_code == 201
            data = token_resp.json()
            assert data["success"] is True
            assert "access_token" in data["data"]
            assert data["data"]["expires_in"] == 300
            assert "refresh_token" in token_resp.cookies

@pytest.mark.asyncio
async def test_hmg_sso_refresh_and_logout(client: AsyncClient, db_session: AsyncSession, redis_setup):
    """
    [검증 항목 4, 5] 토큰 갱신 및 로그아웃 시나리오
    """
    # 1. 먼저 로그인하여 토큰 획득
    # 유저 수동 생성 및 토큰 직접 발급 (테스트 속도 향상)
    user = User(email="test@example.com", employee_id="V999", full_name="세션테스터", is_active=True)
    db_session.add(user)
    await db_session.flush()
    
    from app.services.auth import auth_service
    tokens = auth_service.create_tokens(user)
    client.cookies.set("refresh_token", tokens["refresh_token"])

    # 2. 토큰 갱신 테스트
    refresh_resp = await client.post("/api/v1/auth/refresh")
    assert refresh_resp.status_code == 200
    response_data = refresh_resp.json()
    assert response_data["success"] is True
    assert "access_token" in response_data["data"]
    assert "refresh_token" in refresh_resp.cookies # 쿠키 갱신 확인

    # 3. 로그아웃 테스트
    logout_resp = await client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert logout_resp.status_code == 200
    assert "refresh_token" not in logout_resp.cookies or logout_resp.cookies.get("refresh_token") == ""

@pytest.mark.asyncio
async def test_hmg_sso_error_redirect(client: AsyncClient, redis_setup):
    """
    [검증 항목 6] 에러 발생 시 FE 리다이렉트 시나리오
    """
    with respx.mock(base_url="http://mock-sso/SPI") as respx_mock:
        # Healthcheck 실패 모사 (site=INVALID)
        def health_fail_handler(request):
            return Response(200, text=hmg_crypto.encrypt(json.dumps({"result":False, "status":"3000"}))[0])
        respx_mock.post("/healthcheck").side_effect = health_fail_handler

        resp = await client.get("/api/v1/auth/hmg/login?site=INVALID&upform=N")
        assert resp.status_code == 307
        location = resp.headers["location"]
        assert "error=INIT_FAILED" in location
        # HmgHealthcheckError 메시지가 유동적일 수 있으므로 INIT_FAILED 존재 여부를 주로 확인
