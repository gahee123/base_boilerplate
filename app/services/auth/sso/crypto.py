"""
app/services/auth/sso/crypto.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
HMG SSO 전용 AES-GCM 암복호화 유틸리티.
"""
import base64
import json
import re
import secrets
from typing import Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings
from app.utils.exceptions import Unauthorized

GCM_IV_LENGTH = 16


def _hex_to_bytes(hex_str: str) -> bytes:
    hex_clean = hex_str.strip().replace("0x", "").replace(" ", "")
    if not re.match(r"(?i)^[0-9a-f]{64}$", hex_clean):
        raise ValueError(f"HMG_SSO_CIPHER_KEY must be 64 hex chars. Got {len(hex_clean)}.")
    return bytes.fromhex(hex_clean)


class HmgCrypto:
    def __init__(self) -> None:
        key_str = getattr(settings, "HMG_SSO_CIPHER_KEY", "")
        if not key_str:
            self.key = b"\x00" * 32
        else:
            self.key = _hex_to_bytes(key_str)
        self.aesgcm = AESGCM(self.key)

    def encrypt(self, plaintext: str, iv_b64: str | None = None) -> Tuple[str, str]:
        if iv_b64 is None or iv_b64 == "":
            iv = secrets.token_bytes(GCM_IV_LENGTH)
        else:
            iv = base64.urlsafe_b64decode(iv_b64)
        plaintext_bytes = plaintext.encode("utf-8")
        ciphertext = self.aesgcm.encrypt(iv, plaintext_bytes, None)
        encrypted = iv + ciphertext
        enc_str = base64.urlsafe_b64encode(encrypted).decode("utf-8")
        iv_str = base64.urlsafe_b64encode(iv).decode("utf-8")
        return enc_str, iv_str

    def decrypt(self, enc_b64: str, iv_b64: str) -> str:
        try:
            iv = base64.urlsafe_b64decode(iv_b64)
            decoded = base64.urlsafe_b64decode(enc_b64)
            ciphertext = decoded[GCM_IV_LENGTH:]
            plaintext = self.aesgcm.decrypt(iv, ciphertext, None)
            return plaintext.decode("utf-8")
        except Exception as e:
            raise Unauthorized("SSO 응답 데이터 복호화에 실패했습니다.") from e


hmg_crypto = HmgCrypto()
