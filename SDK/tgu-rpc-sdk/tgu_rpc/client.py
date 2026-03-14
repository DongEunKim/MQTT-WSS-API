"""
TguRpcClient - TGU RPC 기본 클라이언트 (동기).

대부분의 사용 사례에 적합. connect/call/disconnect 블로킹 API.
내부적으로 TguRpcClientAsync와 백그라운드 스레드 이벤트 루프 사용.
고급 기능(스트리밍 등)은 TguRpcClientAsync를 사용하세요.
"""

import asyncio
import concurrent.futures
import threading
from typing import Any, Optional, Union

from wss_mqtt_client.transport import TransportInterface

from .client_async import TguRpcClientAsync
from .exceptions import RpcError, RpcTimeoutError


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
