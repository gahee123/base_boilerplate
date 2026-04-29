import base64
import json
import time
import uuid
from typing import Optional

import jwt
import uvicorn
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

# 프로젝트의 암호화 유틸리티 로드 (경로 주의)
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from app.utils.sso.crypto import hmg_crypto

app = FastAPI(title="Mock HMG SSO Server")

# RS256 서명을 위한 RSA 키 쌍 생성
private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
public_key = private_key.public_key()

pem_public = public_key.public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo
).decode()

def int_to_base64url(val):
    b = val.to_bytes((val.bit_length() + 7) // 8, byteorder='big')
    return base64.urlsafe_b64encode(b).decode('utf-8').rstrip('=')

n_val = int_to_base64url(public_key.public_numbers().n)
e_val = int_to_base64url(public_key.public_numbers().e)

@app.get("/SPI/cert")
async def get_cert():
    """ID Token 검증용 공개키 제공 (JWKS 약식)"""
    return {
        "keys": [
            {
                "kid": "mock-kid",
                "kty": "RSA",
                "alg": "RS256",
                "use": "sig",
                "n": n_val, 
                "e": e_val
            }
        ],
        "pem": pem_public
    }

@app.post("/SPI/healthcheck")
async def healthcheck(request: Request):
    """
    Java VTDM 호환 Healthcheck.
    - 요청: { "str": <AES-GCM 암호문>, "iv": <IV> } (Content-Type: text/plain)
    - 응답: AES-GCM 암호화된 { "result": true, "status": "200" } (Content-Type: text/plain)
    """
    try:
        body = await request.body()
        data = json.loads(body)
        
        # 1. 요청 데이터 복호화 시도 (무결성 검증)
        decrypted = hmg_crypto.decrypt_payload(data["str"], data["iv"])
        print(f"[Mock SSO] Healthcheck Decrypted: {decrypted}")
        
        # [추가] 검증 로직: site가 'INVALID'면 실패 응답
        if decrypted.get("site") == "INVALID":
            json_res = json.dumps({"result": False, "status": "3000"}) # 등록되지 않은 회사 에러
        else:
            json_res = json.dumps({"result": True, "status": "200"})

        enc_str, _ = hmg_crypto.encrypt(json_res, iv_b64=data["iv"])

        
        # hmg_provider.py 105라인: hmg_crypto.decrypt(resp.text, enc_iv) 대응
        # 응답 Body 자체가 암호문이어야 함
        return Response(content=enc_str, media_type="text/plain")
    except Exception as e:
        print(f"[Mock SSO] Healthcheck Error: {e}")
        return Response(content="Internal Error", status_code=500)

@app.get("/SPI/authorize")
async def authorize(state: str, redirect_uri: str, client_id: str, nonce: str = "mock_nonce"):
    """인가 코드 발급 및 리다이렉트 (Nonce를 코드에 숨겨서 상태 비저장 유지)"""
    code = f"mock_code__{nonce}"
    return RedirectResponse(url=f"{redirect_uri}?code={code}&state={state}")

@app.post("/SPI/token")
async def token(request: Request):
    """
    ID Token 발급.
    - info/iv 필드를 포함한 중첩 구조 페이로드 생성
    """
    try:
        form_data = await request.form()
        
        # auth code에서 숨겨둔 nonce 추출 (수동 브라우저 테스트 용이성)
        code_val = form_data.get("code", "")
        extracted_nonce = code_val.split("__")[1] if "__" in code_val else "mock_nonce"
        
        # UserInfoDto 구조 생성 (hmg_provider.py 240~257라인 대응)
        user_info_dto = {
            "site": "H199_W",
            "sitename": "현대오토에버",
            "userid": "V123456",
            "userinfo": {
                "displayName": "홍길동(Mock)",
                "mail": "v123456@hyundai-autoever.com",
                "department": "솔루션개발팀",
                "departmentCode": "D001"
            }
        }
        
        # userinfo를 AES-GCM으로 암호화
        info_enc, iv_enc = hmg_crypto.encrypt_payload(user_info_dto)
        
        # JWT 페이로드 (ProdJwtUtil 호환)
        now = int(time.time())
        id_token_payload = {
            "iss": "http://mock-sso:9092/SPI",
            "sub": "V123456",
            "aud": str(form_data.get("client_id")),
            "exp": now + 3600,
            "iat": now,
            "nonce": extracted_nonce,
            "info": info_enc,
            "iv": iv_enc,
            "uid": "V123456"
        }
        
        id_token = jwt.encode(id_token_payload, private_key, algorithm="RS256", headers={"kid": "mock-kid"})
        
        return {
            "access_token": "mock_access_token",
            "id_token": id_token,
            "token_type": "Bearer",
            "expires_in": 3600
        }
    except Exception as e:
        print(f"[Mock SSO] Token Error: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9092)
