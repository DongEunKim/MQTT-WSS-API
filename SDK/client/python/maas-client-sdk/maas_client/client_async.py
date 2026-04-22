"""
MaasClientAsync: MQTT 5.0 비동기 클라이언트 (고급 인터페이스).
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Optional

from .auth import TokenProvider
from .connection import Mqtt5Connection, IncomingMessage
from ._rpc import RpcManager
from ._pubsub import PubSubManager, MessageHandler
from .models import RpcResponse, StreamEvent, Message

logger = logging.getLogger(__name__)


class MaasClientAsync:
    """
    MQTT 5.0 비동기 클라이언트.

    기본은 WSS+TLS이며, ``use_wss=False`` 로 로컬 TCP 브로커에도 연결 가능하다.
    RPC 호출(call, stream, exclusive_session)과 단순 pub/sub를 지원한다.
    asyncio 환경에서 직접 사용하거나, MaasClient(동기)의 내부 구현으로 사용된다.

    생성자에 ``thing_type``, ``service``, ``vin`` 을 모두 넣으면
    ``call(action[, params])`` / ``stream(action[, params])`` /
    무인자 ``exclusive_session()`` 으로 짧게 호출할 수 있다.
    라우팅을 매번 지정하려면 ``call(thing_type, service, action, vin[, params])`` 형태를 쓴다.
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
            client_id: MQTT 클라이언트 ID. 응답 토픽 라우팅에 사용.
            token_provider: 연결 시마다 호출되어 MQTT username 문자열을 반환.
                None이면 인증 없이 연결. ``HttpTokenSource`` 등 ``__call__`` 제공자 가능.
            port: 브로커 포트. None이면 ``use_wss`` 에 따라 443(WSS) 또는 1883(TCP).
            use_wss: True면 WebSocket+TLS, False면 TCP(로컬 Mosquitto 등).
            thing_type: 바인딩 시 토픽 ThingType. ``service``, ``vin`` 과 함께 세트로 지정.
            service: 바인딩 시 서비스 이름.
            vin: 바인딩 시 대상 VIN.
            logger: 로거 인스턴스.
        """
        bound = (thing_type, service, vin)
        if any(x is not None for x in bound) and not all(x is not None for x in bound):
            raise ValueError(
                "thing_type, service, vin 은 세 값 모두 생략하거나 모두 지정해야 합니다."
            )

        self._endpoint = endpoint
        self._client_id = client_id
        self._token_provider = token_provider
        eff_port = port if port is not None else (443 if use_wss else 1883)
        self._port = eff_port
        self._use_wss = use_wss
        self._thing_type = thing_type
        self._service = service
        self._vin = vin
        self._log = logger or logging.getLogger(__name__)

        self._conn = Mqtt5Connection(
            endpoint=endpoint,
            client_id=client_id,
            token=None,
            port=eff_port,
            use_wss=use_wss,
            logger=self._log,
        )
        self._rpc = RpcManager(self._conn, client_id)
        self._pubsub = PubSubManager(self._conn)

        self._conn.set_message_callback(self._dispatch_message)

    def _is_bound(self) -> bool:
        """생성자에 thing_type, service, vin 이 모두 설정되었는지."""
        return (
            self._thing_type is not None
            and self._service is not None
            and self._vin is not None
        )

    def _bound_routing(self) -> tuple[str, str, str]:
        """바인딩된 thing_type, service, vin. 없으면 ValueError."""
        if not self._is_bound():
            raise ValueError(
                "생성자에 thing_type, service, vin을 모두 지정한 경우에만 "
                "call(action[, params]), stream(action[, params]), "
                "exclusive_session() 무인자 형태를 사용할 수 있습니다. "
                "그렇지 않으면 call(thing_type, service, action, vin[, params])처럼 "
                "네 축을 인자로 넘기세요."
            )
        return self._thing_type, self._service, self._vin

    def _parse_rpc_routing(
        self,
        *args,
        params: Any = None,
        for_stream: bool = False,
    ) -> tuple[str, str, str, str, Any]:
        """
        call/stream 공통: 인자 개수에 따라 바인딩 단축 형식과 전체 라우팅 형식을 구분한다.

        - 바인딩: ``(action,)`` 또는 ``(action, params_pos)``
        - 비바인딩/명시: ``(thing_type, service, action, vin)`` 또는
          ``(thing_type, service, action, vin, params_pos)``
        """
        n = len(args)
        if n in (1, 2):
            thing_type, service, vin = self._bound_routing()
            action = args[0]
            if n == 2:
                if params is not None:
                    raise TypeError(
                        "params를 두 번째 위치 인자와 keyword 동시에 지정할 수 없습니다."
                    )
                eff_params = args[1]
            else:
                eff_params = params
            return thing_type, service, action, vin, eff_params

        if n == 4:
            tt, sv, act, vn = args
            return tt, sv, act, vn, params

        if n == 5:
            if params is not None:
                raise TypeError(
                    "다섯 번째 위치 인자로 params를 넘기면 keyword params는 사용할 수 없습니다."
                )
            return args[0], args[1], args[2], args[3], args[4]

        ctx = "stream" if for_stream else "call"
        raise TypeError(
            f"{ctx}() 인자는 (action[, params]) — 생성자 바인딩 필요 — 또는 "
            f"(thing_type, service, action, vin[, params]) 여야 합니다. "
            f"지금은 인자가 {n}개입니다."
        )

    async def connect(self) -> None:
        """MQTT 브로커에 연결하고 응답 토픽을 구독한다."""
        token: Optional[str] = None
        if self._token_provider is not None:
            token = self._token_provider()
        self._conn.set_token(token)
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
        *args,
        params: Any = None,
        qos: int = 1,
        timeout: float = 10.0,
        expiry: Optional[int] = None,
    ) -> RpcResponse:
        """
        단일 RPC 호출.

        **생성자 바인딩** (``thing_type``, ``service``, ``vin`` 모두 지정):

        - ``await client.call("get")``
        - ``await client.call("get", {"path": "..."})``
        - ``await client.call("get", params={...})``

        **명시 라우팅** (플릿 등):

        - ``await client.call("CGU", "viss", "get", "VIN-1", params={...})``
        - ``await client.call("CGU", "viss", "get", "VIN-1", {"path": "..."})`` (params 다섯 번째 위치)

        Args:
            args: 위 패턴 중 하나.
            params: RPC 인자. 네 축만 위치로 줄 때는 keyword로 전달. 위치 params와 동시 사용 불가.
            qos: MQTT QoS (0 또는 1).
            timeout: 응답 대기 타임아웃(초).
            expiry: Message Expiry Interval(초). 패턴 D(시한성 명령)에 사용.

        Returns:
            RpcResponse (응답 본문은 ``payload`` 필드, MQTT 페이로드와 용어 구분).

        Raises:
            TypeError: 인자 개수·조합이 맞지 않을 때.
            ValueError: 바인딩 단축 형식인데 생성자에 라우팅이 없을 때.
        """
        thing_type, service, action, vin, eff_params = self._parse_rpc_routing(
            *args, params=params, for_stream=False
        )
        return await self._rpc.call(
            thing_type=thing_type,
            service=service,
            action=action,
            vin=vin,
            params=eff_params,
            qos=qos,
            timeout=timeout,
            expiry=expiry,
        )

    async def stream(
        self,
        *args,
        params: Any = None,
        qos: int = 1,
    ) -> AsyncIterator[StreamEvent]:
        """
        스트리밍 RPC 호출. async for 로 청크를 수신한다.

        인자 규칙은 ``call`` 과 동일 (바인딩: ``action[, params]``,
        명시: ``thing_type, service, action, vin[, params]``).

        서버는 청크를 WMO/.../event 토픽으로 발행하고,
        완료 신호를 WMO/.../response 토픽으로 발행한다.
        """
        thing_type, service, action, vin, eff_params = self._parse_rpc_routing(
            *args, params=params, for_stream=True
        )
        async for event in self._rpc.stream(
            thing_type=thing_type,
            service=service,
            action=action,
            vin=vin,
            params=eff_params,
            qos=qos,
        ):
            yield event

    def exclusive_session(
        self,
        *thing_svc_vin: str,
        acquire_action: str = "session_start",
        release_action: str = "session_stop",
        timeout: float = 15.0,
    ) -> "ExclusiveSessionContext":
        """
        독점 세션 컨텍스트 매니저 (패턴 E).

        인자 없음: 생성자에 지정한 thing_type, service, vin 사용.

        인자 세 개: (thing_type, service, vin) 명시 (고급).

        async with client.exclusive_session() as session:
            await session.call(action="ecu_reset", params={})
        """
        if len(thing_svc_vin) == 0:
            thing_type, service, vin = self._bound_routing()
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
            self._thing_type,
            self._service,
            self._acquire_action,
            self._vin,
            qos=1,
            timeout=self._timeout,
        )
        return self

    async def __aexit__(self, exc_type: Any, *args: Any) -> None:
        try:
            await self._client.call(
                self._thing_type,
                self._service,
                self._release_action,
                self._vin,
                qos=1,
                timeout=self._timeout,
            )
        except Exception:
            logger.warning("세션 해제 RPC 실패", exc_info=True)

    async def call(
        self,
        action: str,
        params: Any = None,
        *,
        qos: int = 1,
        timeout: Optional[float] = None,
    ) -> RpcResponse:
        """세션 내에서 RPC 호출."""
        return await self._client.call(
            self._thing_type,
            self._service,
            action,
            self._vin,
            params=params,
            qos=qos,
            timeout=timeout or self._timeout,
        )
