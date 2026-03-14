"""
WssMqttClient - WSS-MQTT API 기본 클라이언트 (동기).

대부분의 사용 사례에 적합. connect/publish/subscribe(callback) 블로킹 API.
내부적으로 WssMqttClientAsync와 백그라운드 스레드 이벤트 루프 사용.
"""

import asyncio
import concurrent.futures
import logging
import threading
from typing import Any, Callable, Optional, Union

from .client import WssMqttClientAsync
from .constants import SUBSCRIPTION_QUEUE_MAXSIZE_DEFAULT
from .exceptions import WssConnectionError
from .models import SubscriptionEvent
from .transport import TransportInterface, MqttTransport, WssMqttApiTransport


def _run_coro(loop: asyncio.AbstractEventLoop, coro, timeout: Optional[float] = None):
    """동기 컨텍스트에서 코루틴 실행."""
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    try:
        return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        future.cancel()
        raise TimeoutError("작업 시간 초과") from None


class WssMqttClient:
    """
    WSS-MQTT API 기본 클라이언트 (동기).

    connect/disconnect/publish는 블로킹 호출.
    subscribe(callback) + run_forever()로 listen-only 구독.

    대부분의 사용 사례에 적합. 스트리밍·다중 구독 등 고급 기능은
    WssMqttClientAsync를 사용하세요.
    """

    def __init__(
        self,
        url: str,
        token: Optional[str] = None,
        *,
        transport: Union[str, TransportInterface] = "wss-mqtt-api",
        use_query_token: bool = False,
        ping_interval: float = 30.0,
        ping_timeout: float = 10.0,
        validate_topic: bool = True,
        topic_max_length: int = 512,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        """
        Args:
            url: wss://[API_DOMAIN]/v1/messaging
            token: JWT 또는 API 키
            transport: "wss-mqtt-api" 또는 "mqtt"
            use_query_token: True면 토큰을 쿼리 파라미터로 전달
            ping_interval: WebSocket Ping 간격(초). wss-mqtt-api 전용
            ping_timeout: Pong 미수신 시 연결 종료(초). wss-mqtt-api 전용
            validate_topic: 토픽 형식 검증 여부
            topic_max_length: 토픽 최대 길이
            logger: 로거
        """
        self._url = url
        self._token = token
        self._transport_name = (
            transport if isinstance(transport, str) else "wss-mqtt-api"
        )
        self._transport_instance = transport if not isinstance(transport, str) else None
        self._use_query_token = use_query_token
        self._ping_interval = ping_interval
        self._ping_timeout = ping_timeout
        self._validate_topic = validate_topic
        self._topic_max_length = topic_max_length
        self._log = logger if logger is not None else logging.getLogger(__name__)

        self._client: Optional[WssMqttClientAsync] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._subscriptions: list[tuple[str, Callable[[SubscriptionEvent], None], Optional[int]]] = []
        self._drain_tasks: list[asyncio.Task[None]] = []

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        """백그라운드 스레드와 이벤트 루프 시작."""
        if self._loop is not None and self._loop.is_running():
            return self._loop

        loop: Optional[asyncio.AbstractEventLoop] = None

        def run_loop() -> None:
            nonlocal loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            self._ready.set()
            loop.run_forever()
            self._loop = None

        self._thread = threading.Thread(target=run_loop, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5.0)
        if self._loop is None:
            raise WssConnectionError("이벤트 루프 시작 실패")
        return self._loop

    def _ensure_client(self) -> WssMqttClientAsync:
        """연결된 클라이언트 보장. connect() 후에만 호출."""
        if self._client is None or not self._client._transport.is_connected:
            raise WssConnectionError("연결되지 않음. connect()를 먼저 호출하세요.")
        return self._client

    def connect(self) -> None:
        """연결 수립 (블로킹)."""
        loop = self._ensure_loop()

        async def _connect() -> None:
            transport: Union[str, TransportInterface] = (
                self._transport_instance
                if self._transport_instance is not None
                else self._transport_name
            )
            self._client = WssMqttClientAsync(
                url=self._url,
                token=self._token,
                transport=transport,
                use_query_token=self._use_query_token,
                ping_interval=self._ping_interval,
                ping_timeout=self._ping_timeout,
                validate_topic=self._validate_topic,
                topic_max_length=self._topic_max_length,
                logger=self._log,
            )
            await self._client.connect()
            for topic, callback, maxsize in self._subscriptions:
                await self._subscribe_callback(topic, callback, maxsize)

        _run_coro(loop, _connect())

    async def _subscribe_callback(
        self,
        topic: str,
        callback: Callable[[SubscriptionEvent], None],
        queue_maxsize: Optional[int],
    ) -> None:
        """콜백 구독 등록 (이벤트 루프 내부용)."""
        from .protocol import build_request, encode_request
        from .models import Action as ActionEnum

        if self._client is None:
            raise WssConnectionError("연결되지 않음")

        maxsize = (
            queue_maxsize
            if queue_maxsize is not None
            else SUBSCRIPTION_QUEUE_MAXSIZE_DEFAULT
        )
        queue: asyncio.Queue[Any] = (
            asyncio.Queue(maxsize=maxsize) if maxsize > 0 else asyncio.Queue()
        )

        async def drain() -> None:
            from .constants import CONNECTION_CLOSED_SENTINEL

            while True:
                try:
                    event = await queue.get()
                    if event is CONNECTION_CLOSED_SENTINEL:
                        break
                    try:
                        callback(event)
                    except Exception:
                        self._log.exception("구독 콜백 예외: topic=%s", topic)
                except asyncio.CancelledError:
                    break

        req = build_request(ActionEnum.SUBSCRIBE, topic)
        self._client._register_subscription_handler(req.req_id, queue)
        await self._client._send_and_wait_ack(req)
        self._client._add_topic_subscriber(topic, req.req_id)
        task = asyncio.create_task(drain())
        self._drain_tasks.append(task)

    def subscribe(
        self,
        topic: str,
        callback: Callable[[SubscriptionEvent], None],
        queue_maxsize: Optional[int] = None,
    ) -> None:
        """
        토픽 구독 (콜백). connect() 전에 호출하거나, connect() 후 호출 가능.

        connect() 전 호출 시 run_forever() 전에 구독 등록.
        connect() 후 호출 시 즉시 구독 (run_forever 사용 시).

        Args:
            topic: 구독할 MQTT 토픽
            callback: 수신 시 호출될 함수 (event: SubscriptionEvent)
            queue_maxsize: 구독 큐 최대 크기. None이면 기본값 사용
        """
        self._subscriptions.append((topic, callback, queue_maxsize))
        if self._client is not None and self._client._transport.is_connected:
            loop = self._ensure_loop()
            _run_coro(
                loop,
                self._subscribe_callback(topic, callback, queue_maxsize),
            )

    def publish(self, topic: str, payload: Any) -> None:
        """토픽에 메시지 발행 (블로킹)."""
        client = self._ensure_client()
        loop = self._ensure_loop()
        _run_coro(loop, client.publish(topic, payload))

    def disconnect(self, unsubscribe_first: bool = False) -> None:
        """연결 종료 (블로킹)."""
        if self._client is None:
            return

        loop = self._ensure_loop()

        async def _disconnect() -> None:
            for task in self._drain_tasks:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            self._drain_tasks.clear()
            await self._client.disconnect(unsubscribe_first=unsubscribe_first)
            self._client = None

        try:
            _run_coro(loop, _disconnect())
        except Exception:
            self._client = None
            raise

        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread is not None:
                self._thread.join(timeout=5.0)
            self._loop = None
            self._thread = None

    def run_forever(self, timeout: Optional[float] = None) -> None:
        """
        수신 루프 실행 (블로킹). connect() 및 subscribe() 후 호출.

        Args:
            timeout: 대기 시간(초). None이면 무한 대기 (Ctrl+C로 종료)
        """
        self._ensure_client()
        stop = threading.Event()
        if timeout is not None:
            stop.wait(timeout=timeout)
        else:
            stop.wait()

    def run(self, timeout: float = 30.0) -> None:
        """run_forever(timeout) 별칭."""
        self.run_forever(timeout=timeout)

    @property
    def is_connected(self) -> bool:
        """연결 상태."""
        return (
            self._client is not None
            and self._client._transport.is_connected
        )

    def __enter__(self) -> "WssMqttClient":
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        self.disconnect(unsubscribe_first=True)
