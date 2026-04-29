"""
app/api/v1/endpoints/notifications.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
실시간 알림(SSE) 스트리밍 및 발송 엔드포인트.
"""
import logging
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis

from app.core.redis import get_redis
from app.core.deps import get_current_active_user
from app.models.user import User
from app.services.notification.factory import get_notification_provider
from app.services.notification.sse import SSENotificationProvider

router = APIRouter(prefix="/notifications", tags=["Notifications"])
logger = logging.getLogger(__name__)

@router.get("/stream", summary="실시간 알림 스트림 연결")
async def stream_notifications(
    request: Request,
    current_user: User = Depends(get_current_active_user),
    redis: Redis | None = Depends(get_redis)
):
    """
    브라우저와 SSE 연결을 맺고 실시간 알림을 수신합니다.
    사용자별 전역 Redis 채널을 구독합니다.
    """
    if not redis:
        return {"error": "Redis is not available"}

    # Factory를 통해 SSE 프로바이더 획득
    provider = get_notification_provider("sse", redis=redis)
    
    # 팩토리에서 반환된 객체가 SSENotificationProvider인지 확인 (구독 메서드 사용을 위함)
    if not isinstance(provider, SSENotificationProvider):
        return {"error": "Invalid notification provider configuration"}

    # 수신자 ID로 구독 제너레이터 실행
    # recipient는 유저의 고유 ID(사번 혹은 DB ID)를 사용합니다.
    recipient = str(current_user.id)
    
    return StreamingResponse(
        provider.subscribe(recipient),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Nginx 대리 응답 버퍼링 방지
        }
    )

@router.post("/test-send", summary="테스트 알림 발송 (관리자용)")
async def test_send_notification(
    user_id: str,
    title: str,
    content: str,
    redis: Redis | None = Depends(get_redis)
):
    """
    특정 유저에게 실시간 알림을 수동으로 발송해봅니다.
    """
    provider = get_notification_provider("sse", redis=redis)
    result = await provider.send(recipient=user_id, title=title, content=content)
    
    return {
        "success": result.success,
        "message": result.message
    }
