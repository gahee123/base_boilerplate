"""
app/utils/sse.py
~~~~~~~~~~~~~~~~
Server-Sent Events (SSE) 유틸리티.

Redis Pub/Sub을 구독하고 브라우저에 이벤트를 스트리밍하는 제네레이터를 제공합니다.
분산 서버 환경에서 모든 인스턴스가 동일한 알림을 받을 수 있게 합니다.
"""
import asyncio
import json
import logging
from collections.abc import AsyncGenerator

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

async def sse_event_generator(
    redis: aioredis.Redis,
    channel_name: str,
    user_id: str | None = None
) -> AsyncGenerator[str, None]:
    """Redis Pub/Sub 메시지를 SSE 형식으로 변환하여 스트리밍합니다."""
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel_name)

    try:
        # 연결 유지용 하트비트 메시지 대기 시간
        heartbeat_interval = 15

        while True:
            try:
                # 메시지 대기 (타임아웃 적용하여 하트비트 발송 기회 확보)
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_init=True),
                    timeout=heartbeat_interval
                )

                if message and message["type"] == "message":
                    data = json.loads(message["data"])

                    # 특정 유저 필터링 (메시지에 target_user가 있는 경우)
                    target_user = data.get("target_user")
                    if target_user and user_id and str(target_user) != str(user_id):
                        continue

                    yield f"event: message\ndata: {json.dumps(data)}\n\n"

            except TimeoutError:
                # 연결 유지용 하트비트 (Keep-alive)
                yield ": heartbeat\n\n"

    except asyncio.CancelledError:
        logger.info("SSE 연결 종료 (Cancelled)")
    finally:
        await pubsub.unsubscribe(channel_name)
        await pubsub.close()
