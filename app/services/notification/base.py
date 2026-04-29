"""
app/services/notification/base.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
다채널 알림(Email, SMS, Push) 발송을 위한 통합 Base 인터페이스.
"""
from abc import ABC, abstractmethod


class CallResult:
    """발송 결과를 담는 구조체"""
    def __init__(self, success: bool, message: str = ""):
        self.success = success
        self.message = message


class BaseNotificationProvider(ABC):
    """
    모든 알림 프로바이더가 공통으로 상속받아야 하는 인터페이스입니다.
    """

    @abstractmethod
    async def send(self, recipient: str, title: str, content: str) -> CallResult:
        """
        알림 전송 추상 메서드.
        
        Args:
            recipient: 수신자 (Email, 전화번호, Device Token 등)
            title: 제목
            content: 본문 내용
            
        Returns:
            CallResult: 성공 여부 및 메시지
        """
        pass
