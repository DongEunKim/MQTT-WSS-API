"""
MaasServer: MQTT 5.0 서비스 서버 (기본 인터페이스).

asyncio 이벤트 루프에서 MQTT를 구동하고,
@action 데코레이터로 RPC 핸들러를 등록한 뒤 run()으로 실행한다.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Callable, Optional

from .connection import Mqtt5ServerConnection, IncomingMessage, encode_payload
from ._dispatcher import Dispatcher
from .session import SessionManager
from .presence import PresenceMonitor
from .context import RpcContext
from . import topics as topic_utils

logger = logging.getLogger(__name__)


class MaasServer:
    """
    MQTT 5.0 RPC 서비스 서버.

    토픽의 ``{ThingType}``, ``{Service}``, ``{VIN}`` 을 고정하고
    ``@server.action("이름")`` 으로 페이로드 ``action`` 과 매칭되는 핸들러를 등록한다.

    Example::

        server = MaasServer(
            thing_type="CGU",
            service_name="viss",
            vin="VIN-123456",
            endpoint="xxxx.iot.amazonaws.com",
        )

        @server.action("get")
        def get_datapoint(ctx: RpcContext):
            return {"value": read_sensor(ctx.payload.get("path"))}

        server.run()  # 블로킹
    """

    def __init__(
        self,
        thing_type: str,
        service_name: str,
        vin: str,
        endpoint: str,
        port: int = 8883,
        use_wss: bool = False,
        client_id: Optional[str] = None,
        session_idle_timeout: float = 300.0,
        *,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        """
        Args:
            thing_type: 토픽의 {ThingType} (예: CGU).
            service_name: 이 서비스의 이름. 토픽의 {Service}에 해당.
            vin: 이 서비스가 담당하는 장비 VIN. 토픽의 {VIN}.
            endpoint: MQTT 브로커 엔드포인트.
            port: 브로커 포트 (TLS 기본 8883, WSS는 443).
            use_wss: True이면 WSS 전송 사용.
            client_id: MQTT 클라이언트 ID. None이면 service_name 기반으로 자동 생성.
            session_idle_timeout: 독점 세션 자동 해제 시간(초).
            logger: 로거 인스턴스.
        """
        self._thing_type = thing_type
        self._service_name = service_name
        self._vin = vin
        self._log = logger or logging.getLogger(__name__)

        self._client_id = client_id or f"{service_name}-{vin}"

        self._conn = Mqtt5ServerConnection(
            endpoint=endpoint,
            client_id=self._client_id,
            port=port,
            use_wss=use_wss,
            logger=self._log,
        )
        self._session = SessionManager(idle_timeout=session_idle_timeout)
        self._presence = PresenceMonitor()
        self._dispatcher = Dispatcher(
            conn=self._conn,
            session=self._session,
            thing_type=thing_type,
            service_name=service_name,
            vin=vin,
        )

        self._presence.on_disconnect(self._session.force_release)

        self._conn.set_message_callback(self._dispatch)

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_event: Optional[asyncio.Event] = None

    @classmethod
    def from_env(
        cls,
        thing_type: str,
        service_name: str,
        *,
        vin_env: str = "THING_VIN",
        endpoint_env: str = "MQTT_ENDPOINT",
        **kwargs: Any,
    ) -> "MaasServer":
        """
        환경변수에서 VIN과 엔드포인트를 읽어 서버를 생성한다.

        Greengrass Component 배포 환경에서 편리하게 사용할 수 있다.
        """
        vin = os.environ[vin_env]
        endpoint = os.environ[endpoint_env]
        return cls(
            thing_type=thing_type,
            service_name=service_name,
            vin=vin,
            endpoint=endpoint,
            **kwargs,
        )

    def action(
        self,
        action_name: str,
        *,
        streaming: bool = False,
        exclusive: bool = False,
        acquire_lock: bool = False,
        release_lock: bool = False,
    ) -> Callable:
        """
        RPC 핸들러 등록 데코레이터.

        ``action_name`` 은 클라이언트가 보내는 페이로드 ``"action"`` 값과 같아야 한다.

        Args:
            action_name: 페이로드 action과 동일한 식별자.
            streaming: True이면 generator/async generator 핸들러.
            exclusive: True이면 세션 Lock 보유 클라이언트만 호출 가능.
            acquire_lock: True이면 이 action 호출 시 세션 Lock 획득.
            release_lock: True이면 이 action 호출 시 세션 Lock 해제.
        """

        def decorator(func: Callable) -> Callable:
            self._dispatcher.register(
                action_name,
                func,
                streaming=streaming,
                exclusive=exclusive,
                acquire_lock=acquire_lock,
                release_lock=release_lock,
            )
            return func

        return decorator

    def subscribe(self, topic: str) -> Callable:
        """
        임의 토픽 구독 데코레이터.

        @server.subscribe("shadow/update/#")
        def on_shadow(topic: str, payload: bytes):
            ...
        """

        def decorator(func: Callable) -> Callable:
            self._dispatcher.register_pubsub(topic, func)
            return func

        return decorator

    def run(self) -> None:
        """서버를 시작하고 블로킹 실행한다."""
        asyncio.run(self._run_async())

    def stop(self) -> None:
        """실행 중인 서버를 종료한다."""
        if self._stop_event:
            if self._loop:
                self._loop.call_soon_threadsafe(self._stop_event.set)

    def publish(
        self,
        topic: str,
        payload: Any,
        qos: int = 1,
    ) -> None:
        """임의 토픽에 메시지 발행 (run() 실행 중에만 사용)."""
        if not self._loop:
            raise RuntimeError("서버가 실행 중이지 않습니다")
        asyncio.run_coroutine_threadsafe(
            self._conn.publish(topic, encode_payload(payload), qos=qos),
            self._loop,
        ).result(timeout=10.0)

    async def _run_async(self) -> None:
        """비동기 서버 실행 루프."""
        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()

        await self._conn.connect()
        self._log.info(
            "MaasServer 시작: thing_type=%s, service=%s, vin=%s",
            self._thing_type,
            self._service_name,
            self._vin,
        )

        sub_topic = topic_utils.build_subscription(
            self._thing_type, self._service_name, self._vin
        )
        await self._conn.subscribe(sub_topic, qos=1)
        self._log.info("요청 구독 완료: %s", sub_topic)

        for topic in self._presence.get_subscription_topics():
            await self._conn.subscribe(topic, qos=0)

        for topic in self._dispatcher._pubsub_handlers:
            await self._conn.subscribe(topic, qos=1)

        self._log.info("서버 실행 중. 종료하려면 KeyboardInterrupt 또는 stop() 호출.")
        try:
            await self._stop_event.wait()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await self._conn.disconnect()
            self._log.info("MaasServer 종료")

    def _dispatch(self, msg: IncomingMessage) -> None:
        """수신 메시지를 dispatcher로 라우팅."""
        if not self._loop:
            return

        if "$aws/events/presence" in msg.topic:
            self._presence.handle_message(msg.topic, msg.payload)
            return

        for pattern, callbacks in self._dispatcher._pubsub_handlers.items():
            if _topic_matches(pattern, msg.topic):
                for cb in callbacks:
                    try:
                        cb(msg.topic, msg.payload)
                    except Exception:
                        logger.exception("pub/sub 핸들러 오류: topic=%s", msg.topic)
                return

        asyncio.run_coroutine_threadsafe(
            self._dispatcher.handle(msg), self._loop
        )


def _topic_matches(pattern: str, topic: str) -> bool:
    """MQTT 와일드카드 토픽 패턴 매칭."""
    pattern_parts = pattern.split("/")
    topic_parts = topic.split("/")
    for i, pp in enumerate(pattern_parts):
        if pp == "#":
            return True
        if i >= len(topic_parts):
            return False
        if pp != "+" and pp != topic_parts[i]:
            return False
    return len(pattern_parts) == len(topic_parts)
