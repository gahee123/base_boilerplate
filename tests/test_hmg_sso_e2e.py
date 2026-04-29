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
    HMG SSO 통합 검증 - Redis 세션 및 Nonce 검증을 포함한 무결성 테스트.
    """
    mock_settings = {
        "HMG_SSO_BASE_URL": "http://mock-sso/SPI",
        "HMG_SSO_CLIENT_ID": "verify_svc",
        "HMG_SSO_CALLBACK_URI": "http://testserver/api/v1/auth/hmg/callback",
        "HMG_SSO_CIPHER_KEY": "0000000000000000000000000000000000000000000000000000000000000000"
    }
    
    # 1. 환경변수 및 JWKS 클라이언트 패치
    with patch.multiple(settings, **mock_settings), \
         patch("app.services.oidc.hmg_provider.PyJWKClient.get_signing_key_from_jwt") as mock_key_grabber:
        
        mock_key_grabber.return_value = MagicMock(key=PUBLIC_KEY)
        
        # 2. HTTP 통신 Mocking (respx)
        with respx.mock(base_url="http://mock-sso/SPI", assert_all_called=False) as respx_mock:
            
            # [A] Healthcheck Handler
            def healthcheck_handler(request):
                content = json.loads(request.content)
                req_iv = content.get("iv")
                enc_str, _ = hmg_crypto.encrypt(json.dumps({"result":True, "status":"200"}), iv_b64=req_iv)
                return Response(200, text=enc_str)
            respx_mock.post("/healthcheck").side_effect = healthcheck_handler

            # [Step 1: 로그인 시작 (Redis에 state/nonce/verifier 저장 유도)]
            resp = await client.get("/api/v1/auth/hmg/login?site_code=H101&login_type=simple")
            assert resp.status_code in (302, 307)
            
            target_url = resp.headers["location"]
            q_params = urllib.parse.parse_qs(urllib.parse.urlparse(target_url).query)
            state_val = q_params["state"][0]
            nonce_val = q_params["nonce"][0]

            # [B] Token Exchange Handler - URL에서 추출한 nonce를 서명에 포함
            def token_handler(request):
                user_dto = {
                    "site":"H199_W", "userid":"V123", 
                    "userinfo":{
                        "displayName":"최종인", "mail":"v123@h.com", "department":"솔루션개발팀"
                    }
                }
                info_enc, iv_enc = hmg_crypto.encrypt_payload(user_dto)
                
                # 백엔드가 요청 시 넘겨준 nonce를 포함하여 ID Token 생성 (RS256)
                token = jwt.encode({
                    "iss":"http://mock-sso/SPI", 
                    "sub":"V123", 
                    "aud":"verify_svc", 
                    "exp":int(time.time())+60, 
                    "info":info_enc, 
                    "iv":iv_enc,
                    "nonce": nonce_val
                }, PRIVATE_KEY, algorithm="RS256")
                
                return Response(200, json={"id_token": token, "access_token": "at"})

            
            respx_mock.post("/token").side_effect = token_handler

            # [Step 2: 콜백 처리 (JWT 검증 및 DB 동기화 실행)]
            resp = await client.get(f"/api/v1/auth/hmg/callback?code=mock_c&state={state_val}")
            assert resp.status_code in (302, 307)
            
            # [Step 3: 최종 DB 확인]
            stmt = select(User).where(User.employee_id=="V123")
            db_res = await db_session.execute(stmt)
            user = db_res.scalar_one_or_none()
            
            assert user is not None
            assert user.full_name == "최종인"
            assert user.site_code == "H199_W"

    print("\n[SUCCESS] HMG SSO Auth logic verified completely!")
