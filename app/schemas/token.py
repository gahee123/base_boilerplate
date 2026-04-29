"""
app/schemas/token.py
~~~~~~~~~~~~~~~~~~~~
JWT 토큰 관련 Pydantic 스키마.
"""
from pydantic import Field

from app.schemas.base import BaseSchema


class TokenResponse(BaseSchema):
    """로그인/토큰 갱신 응답 스키마."""

    access_token: str = Field(
        ...,
        description="API 접근용 JWT",
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."]
    )
    refresh_token: str = Field(
        ...,
        description="토큰 갱신용 JWT",
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."]
    )
    token_type: str = Field(default="bearer", description="인증 타입", examples=["bearer"])
    expires_in: int = Field(..., description="Access Token 만료까지 남은 초", examples=[1800])


class RefreshTokenRequest(BaseSchema):
    """토큰 갱신 요청 스키마."""

    refresh_token: str = Field(
        ...,
        description="갱신할 Refresh Token",
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."]
    )
