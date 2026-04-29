"""
app/services/notification/factory.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
알림 채널(channel)에 따라 적절한 프로바이더 인스턴스를 반환하는 팩토리.
"""
from typing import Literal

from redis.asyncio import Redis

from app.services.notification.base import BaseNotificationProvider
from app.services.notification.providers import (
    DummyEmailProvider,
    DummyPushProvider,
    DummySMSProvider,
)
from app.services.notification.sse import SSENotificationProvider
from app.utils.exceptions import BadRequest

NotificationChannel = Literal["email", "sms", "push", "sse"]


def get_notification_provider(
    channel: NotificationChannel, redis: Redis | None = None
) -> BaseNotificationProvider:
    """채널에 맞는 알림 프로바이더를 선택하여 반환합니다."""
    if channel == "sse":
        if not redis:
            raise BadRequest("SSE 채널을 사용하려면 Redis 클라이언트가 필요합니다.")
        return SSENotificationProvider(redis)

    if channel == "email":
        return DummyEmailProvider()
    elif channel == "sms":
        return DummySMSProvider()
    elif channel == "push":
        return DummyPushProvider()
    else:
        raise BadRequest(f"지원하지 않는 알림 채널입니다: {channel}")
