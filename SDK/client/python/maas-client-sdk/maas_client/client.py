"""
MaasClient: MQTT 5.0 동기 클라이언트 (기본 인터페이스).

asyncio 루프를 백그라운드 스레드에서 실행하며,
모든 메서드는 결과가 나올 때까지 블로킹한다.
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
from typing import Any, Callable, Generator, Iterator, Optional

from .client_async import MaasClientAsync
from ._pubsub import MessageHandler
from .models import RpcResponse, StreamEvent, Message

logger = logging.getLogger(__name__)


class MaasClient:
    """
    MQTT 5.0 over WSS 동기 클라이언트 (기본 인터페이스).

    내부적으로 asyncio 루프를 전용 스레드에서 운영한다.
    모든 메서드는 블로킹 방식으로 동작하므로 일반 Python 스크립트,
    Flask, Greengrass Component 등 비동기 컨텍스트 없이 바로 사용할 수 있다.

    Example::

        client = MaasClient(
            endpoint="xxxx.iot.amazonaws.com",
            client_id="my-client",
            token_provider=get_jwt,
        )
        client.connect()

        result = client.call("CGU", "viss", "get", "VIN-001", {"path": "Vehicle.Speed"})
        print(result.payload)

        client.disconnect()
    """

    def __init__(
        self,
        endpoint: str,
        client_id: str,
        token_provider: Optional[Callable[[], str]] = None,
        port: int = 443,
        *,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        """
        Args:
            endpoint: AWS IoT Core 엔드포인트 호스트명.
            client_id: MQTT 클라이언트 ID.
            token_provider: JWT 토큰을 반환하는 콜백. None이면 인증 없이 연결.
            port: WSS 포트 (기본 443).
            logger: 로거 인스턴스.
        """
        self._log = logger or logging.getLogger(__name__)
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever,
            name="maas-client-loop",
            daemon=True,
        )
        self._thread.start()

        self._async = MaasClientAsync(
            endpoint=endpoint,
            client_id=client_id,
            token_provider=token_provider,
            port=port,
            logger=self._log,
        )

    def _run(self, coro: Any, timeout: Optional[float] = None) -> Any:
        """코루틴을 백그라운드 루프에 제출하고 결과를 블로킹 대기."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    def connect(self, timeout: float = 30.0) -> None:
        """MQTT 브로커에 연결한다."""
        self._run(self._async.connect(), timeout=timeout)

    def disconnect(self) -> None:
        """연결을 종료하고 백그라운드 루프를 중지한다."""
        try:
            self._run(self._async.disconnect(), timeout=10.0)
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=5.0)

    def __enter__(self) -> "MaasClient":
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        self.disconnect()

    # ── RPC Layer ────────────────────────────────────────────────────────────

    def call(
        self,
        thing_type: str,
        service: str,
        action: str,
        vin: str,
        payload: Any = None,
        *,
        qos: int = 1,
        timeout: float = 10.0,
        expiry: Optional[int] = None,
    ) -> RpcResponse:
        """
        단일 RPC 호출 (블로킹).

        Args:
            thing_type: 사물 타입 (예: CGU).
            service: 서비스 이름 (예: viss).
            action: 실행할 액션. 페이로드에 자동 삽입.
            vin: 대상 장비 VIN.
            payload: 추가 페이로드 (dict 권장).
            qos: MQTT QoS (0 또는 1).
            timeout: 응답 대기 타임아웃(초).
            expiry: Message Expiry Interval(초). 패턴 D(시한성 명령)에 사용.

        Returns:
            RpcResponse.

        Raises:
            RpcTimeoutError: 타임아웃 초과.
            RpcServerError: 서버 오류 응답.
        """
        return self._run(
            self._async.call(
                thing_type=thing_type,
                service=service,
                action=action,
                vin=vin,
                payload=payload,
                qos=qos,
                timeout=timeout,
                expiry=expiry,
            ),
            timeout=timeout + 5.0,
        )

    def stream(
        self,
        thing_type: str,
        service: str,
        action: str,
        vin: str,
        payload: Any = None,
        *,
        qos: int = 1,
        chunk_timeout: float = 60.0,
    ) -> Iterator[StreamEvent]:
        """
        스트리밍 RPC 호출 (동기 이터레이터).

        for chunk in client.stream("CGU", "diagnostics", "can_log", "VIN-001"):
            process(chunk)

        Args:
            chunk_timeout: 청크 간 최대 대기 시간(초).

        Yields:
            StreamEvent (is_eof=False인 청크들).

        Raises:
            RpcServerError: 서버 오류.
            StreamInterruptedError: 연결 끊김.
        """
        sync_queue: queue.Queue = queue.Queue()

        async def _collect() -> None:
            try:
                async for event in self._async.stream(
                    thing_type=thing_type,
                    service=service,
                    action=action,
                    vin=vin,
                    payload=payload,
                    qos=qos,
                ):
                    sync_queue.put(event)
            except Exception as exc:
                sync_queue.put(exc)
            finally:
                sync_queue.put(None)  # 종료 sentinel

        asyncio.run_coroutine_threadsafe(_collect(), self._loop)

        while True:
            item = sync_queue.get(timeout=chunk_timeout)
            if item is None:
                break
            if isinstance(item, Exception):
                raise item
            if not item.is_eof:
                yield item

    def exclusive_session(
        self,
        thing_type: str,
        service: str,
        vin: str,
        *,
        acquire_action: str = "session_start",
        release_action: str = "session_stop",
        timeout: float = 15.0,
    ) -> "SyncExclusiveSessionContext":
        """
        독점 세션 컨텍스트 매니저 (패턴 E).

        with client.exclusive_session("CGU", "uds", "VIN-001") as session:
            session.call("ecu_reset", payload={})
        """
        return SyncExclusiveSessionContext(
            client=self,
            thing_type=thing_type,
            service=service,
            vin=vin,
            acquire_action=acquire_action,
            release_action=release_action,
            timeout=timeout,
        )

    # ── Pub/Sub Layer ─────────────────────────────────────────────────────────

    def publish(
        self,
        topic: str,
        payload: Any,
        qos: int = 0,
        message_expiry: Optional[int] = None,
    ) -> None:
        """임의 토픽에 메시지 발행 (블로킹)."""
        self._run(
            self._async.publish(topic, payload, qos=qos, message_expiry=message_expiry)
        )

    def subscribe(self, topic: str, callback: MessageHandler, qos: int = 1) -> None:
        """임의 토픽 구독 (블로킹). 메시지 수신 시 callback이 호출된다."""
        self._run(self._async.subscribe(topic, callback, qos=qos))

    def unsubscribe(self, topic: str) -> None:
        """임의 토픽 구독 해제 (블로킹)."""
        self._run(self._async.unsubscribe(topic))

    @property
    def client_id(self) -> str:
        """클라이언트 ID."""
        return self._async.client_id

    @property
    def is_connected(self) -> bool:
        """연결 상태."""
        return self._async.is_connected


