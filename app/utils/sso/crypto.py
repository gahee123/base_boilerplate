"""
app/utils/sso/crypto.py
~~~~~~~~~~~~~~~~~~~~~~~
HMG SSO 연동을 위한 AES-GCM 양방향 암복호화 유틸리티.

HMG SSO 서버가 요구하는 AES-GCM 암호화 규격을 준수합니다.
규격 세부사항은 Java(VTDM) 프로젝트의 AESGCMCipher.java가
실 서버 통신에서 사용한 방식을 근거로 도출했습니다.

규격:
  - 키: 64자 Hex 문자열 → 32바이트 (AES-256)
  - IV: 16바이트 (GCM_IV_LENGTH = 16)
  - Tag: 128비트 (GCM_TAG_LENGTH = 128)
  - Base64: URL-safe 인코딩
  - 암호문 포맷: IV + Ciphertext 결합 후 단일 인코딩
"""
import base64
import json
import re
import secrets
from typing import Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings
from app.utils.exceptions import Unauthorized

# Java VTDM 기준 상수
# HMG SSO 기준 상수
GCM_IV_LENGTH = 16
GCM_TAG_LENGTH = 128


def _hex_to_bytes(hex_str: str) -> bytes:
    """
    Hex 문자열 → bytes 변환 (HMG SSO 키 포맷).
    입력: 64자 Hex 문자열 (대소문자 불문)
    출력: 32바이트 AES-256 키
    """
    hex_clean = hex_str.strip().replace("0x", "").replace(" ", "")
    if not re.match(r"(?i)^[0-9a-f]{64}$", hex_clean):
        raise ValueError(
            "HMG_SSO_CIPHER_KEY must be 64 hex chars (32 bytes for AES-256). "
            f"Got {len(hex_clean)} chars."
        )
    return bytes.fromhex(hex_clean)


class HmgCrypto:
    """HMG SSO 서버 규격을 준수하는 AES-256-GCM 암복호화 클래스."""

    def __init__(self) -> None:
        key_str = getattr(settings, "HMG_SSO_CIPHER_KEY", "")
        if not key_str:
            # 개발 환경 폴백 — 프로덕션에서는 필수 검증
            self.key = b"\x00" * 32
        else:
            self.key = _hex_to_bytes(key_str)

        self.aesgcm = AESGCM(self.key)

    def encrypt(self, plaintext: str, iv_b64: str | None = None) -> Tuple[str, str]:
        """
        Java AESGCMCipher.encrypt() 호환 암호화.

        1) IV가 없으면 16바이트 랜덤 생성, 있으면 URL-safe Base64 디코딩
        2) AES-GCM 암호화 수행
        3) IV + Ciphertext(Tag 포함)를 결합하여 URL-safe Base64 인코딩

        Returns:
            (암호문 URL-safe Base64, IV URL-safe Base64)
        """
        if iv_b64 is None or iv_b64 == "":
            iv = secrets.token_bytes(GCM_IV_LENGTH)
        else:
            iv = base64.urlsafe_b64decode(iv_b64)

        plaintext_bytes = plaintext.encode("utf-8")
        ciphertext = self.aesgcm.encrypt(iv, plaintext_bytes, None)

        # Java 포맷: IV + Ciphertext 결합 후 단일 인코딩
        encrypted = iv + ciphertext
        enc_str = base64.urlsafe_b64encode(encrypted).decode("utf-8")
        iv_str = base64.urlsafe_b64encode(iv).decode("utf-8")

        return enc_str, iv_str

    def decrypt(self, enc_b64: str, iv_b64: str) -> str:
        """
        Java AESGCMCipher.decrypt() 호환 복호화.

        1) IV를 URL-safe Base64 디코딩
        2) 암호문을 URL-safe Base64 디코딩
        3) 디코딩된 암호문에서 앞 16바이트(IV)를 제거하고 나머지를 복호화

        Returns:
            복호화된 평문 문자열
        """
        try:
            iv = base64.urlsafe_b64decode(iv_b64)
            decoded = base64.urlsafe_b64decode(enc_b64)

            # Java 포맷: decoded = IV(16) + Ciphertext(나머지)
            ciphertext = decoded[GCM_IV_LENGTH:]
            plaintext = self.aesgcm.decrypt(iv, ciphertext, None)

            return plaintext.decode("utf-8")
        except Exception as e:
            raise Unauthorized(
                "SSO 응답 데이터 복호화에 실패했습니다. (무결성 훼손 오류)"
            ) from e

    # ── 편의 래퍼 (dict 기반) ──

    def encrypt_payload(self, payload: dict) -> Tuple[str, str]:
        """dict → JSON 문자열 → 암호화. Java 호환 형식으로 반환."""
        json_str = json.dumps(payload, ensure_ascii=False)
        return self.encrypt(json_str)

    def decrypt_payload(self, enc_b64: str, iv_b64: str) -> dict:
        """암호문 → 복호화 → JSON dict 파싱."""
        plaintext = self.decrypt(enc_b64, iv_b64)
        return json.loads(plaintext)


hmg_crypto = HmgCrypto()
