"""
WSS-MQTT 클라이언트 예외 정의.
"""

from typing import Any, Optional


class WssMqttError(Exception):
    """WSS-MQTT SDK 기본 예외."""

    pass


class WssConnectionError(WssMqttError):
    """연결 실패 또는 연결 끊김."""

    pass


class AckError(WssMqttError):
    """
    ACK 4xx/5xx 응답 수신 시 발생.

    Attributes:
        code: HTTP 상태 코드 (400, 401, 403, 422, 504)
        req_id: 해당 요청 식별자
        payload: 에러 상세 메시지 (선택)
    """

    def __init__(
        self,
        code: int,
        req_id: str,
        payload: Optional[Any] = None,
        message: Optional[str] = None,
    ) -> None:
        self.code = code
        self.req_id = req_id
        self.payload = payload
        if message is None:
            message = f"ACK error: code={code}, req_id={req_id}"
        super().__init__(message)


class AckTimeoutError(WssMqttError):
    """ACK 5초 이내 미수신 시 발생."""

    def __init__(self, req_id: str, timeout: float) -> None:
        self.req_id = req_id
        self.timeout = timeout
        super().__init__(f"ACK timeout for req_id={req_id} (timeout={timeout}s)")


class SubscriptionTimeoutError(WssMqttError):
    """구독 응답 30초 이내 미수신 시 발생."""

    def __init__(self, topic: str, req_id: str, timeout: float) -> None:
        self.topic = topic
        self.req_id = req_id
        self.timeout = timeout
        super().__init__(
            f"Subscription timeout for topic={topic}, req_id={req_id} (timeout={timeout}s)"
        )
