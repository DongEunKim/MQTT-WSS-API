"""
WssMqttClient - WSS-MQTT API 고수준 클라이언트.
"""

import asyncio
import logging
from typing import Any, AsyncIterator, Optional

from .constants import ACK_TIMEOUT_DEFAULT, CODE_OK
from .exceptions import (
    AckError,
    AckTimeoutError,
    SubscriptionTimeoutError,
    WssConnectionError,
)
from .models import AckEvent, Action as ActionEnum, SubscriptionEvent
from .protocol import build_request, encode_request
from .transport import Transport

logger = logging.getLogger(__name__)


class SubscriptionStream:
    """
    구독 스트림. async for로 SUBSCRIPTION 이벤트를 소비한다.

    Usage:
        async for event in client.subscribe("topic/response"):
            print(event.payload)
    """

    def __init__(
        self,
        client: "WssMqttClient",
        topic: str,
        timeout: Optional[float] = None,
    ) -> None:
        self._client = client
        self._topic = topic
        self._timeout = timeout
        self._queue: asyncio.Queue[SubscriptionEvent] = asyncio.Queue()
        self._req_id: Optional[str] = None
        self._subscribed = False
        self._closed = False

    async def __aenter__(self) -> "SubscriptionStream":
        req = build_request(ActionEnum.SUBSCRIBE, self._topic)
        self._req_id = req.req_id
        self._client._register_subscription_handler(self._req_id, self._queue)
        try:
            await self._client._send_and_wait_ack(req)
            self._subscribed = True
            self._client._topic_to_req_id[self._topic] = self._req_id
        except Exception:
            self._client._unregister_subscription_handler(self._req_id)
            raise
        return self

    async def __aexit__(self, *args: Any) -> None:
        self._closed = True
        if self._subscribed and self._req_id:
            await self._client._unsubscribe_and_unregister(
                self._topic, self._req_id
            )
        self._client._unregister_subscription_handler(self._req_id or "")

    def __aiter__(self) -> AsyncIterator[SubscriptionEvent]:
        return self

    async def __anext__(self) -> SubscriptionEvent:
        if not self._subscribed:
            raise RuntimeError(
                "SubscriptionStream must be used as async context manager: "
                "async with client.subscribe(topic) as stream:"
            )
        try:
            return await asyncio.wait_for(
                self._queue.get(),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError as e:
            raise SubscriptionTimeoutError(
                self._topic, self._req_id or "", self._timeout or 0
            ) from e


class WssMqttClient:
    """
    WSS-MQTT API 클라이언트.

    TGU/MQTT와 토픽 기반 publish/subscribe로 통신한다.
    """

    def __init__(
        self,
        url: str,
        token: Optional[str] = None,
        *,
        ack_timeout: float = ACK_TIMEOUT_DEFAULT,
        use_query_token: bool = False,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        """
        Args:
            url: wss://[API_DOMAIN]/v1/messaging
            token: JWT 또는 API 키
            ack_timeout: ACK 수신 대기 시간(초). 기본 5초
            use_query_token: True면 토큰을 쿼리 파라미터로 전달
            logger: 로거
        """
        self._transport = Transport(
            url,
            token,
            use_query_token=use_query_token,
            logger=logger,
        )
        self._ack_timeout = ack_timeout
        self._log = logger if logger is not None else logging.getLogger(__name__)

        self._ack_futures: dict[str, asyncio.Future[AckEvent]] = {}
        self._subscription_handlers: dict[
            str, asyncio.Queue[SubscriptionEvent]
        ] = {}
        self._topic_to_req_id: dict[str, str] = {}
        self._receive_task: Optional[asyncio.Task[None]] = None

    async def connect(self) -> None:
        """WebSocket 연결 수립 및 수신 루프 시작."""
        await self._transport.connect()
        self._transport.set_receive_callback(self._on_message)
        self._receive_task = asyncio.create_task(
            self._transport.receive_loop()
        )

    async def disconnect(self) -> None:
        """연결 종료 및 정리."""
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None
        for future in self._ack_futures.values():
            if not future.done():
                future.cancel()
        self._ack_futures.clear()
        self._subscription_handlers.clear()
        self._topic_to_req_id.clear()
        await self._transport.disconnect()

    async def __aenter__(self) -> "WssMqttClient":
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.disconnect()

    def subscribe(
        self,
        topic: str,
        timeout: Optional[float] = None,
    ) -> SubscriptionStream:
        """
        토픽 구독. async context manager와 async iterator로 사용.

        Usage:
            async with client.subscribe("tgu/device_001/response") as stream:
                async for event in stream:
                    print(event.payload)
                    break  # RPC 패턴: 1건 수신 후 종료
        """
        return SubscriptionStream(self, topic, timeout=timeout)

    async def publish(self, topic: str, payload: Any) -> None:
        """
        토픽에 메시지 발행.

        Args:
            topic: MQTT 토픽
            payload: 발행할 데이터 (JSON 직렬화 가능한 객체)

        Raises:
            AckError: ACK 4xx/5xx 수신 시
            AckTimeoutError: ACK 타임아웃
            WssConnectionError: 연결되지 않음
        """
        req = build_request(ActionEnum.PUBLISH, topic, payload)
        await self._send_and_wait_ack(req)

    async def unsubscribe(self, topic: str) -> None:
        """
        토픽 구독 해제.

        참고: subscribe()의 async with를 벗어나면 자동으로 호출된다.
        """
        req_id = self._topic_to_req_id.get(topic)
        if req_id:
            await self._unsubscribe_and_unregister(topic, req_id)

    def _on_message(self, msg: AckEvent | SubscriptionEvent) -> None:
        """수신 메시지 분배."""
        if isinstance(msg, AckEvent):
            future = self._ack_futures.pop(msg.req_id, None)
            if future and not future.done():
                future.set_result(msg)
        elif isinstance(msg, SubscriptionEvent):
            queue = self._subscription_handlers.get(msg.req_id)
            if queue:
                queue.put_nowait(msg)

    def _register_subscription_handler(
        self, req_id: str, queue: asyncio.Queue[SubscriptionEvent]
    ) -> None:
        self._subscription_handlers[req_id] = queue

    def _unregister_subscription_handler(self, req_id: str) -> None:
        self._subscription_handlers.pop(req_id, None)

    async def _send_and_wait_ack(self, req: Any) -> None:
        """요청 전송 후 ACK 대기."""
        if not self._transport.is_connected:
            raise WssConnectionError("연결되지 않음")
        future: asyncio.Future[AckEvent] = (
            asyncio.get_running_loop().create_future()
        )
        self._ack_futures[req.req_id] = future
        data = encode_request(req)
        await self._transport.send(data)
        try:
            ack = await asyncio.wait_for(future, timeout=self._ack_timeout)
        except asyncio.TimeoutError as e:
            self._ack_futures.pop(req.req_id, None)
            raise AckTimeoutError(req.req_id, self._ack_timeout) from e
        if ack.code != CODE_OK:
            raise AckError(ack.code, ack.req_id, ack.payload)

    async def _unsubscribe_and_unregister(
        self, topic: str, req_id: str
    ) -> None:
        """UNSUBSCRIBE 전송 및 구독 핸들러 해제."""
        self._topic_to_req_id.pop(topic, None)
        self._unregister_subscription_handler(req_id)
        req = build_request(ActionEnum.UNSUBSCRIBE, topic)
        await self._send_and_wait_ack(req)
