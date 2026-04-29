from pydantic import BaseModel
from uuid import UUID

class TokenResponse(BaseModel):
    """Access Token 응답 스키마"""
    access_token: str
    token_type: str = "Bearer"
    expires_in: int | None = None  # 토큰 만료 시간 (초, 선택 사항)

class AuthCodeRequest(BaseModel):
    """임시 코드를 통한 토큰 교환 요청"""
    code: str

class MessageResponse(BaseModel):
    """일반 메시지 응답"""
    message: str
