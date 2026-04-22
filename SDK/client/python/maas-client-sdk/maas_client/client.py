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
from typing import Any, Iterator, Optional

from .auth import TokenProvider
from .client_async import MaasClientAsync
from ._pubsub import MessageHandler
from .models import RpcResponse, StreamEvent, Message

logger = logging.getLogger(__name__)


class MaasClient:
    """
    MQTT 5.0 동기 클라이언트 (기본 인터페이스).

    기본은 WSS+TLS이며, ``use_wss=False`` 로 로컬 TCP 브로커(Mosquitto 등)에도 연결할 수 있다.
    내부적으로 asyncio 루프를 전용 스레드에서 운영한다.
    모든 메서드는 블로킹 방식으로 동작하므로 일반 Python 스크립트,
    Flask 등 비동기 컨텍스트 없이 바로 사용할 수 있다.

    Example (생성자 바인딩 + 짧은 ``call``)::

        client = MaasClient(
            endpoint="mqtt.example.com",
            client_id="my-client",
            thing_type="CGU",
            service="viss",
            vin="VIN-001",
            token_provider=get_jwt,
        )
        client.connect()
        result = client.call("get", {"path": "Vehicle.Speed"})
        client.disconnect()

    Example (호출마다 라우팅 지정)::

        client = MaasClient(endpoint="...", client_id="...")
        client.connect()
        result = client.call("CGU", "viss", "get", "VIN-001", {"path": "Vehicle.Speed"})
        client.disconnect()
    """

    def __init__(
        self,
        endpoint: str,
        client_id: str,
        token_provider: Optional[TokenProvider] = None,
        port: Optional[int] = None,
        *,
        use_wss: bool = True,
        thing_type: Optional[str] = None,
        service: Optional[str] = None,
        vin: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        """
        Args:
            endpoint: 브로커 호스트명.
            client_id: MQTT 클라이언트 ID.
            token_provider: 연결 시마다 호출되어 MQTT username 문자열을 반환.
                None이면 인증 없이 연결.
            port: 브로커 포트. None이면 ``use_wss`` 에 따라 443(WSS) 또는 1883(TCP).
            use_wss: True면 WebSocket+TLS, False면 TCP(로컬 Mosquitto 등).
            thing_type: 바인딩 시 토픽 ThingType. ``service``, ``vin`` 과 함께 세트로 지정.
            service: 바인딩 시 서비스 이름.
            vin: 바인딩 시 대상 VIN.
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
            use_wss=use_wss,
            thing_type=thing_type,
            service=service,
            vin=vin,
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
        *args,
        params: Any = None,
        qos: int = 1,
        timeout: float = 10.0,
        expiry: Optional[int] = None,
    ) -> RpcResponse:
        """
        단일 RPC 호출 (블로킹).

        ``MaasClientAsync.call`` 와 동일한 인자 규칙:
        바인딩 시 ``call(action[, params])``, 명시 시
        ``call(thing_type, service, action, vin[, params])``.

        ``timeout``·``expiry``·QoS 1에서의 Message Expiry 연동은
        ``MaasClientAsync.call`` 과 동일하다.

        Returns:
            RpcResponse.

        Raises:
            TypeError, ValueError: 인자 조합 오류.
            RpcTimeoutError: 타임아웃 초과.
            RpcServerError: 서버 오류 응답.
        """
        return self._run(
            self._async.call(
                *args,
                params=params,
                qos=qos,
                timeout=timeout,
                expiry=expiry,
            ),
            timeout=timeout + 5.0,
        )

    def stream(
        self,
        *args,
        params: Any = None,
        qos: int = 1,
        chunk_timeout: float = 60.0,
    ) -> Iterator[StreamEvent]:
        """
        스트리밍 RPC 호출 (동기 이터레이터).

        인자 규칙은 ``call`` 과 동일.

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
                    *args,
                    params=params,
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
        *thing_svc_vin: str,
        acquire_action: str = "session_start",
        release_action: str = "session_stop",
        timeout: float = 15.0,
    ) -> "SyncExclusiveSessionContext":
        """
        독점 세션 컨텍스트 매니저 (패턴 E).

        인자 없음: 생성자 바인딩 사용.

        인자 세 개: (thing_type, service, vin) 명시.

        with client.exclusive_session() as session:
            session.call("ecu_reset", params={})
        """
        if len(thing_svc_vin) == 0:
            thing_type, service, vin = self._async._bound_routing()
        elif len(thing_svc_vin) == 3:
            thing_type, service, vin = (
                thing_svc_vin[0],
                thing_svc_vin[1],
                thing_svc_vin[2],
            )
        else:
            raise TypeError(
                "exclusive_session() 인자는 0개(생성자 바인딩) 또는 "
                "(thing_type, service, vin) 3개여야 합니다."
            )
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
        params: Any = None,
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
            params=params,
            qos=qos,
            timeout=timeout or self._timeout,
        )