class SyncExclusiveSessionContext:
    """MaasClient용 동기 독점 세션 컨텍스트 매니저."""

    def __init__(
        self,
        client: MaasClient,
        thing_type: str,
        service: str,
        vin: str,
        acquire_action: str,
        release_action: str,
        timeout: float,
    ) -> None:
        self._client = client
        self._thing_type = thing_type
        self._service = service
        self._vin = vin
        self._acquire_action = acquire_action
        self._release_action = release_action
        self._timeout = timeout

    def __enter__(self) -> "SyncExclusiveSessionContext":
        self._client.call(
            self._thing_type,
            self._service,
            self._acquire_action,
            self._vin,
            qos=1,
            timeout=self._timeout,
        )
        return self

    def __exit__(self, exc_type: Any, *args: Any) -> None:
        try:
            self._client.call(
                self._thing_type,
                self._service,
                self._release_action,
                self._vin,
                qos=1,
                timeout=self._timeout,
            )
        except Exception:
            logger.warning("세션 해제 RPC 실패", exc_info=True)

    def call(
        self,
        action: str,
        payload: Any = None,
        *,
        qos: int = 1,
        timeout: Optional[float] = None,
    ) -> RpcResponse:
        """세션 내에서 RPC 호출."""
        return self._client.call(
            self._thing_type,
            self._service,
            action,
            self._vin,
            payload=payload,
            qos=qos,
            timeout=timeout or self._timeout,
        )
