"""
Transport 프로토콜 정의.

WssMqttClient가 요구하는 전송 계층 인터페이스.
"""

from typing import Any, Callable, Protocol, runtime_checkable


@runtime_checkable
class TransportInterface(Protocol):
    """
    전송 계층 프로토콜.

    WssMqttClient는 이 인터페이스를 구현한 transport를 주입받아 사용한다.
    send/receive_callback는 decode_message 결과(AckEvent | SubscriptionEvent)를
    다룬다.
    """

    async def connect(self) -> None:
        """연결 수립."""
        ...

    async def disconnect(self) -> None:
        """연결 종료."""
        ...

    async def send(self, data: str | bytes) -> None:
        """
        메시지 전송.

        Args:
            data: JSON 문자열 또는 MessagePack 바이너리
        """
        ...

    def set_receive_callback(self, callback: Callable[[Any], None]) -> None:
        """수신 메시지 콜백 등록. decode_message 결과가 전달된다."""
        ...

    async def receive_loop(self) -> None:
        """수신 루프. 연결 유지 동안 메시지 수신 후 콜백 호출."""
        ...

    @property
    def is_connected(self) -> bool:
        """연결 상태."""
        ...
