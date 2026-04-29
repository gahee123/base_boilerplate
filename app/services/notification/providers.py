"""
app/services/notification/providers.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
실제 알림망 연동 전 단계의 Dummy Adapter 구현체.
시스템 구성 및 비즈니스 로직 테스트용으로 사용됩니다.
"""
import asyncio
import logging

from app.services.notification.base import BaseNotificationProvider, CallResult

logger = logging.getLogger(__name__)


class DummyEmailProvider(BaseNotificationProvider):
    async def send(self, recipient: str, title: str, content: str) -> CallResult:
        logger.info(f"[Email 발송 시뮬레이션] To: {recipient} | Title: {title}")
        # 외부 API 호출 시뮬레이션
        await asyncio.sleep(0.5)
        return CallResult(success=True, message="Email 전송 완료 (Dummy)")


class DummySMSProvider(BaseNotificationProvider):
    async def send(self, recipient: str, title: str, content: str) -> CallResult:
        logger.info(f"[SMS 발송 시뮬레이션] To: {recipient} | Title: {title}")
        await asyncio.sleep(0.3)
        return CallResult(success=True, message="SMS 전송 완료 (Dummy)")


class DummyPushProvider(BaseNotificationProvider):
    async def send(self, recipient: str, title: str, content: str) -> CallResult:
        logger.info(f"[App Push 발송 시뮬레이션] Token: {recipient} | Title: {title}")
        await asyncio.sleep(0.2)
        return CallResult(success=True, message="Push 전송 완료 (Dummy)")
