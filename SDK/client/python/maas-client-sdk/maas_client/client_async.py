"""
MaasClientAsync: MQTT 5.0 비동기 클라이언트 (고급 인터페이스).
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Callable, Optional

from .connection import Mqtt5Connection, IncomingMessage, encode_payload, build_publish_properties
from ._rpc import RpcManager
from ._pubsub import PubSubManager, MessageHandler
from .models import RpcResponse, StreamEvent, Message

logger = logging.getLogger(__name__)


class MaasClientAsync:
    """
    MQTT 5.0 over WSS 비동기 클라이언트.

    RPC 호출(call, stream, exclusive_session)과 단순 pub/sub를 지원한다.
    asyncio 환경에서 직접 사용하거나, MaasClient(동기)의 내부 구현으로 사용된다.
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
            client_id: MQTT 클라이언트 ID. 응답 토픽 라우팅에 사용.
            token_provider: JWT 토큰을 반환하는 콜백 함수. None이면 인증 없이 연결.
            port: WSS 포트 (기본 443).
            logger: 로거 인스턴스.
        """
        self._endpoint = endpoint
        self._client_id = client_id
        self._token_provider = token_provider
        self._port = port
        self._log = logger or logging.getLogger(__name__)

        token = token_provider() if token_provider else None
        self._conn = Mqtt5Connection(
            endpoint=endpoint,
            client_id=client_id,
            token=token,
            port=port,
            logger=self._log,
        )
        self._rpc = RpcManager(self._conn, client_id)
        self._pubsub = PubSubManager(self._conn)

        self._conn.set_message_callback(self._dispatch_message)

    async def connect(self) -> None:
        """MQTT 브로커에 연결하고 응답 토픽을 구독한다."""
        await self._conn.connect()
        await self._rpc.setup_subscriptions()
        self._log.info(
            "MaasClientAsync 연결 완료: endpoint=%s, client_id=%s",
            self._endpoint,
            self._client_id,
        )

    async def disconnect(self) -> None:
        """연결을 종료한다."""
        await self._conn.disconnect()
        self._log.info("MaasClientAsync 연결 종료")

    async def __aenter__(self) -> "MaasClientAsync":
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.disconnect()

    # ── RPC Layer ────────────────────────────────────────────────────────────

    async def call(
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
        단일 RPC 호출.

        Args:
            thing_type: 사물 타입 (예: CGU).
            service: 서비스 이름 (예: viss).
            action: 실행할 액션 이름. 페이로드에 자동 삽입.
            vin: 대상 장비 VIN.
            payload: 추가 페이로드 (dict 권장).
            qos: MQTT QoS (0 또는 1).
            timeout: 응답 대기 타임아웃(초).
            expiry: Message Expiry Interval(초). 패턴 D(시한성 명령)에 사용.

        Returns:
            RpcResponse (payload, reason_code 포함).
        """
        return await self._rpc.call(
            thing_type=thing_type,
            service=service,
            action=action,
            vin=vin,
            payload=payload,
            qos=qos,
            timeout=timeout,
            expiry=expiry,
        )

    async def stream(
        self,
        thing_type: str,
        service: str,
        action: str,
        vin: str,
        payload: Any = None,
        *,
        qos: int = 1,
    ) -> AsyncIterator[StreamEvent]:
        """
        스트리밍 RPC 호출. async for 로 청크를 수신한다.

        서버는 청크를 WMO/.../event 토픽으로 발행하고,
        완료 신호를 WMO/.../response 토픽으로 발행한다.
        """
        async for event in self._rpc.stream(
            thing_type=thing_type,
            service=service,
            action=action,
            vin=vin,
            payload=payload,
            qos=qos,
        ):
            yield event

    def exclusive_session(
        self,
        thing_type: str,
        service: str,
        vin: str,
        *,
        acquire_action: str = "session_start",
        release_action: str = "session_stop",
        timeout: float = 15.0,
    ) -> "ExclusiveSessionContext":
        """
        독점 세션 컨텍스트 매니저 (패턴 E).

        async with client.exclusive_session(...) as session:
            await session.call(action="ecu_reset", payload={})
        """
        return ExclusiveSessionContext(
            client=self,
            thing_type=thing_type,
            service=service,
            vin=vin,
            acquire_action=acquire_action,
            release_action=release_action,
            timeout=timeout,
        )

    # ── Pub/Sub Layer ─────────────────────────────────────────────────────────

    async def publish(
        self,
        topic: str,
        payload: Any,
        qos: int = 0,
        message_expiry: Optional[int] = None,
    ) -> None:
        """임의 토픽에 메시지 발행."""
        await self._pubsub.publish(topic, payload, qos=qos, message_expiry=message_expiry)

    async def subscribe(
        self,
        topic: str,
        callback: MessageHandler,
        qos: int = 1,
    ) -> None:
        """임의 토픽 구독."""
        await self._pubsub.subscribe(topic, callback, qos=qos)

    async def unsubscribe(self, topic: str) -> None:
        """임의 토픽 구독 해제."""
        await self._pubsub.unsubscribe(topic)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _dispatch_message(self, msg: IncomingMessage) -> None:
        """수신 메시지를 RPC 또는 pub/sub 레이어로 라우팅."""
        if not self._rpc.handle_incoming(msg):
            self._pubsub.handle_incoming(msg)

    @property
    def client_id(self) -> str:
        """클라이언트 ID."""
        return self._client_id

    @property
    def is_connected(self) -> bool:
        """연결 상태."""
        return self._conn.is_connected


class ExclusiveSessionContext:
    """
    독점 세션 비동기 컨텍스트 매니저.

    진입 시 acquire_action RPC를 호출하여 서버 측 Lock을 획득하고,
    종료 시 release_action RPC를 호출하여 Lock을 해제한다.
    """

    def __init__(
        self,
        client: MaasClientAsync,
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

    async def __aenter__(self) -> "ExclusiveSessionContext":
        await self._client.call(
            thing_type=self._thing_type,
            service=self._service,
            action=self._acquire_action,
            vin=self._vin,
            qos=1,
            timeout=self._timeout,
        )
        return self

    async def __aexit__(self, exc_type: Any, *args: Any) -> None:
        try:
            await self._client.call(
                thing_type=self._thing_type,
                service=self._service,
                action=self._release_action,
                vin=self._vin,
                qos=1,
                timeout=self._timeout,
            )
        except Exception:
            logger.warning("세션 해제 RPC 실패", exc_info=True)

    async def call(
        self,
        action: str,
        payload: Any = None,
        *,
        qos: int = 1,
        timeout: Optional[float] = None,
    ) -> RpcResponse:
        """세션 내에서 RPC 호출."""
        return await self._client.call(
            thing_type=self._thing_type,
            service=self._service,
            action=action,
            vin=self._vin,
            payload=payload,
            qos=qos,
            timeout=timeout or self._timeout,
        )
