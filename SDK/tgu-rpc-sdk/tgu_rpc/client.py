"""
TguRpcClient - TGU RPC 기본 클라이언트 (동기).

대부분의 사용 사례에 적합. connect/call/disconnect 블로킹 API.
내부적으로 TguRpcClientAsync와 백그라운드 스레드 이벤트 루프 사용.
고급 기능(스트리밍 등)은 TguRpcClientAsync를 사용하세요.
"""

import asyncio
import concurrent.futures
import threading
from typing import Any, Callable, Optional, Union

from wss_mqtt_client.transport import TransportInterface

from .client_async import TguRpcClientAsync
from .exceptions import RpcError, RpcTimeoutError
from .topics import build_stream_topic


def _run_coro(
    loop: asyncio.AbstractEventLoop,
    coro,
    timeout: Optional[float] = None,
) -> Any:
    """동기 컨텍스트에서 코루틴 실행."""
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    try:
        return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        future.cancel()
        raise TimeoutError("작업 시간 초과") from None


class TguRpcClient:
    """
    TGU RPC 기본 클라이언트 (동기).

    connect()/call()/disconnect()는 블로킹 호출.
    대부분의 사용 사례에 적합. 스트리밍·다중 구독 등 고급 기능은
    TguRpcClientAsync를 사용하세요.
    """

    def __init__(
        self,
        url: str,
        token: Optional[str] = None,
        *,
        vehicle_id: str,
        client_id: Optional[str] = None,
        transport: Union[str, TransportInterface] = "wss-mqtt-api",
        call_timeout: float = 30.0,
        **kwargs: Any,
    ) -> None:
        """
        Args:
            url: wss-mqtt-api URL 또는 MQTT 브로커 URL
            token: JWT 또는 API 키
            vehicle_id: 차량 식별자
            client_id: 클라이언트 식별자. None이면 자동 생성
            transport: "wss-mqtt-api" 또는 "mqtt"
            call_timeout: RPC call 기본 타임아웃(초)
            **kwargs: WssMqttClientAsync 추가 인자 (ack_timeout, auto_reconnect 등)
        """
        self._url = url
        self._token = token
        self._vehicle_id = vehicle_id
        self._client_id = client_id
        self._transport = transport
        self._call_timeout = call_timeout
        self._kwargs = kwargs

        self._async_client: Optional[TguRpcClientAsync] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._stop_event = threading.Event()
        self._stream_tasks: list[asyncio.Task[None]] = []  # subscribe_stream 드레인

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
            raise RuntimeError("이벤트 루프 시작 실패")
        return self._loop

    def connect(self) -> None:
        """연결 수립 (블로킹)."""
        loop = self._ensure_loop()

        async def _connect() -> None:
            self._async_client = TguRpcClientAsync(
                url=self._url,
                token=self._token,
                vehicle_id=self._vehicle_id,
                client_id=self._client_id,
                transport=self._transport,
                call_timeout=self._call_timeout,
                **self._kwargs,
            )
            await self._async_client._wss_client.connect()

        _run_coro(loop, _connect())

    def disconnect(self) -> None:
        """연결 종료 (블로킹)."""
        if self._async_client is None:
            return

        loop = self._ensure_loop()

        async def _disconnect() -> None:
            for task in self._stream_tasks:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            self._stream_tasks.clear()
            if self._async_client is not None:
                await self._async_client._wss_client.disconnect()
                self._async_client = None

        try:
            _run_coro(loop, _disconnect())
        except Exception:
            self._async_client = None
            raise

        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread is not None:
                self._thread.join(timeout=5.0)
            self._loop = None
            self._thread = None

    def call(
        self,
        service: str,
        payload: dict[str, Any],
        *,
        timeout: Optional[float] = None,
    ) -> Any:
        """
        RPC 호출. Request-Response 패턴 (블로킹).

        Args:
            service: 서비스 식별자 (예: RemoteUDS, VISS)
            payload: 요청 payload. {"action": str, "params": object?} 규격
            timeout: 타임아웃(초). None이면 call_timeout 사용

        Returns:
            TGU 응답의 result 필드 값

        Raises:
            ValueError: payload에 action이 없는 경우
            RpcError: TGU가 error 필드로 응답한 경우
            RpcTimeoutError: 타임아웃
            RuntimeError: 연결되지 않은 경우
        """
        if self._async_client is None:
            raise RuntimeError("연결되지 않음. connect()를 먼저 호출하세요.")

        loop = self._ensure_loop()
        used_timeout = timeout if timeout is not None else self._call_timeout

        return _run_coro(
            loop,
            self._async_client.call(service, payload, timeout=used_timeout),
            timeout=used_timeout + 5.0,  # 내부 타임아웃보다 여유
        )

    def call_stream(
        self,
        service: str,
        payload: dict[str, Any],
        callback: Callable[[Any], None],
        *,
        on_complete: Optional[Callable[[], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        timeout: Optional[float] = None,
    ) -> None:
        """
        1회 요청 → 멀티 응답. 각 청크마다 callback(chunk) 호출. done 시 on_complete. 블로킹.

        Args:
            service: 서비스 식별자
            payload: 요청 payload. {"action": str, "params": object?}
            callback: 각 청크 수신 시 호출 (chunk) -> None
            on_complete: 스트림 종료 시 호출 (선택)
            on_error: 예외 시 호출 (선택)
            timeout: 타임아웃(초). None이면 call_timeout 사용
        """
        if self._async_client is None:
            raise RuntimeError("연결되지 않음. connect()를 먼저 호출하세요.")

        async def _consume() -> None:
            try:
                async for chunk in self._async_client.call_stream(
                    service, payload, timeout=timeout
                ):
                    callback(chunk)
                if on_complete is not None:
                    on_complete()
            except Exception as e:
                if on_error is not None:
                    on_error(e)
                raise

        loop = self._ensure_loop()
        used_timeout = timeout if timeout is not None else self._call_timeout
        _run_coro(loop, _consume(), timeout=used_timeout + 10.0)

    def run_forever(self, timeout: Optional[float] = None) -> None:
        """수신 루프 (블로킹). subscribe_stream 사용 시. stop()으로 종료 가능."""
        self._stop_event.clear()
        if timeout is not None:
            self._stop_event.wait(timeout=timeout)
        else:
            self._stop_event.wait()

    def stop(self) -> None:
        """run_forever() 블로킹 해제. 다른 스레드 또는 시그널 핸들러에서 호출."""
        self._stop_event.set()

    def subscribe_stream(
        self,
        service: str,
        api: str,
        callback: Callable[[Any], None],
        *,
        params: Optional[dict[str, Any]] = None,
        queue_maxsize: Optional[int] = None,
    ) -> None:
        """
        구독형 스트림 (VISSv3 스타일). connect() 후 호출. run_forever()로 수신.

        Args:
            service: 서비스 식별자 (예: RemoteDashboard)
            api: 스트림 API 식별자 (예: vehicleSpeed)
            callback: 이벤트 수신 시 호출 (event.payload 등)
            params: 선택 (TGU 규격 확정 시 RPC 연동용)
            queue_maxsize: 구독 큐 최대 크기
        """
        if self._async_client is None:
            raise RuntimeError("연결되지 않음. connect()를 먼저 호출하세요.")
        _ = params
        stream_topic = build_stream_topic(
            service, self._vehicle_id, self._async_client._client_id, api
        )

        async def _drain() -> None:
            async with self._async_client._wss_client.subscribe(
                stream_topic, queue_maxsize=queue_maxsize
            ) as stream:
                async for event in stream:
                    callback(event)

        async def _register() -> None:
            task = asyncio.create_task(_drain())
            self._stream_tasks.append(task)

        loop = self._ensure_loop()
        asyncio.run_coroutine_threadsafe(_register(), loop).result(timeout=5.0)

    def publish(self, topic: str, payload: Any) -> None:
        """토픽에 메시지 발행 (블로킹). RPC와 동일한 연결 사용."""
        if self._async_client is None:
            raise RuntimeError("연결되지 않음. connect()를 먼저 호출하세요.")
        loop = self._ensure_loop()
        _run_coro(loop, self._async_client._wss_client.publish(topic, payload))

    def subscribe(
        self,
        topic: str,
        callback: Callable[[Any], None],
        *,
        queue_maxsize: Optional[int] = None,
    ) -> None:
        """
        토픽 구독. connect() 후 호출. run_forever()로 수신. stop()으로 종료.

        Args:
            topic: 구독할 MQTT 토픽
            callback: 수신 시 호출 (event.payload 등)
            queue_maxsize: 구독 큐 최대 크기
        """
        if self._async_client is None:
            raise RuntimeError("연결되지 않음. connect()를 먼저 호출하세요.")

        async def _drain() -> None:
            async with self._async_client._wss_client.subscribe(
                topic, queue_maxsize=queue_maxsize
            ) as stream:
                async for event in stream:
                    callback(event)

        async def _register() -> None:
            task = asyncio.create_task(_drain())
            self._stream_tasks.append(task)

        loop = self._ensure_loop()
        asyncio.run_coroutine_threadsafe(_register(), loop).result(timeout=5.0)

    @property
    def raw_client(self):
        """내부 WssMqttClientAsync 인스턴스. connect() 후에만 사용 가능."""
        if self._async_client is None:
            raise RuntimeError("연결되지 않음. connect()를 먼저 호출하세요.")
        return self._async_client.raw_client

    def __enter__(self) -> "TguRpcClient":
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        self.disconnect()
