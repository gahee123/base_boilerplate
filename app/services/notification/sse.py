"""
app/services/notification/sse.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Redis Pub/Sub을 이용한 실시간 SSE(Server-Sent Events) 알림 프로바이더.
"""
import asyncio
import json
import logging
from typing import AsyncGenerator

from redis.asyncio import Redis

from app.core.config import settings
from app.services.notification.base import BaseNotificationProvider, CallResult

logger = logging.getLogger(__name__)


class SSENotificationProvider(BaseNotificationProvider):
    """
    브라우저와 유지된 연결을 통해 실시간 알림을 전송하는 프로바이더.
    분산 환경을 지원하기 위해 Redis Pub/Sub을 사용합니다.
    """

    def __init__(self, redis: Redis):
        self.redis = redis
        self.channel_prefix = settings.NOTIFICATIONS_SSE_CHANNEL

    async def send(self, recipient: str, title: str, content: str) -> CallResult:
        """
        특정 유저의 Redis 채널로 메시지를 발행(Publish)합니다.
        
        Args:
            recipient: 수신 유저 ID (문자열)
            title: 알림 제목
            content: 알림 본문
        """
        if not self.redis:
            return CallResult(False, "Redis가 연결되어 있지 않아 SSE 발송이 불가능합니다.")

        channel = f"{self.channel_prefix}:{recipient}"
        payload = {
            "title": title,
            "content": content,
            "timestamp": asyncio.get_event_loop().time()
        }
        
        try:
            await self.redis.publish(channel, json.dumps(payload, ensure_ascii=False))
            return CallResult(True, f"SSE 메시지 발행 성공: {channel}")
        except Exception as e:
            logger.error("SSE 발행 실패: %s", str(e))
            return CallResult(False, f"SSE 발행 중 오류 발생: {str(e)}")

    async def subscribe(self, recipient: str) -> AsyncGenerator[str, None]:
        """
        특정 유저의 Redis 채널을 구독(Subscribe)하고 메시지를 스트리밍합니다.
        API 엔드포인트에서 이 제너레이터를 호출하여 EventSourceResponse로 반환합니다.
        """
        if not self.redis:
            yield "data: {\"error\": \"Redis disconnected\"}\n\n"
            return

        channel = f"{self.channel_prefix}:{recipient}"
        pubsub = self.redis.pubsub()
        
        try:
            await pubsub.subscribe(channel)
            logger.info("SSE 구독 시작: %s", channel)

            # 연결 유지용 Heartbeat 루프와 메시지 수신 루프를 조화롭게 구성
            while True:
                try:
                    # 15초 타임아웃으로 메시지 대기 (없으면 하트비트 전송)
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15.0)
                    
                    if message:
                        data = message["data"]
                        yield f"data: {data}\n\n"
                    else:
                        # Heartbeat 전송 (연결 끊김 방지)
                        yield ": heartbeat\n\n"
                        
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                except Exception as e:
                    logger.error("SSE 스트리밍 중 오류: %s", str(e))
                    break
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
            logger.info("SSE 구독 종료: %s", channel)
