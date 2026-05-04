import json
import time
import urllib.parse
from unittest.mock import patch, MagicMock

import jwt
import pytest
import respx
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis import get_redis
from app.models.user import User, UserRole
from app.services.auth.sso.crypto import hmg_crypto

# RSA 키 생성
from cryptography.hazmat.primitives.asymmetric import rsa
PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC_KEY = PRIVATE_KEY.public_key()

@pytest.mark.asyncio
async def test_hmg_sso_full_flow_success(client: AsyncClient, db_session: AsyncSession, redis_setup):
    """
    로그인 시작 -> 콜백 -> 토큰 교환 성공 시나리오
    """
    mock_settings = {
        "HMG_SSO_BASE_URL": "http://mock-sso/SPI",
        "HMG_SSO_CLIENT_ID": "verify_svc",
        "HMG_SSO_CALLBACK_URI": "http://testserver/api/v1/auth/hmg/callback",
        "HMG_SSO_CIPHER_KEY": "0000000000000000000000000000000000000000000000000000000000000000"
    }
    
    with patch.multiple(settings, **mock_settings), \
         patch("app.services.auth.oidc.hmg_provider.PyJWKClient.get_signing_key_from_jwt") as mock_key_grabber:
        
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
            assert resp.status_code == 200 # RedirectResponse가 아닌 JSON 반환 구조로 변경됨 (최신 코드 기준)
            data = resp.json()
            assert "login_url" in data
            
            target_url = data["login_url"]
            q_params = urllib.parse.parse_qs(urllib.parse.urlparse(target_url).query)
            state_val = q_params["state"][0]
            nonce_val = q_params["nonce"][0]

            # Token Exchange Handler
            def token_handler(request):
                user_dto = {"site":"HMC", "userid":"V123", "userinfo":{"displayName":"테스터", "mail":"v123@h.com"}}
                info_enc, iv_enc = hmg_crypto.encrypt(json.dumps(user_dto))
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
            assert token_resp.status_code == 200
            data = token_resp.json()
            assert "access_token" in data
            assert data["token_type"] == "bearer"
            assert "refresh_token" in token_resp.cookies

@pytest.mark.asyncio
async def test_hmg_sso_refresh_and_logout(client: AsyncClient, db_session: AsyncSession, redis_setup):
    """
    토큰 갱신 및 로그아웃 시나리오
    """
    user = User(
        email="test@example.com",
        employee_id="V999",
        full_name="세션테스터",
        is_active=True,
        role=UserRole.USER,  # 명시적 role 지정 (기본값 PERMISSION_REQUIRED 방지)
    )
    db_session.add(user)
    await db_session.flush()

    from app.services.auth.service import auth_service
    tokens = auth_service.create_tokens(user)

    # Redis 세션 활성화 (get_current_user의 touch_session 통과를 위해 필수)
    redis = await get_redis()
    await auth_service.activate_session(redis, str(user.id))

    client.cookies.set("refresh_token", tokens["refresh_token"])

    # 1. 토큰 갱신 테스트
    refresh_resp = await client.post("/api/v1/auth/refresh")
    assert refresh_resp.status_code == 200
    data = refresh_resp.json()
    assert "access_token" in data
    assert "refresh_token" in refresh_resp.cookies # 쿠키 갱신 확인

    # 2. 로그아웃 테스트
    logout_resp = await client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {data['access_token']}"})
    assert logout_resp.status_code == 200
    assert "access_token" not in logout_resp.cookies or logout_resp.cookies.get("access_token") == ""
    assert "refresh_token" not in logout_resp.cookies or logout_resp.cookies.get("refresh_token") == ""
