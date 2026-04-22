"""
RPC 레이어 (내부 모듈).

WMT/WMO 토픽 패턴 기반의 요청-응답 및 스트리밍 RPC 로직.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Optional

from .connection import (
    IncomingMessage,
    Mqtt5Connection,
    UP_ERROR_DETAIL,
    UP_IS_EOF,
    UP_REASON_CODE,
    build_publish_properties,
    decode_payload,
    encode_payload,
    new_correlation_id,
)
from .exceptions import (
    RpcServerError,
    RpcTimeoutError,
    StreamInterruptedError,
    NotAuthorizedError,
    ServerBusyError,
)
from .models import RpcResponse, StreamEvent
from . import topics

logger = logging.getLogger(__name__)

_REASON_SUCCESS = 0
_RC_NOT_AUTHORIZED = 0x87
_RC_SERVER_BUSY = 0x8A


def _raise_for_reason_code(rc: int, detail: str, service: str, action: str) -> None:
    """reason_code가 오류면 적절한 예외를 발생시킨다."""
    if rc == 0:
        return
    if rc == _RC_NOT_AUTHORIZED:
        raise NotAuthorizedError(detail)
    if rc == _RC_SERVER_BUSY:
        raise ServerBusyError(detail)
    raise RpcServerError(rc, detail)


def _ceil_positive_seconds(seconds: float) -> int:
    """
    양의 타임아웃(초)을 정수 초로 올림한다.

    ``timeout``이 정수 초와 같으면 그대로 두고, 소수 초면 한 칸 올린다.
    """
    t = float(seconds)
    i = int(t)
    return i if t <= i else i + 1


def _publish_message_expiry_for_call(
    qos: int,
    timeout: float,
    expiry: Optional[int],
) -> Optional[int]:
    """
    단일 RPC PUBLISH에 넣을 Message Expiry Interval(초)을 결정한다.

    QoS 1에서는 브로커가 오래된 요청을 무기한 전달하지 않도록, 클라이언트의
    ``timeout``(응답 대기 상한)과 동일한 값을 Expiry로 둔다(초 단위 올림, 최소 1).
    QoS 0에서는 ``expiry`` 인자만 선택 반영한다. QoS 0은 보통 비큐잉이라
    Expiry의 실효는 배포·브로커에 따라 제한적일 수 있다.

    Args:
        qos: MQTT QoS (0 또는 1).
        timeout: ``call``의 응답 대기 타임아웃(초).
        expiry: 호출자가 지정한 Expiry. QoS 0에서만 PUBLISH에 넣는다.

    Returns:
        ``build_publish_properties``에 넘길 정수 초, 또는 생략 시 ``None``.
    """
    if qos == 1:
        return max(1, _ceil_positive_seconds(timeout))
    return expiry


def _build_request_payload(action: str, params: Any) -> bytes:
    """
    action과 RPC params를 MQTT PUBLISH 본문(JSON bytes)으로 직렬화.

    JSON 객체에서는 ``action`` 키를 항상 선행(첫 필드)으로 둔다.
    params에 ``action`` 키가 있어도 인자 ``action``이 최종 값으로 쓰인다.
    """
    if isinstance(params, dict):
        rest = {k: v for k, v in params.items() if k != "action"}
        data = {"action": action, **rest}
    elif params is None:
        data = {"action": action}
    else:
        data = {
            "action": action,
            "data": params
            if not isinstance(params, bytes)
            else params.decode("utf-8", errors="replace"),
        }
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


class RpcManager:
    """
    RPC 요청-응답 및 스트리밍을 관리한다.

    pending_map: correlation_id → asyncio.Future (단일 응답 대기)
    stream_map: correlation_id → asyncio.Queue (스트림 이벤트 대기)
    """

    def __init__(self, conn: Mqtt5Connection, client_id: str) -> None:
        self._conn = conn
        self._client_id = client_id
        self._pending: dict[bytes, asyncio.Future] = {}
        self._streams: dict[bytes, asyncio.Queue] = {}
        self._lock = asyncio.Lock()

    async def setup_subscriptions(self) -> None:
        """
        연결 후 호출. 이 클라이언트의 모든 응답/이벤트 토픽을 와일드카드로 구독.
        """
        resp_topic = topics.build_response_wildcard(self._client_id)
        event_topic = topics.build_event_wildcard(self._client_id)
        await self._conn.subscribe(resp_topic, qos=1)
        await self._conn.subscribe(event_topic, qos=1)
        logger.debug("RPC 응답/이벤트 구독 완료: %s, %s", resp_topic, event_topic)

    def handle_incoming(self, msg: IncomingMessage) -> bool:
        """
        수신 메시지를 pending_map 또는 stream_map으로 라우팅.

        Returns:
            처리된 경우 True.
        """
        corr = msg.correlation_data
        if not corr:
            return False

        suffix = msg.topic.rsplit("/", 1)[-1] if "/" in msg.topic else ""

        if suffix == "response":
            return self._handle_response(corr, msg)
        if suffix == "event":
            return self._handle_event(corr, msg)
        return False

    def _handle_response(self, corr: bytes, msg: IncomingMessage) -> bool:
        rc = int(msg.user_props.get(UP_REASON_CODE, "0") or "0")
        detail = msg.user_props.get(UP_ERROR_DETAIL, "")
        is_eof = msg.user_props.get(UP_IS_EOF, "").lower() == "true"
        payload = decode_payload(msg.payload)

        # 스트림 완료 신호 처리
        if corr in self._streams:
            q = self._streams.get(corr)
            if q is not None:
                loop = asyncio.get_event_loop()
                if rc != 0:
                    exc = _make_error(rc, detail)
                    loop.call_soon_threadsafe(
                        lambda: asyncio.ensure_future(q.put(exc))
                    )
                else:
                    final = StreamEvent(
                        payload=payload, is_eof=True, correlation_id=corr
                    )
                    loop.call_soon_threadsafe(
                        lambda: asyncio.ensure_future(q.put(final))
                    )
            return True

        # 단일 응답 처리
        future = self._pending.pop(corr, None)
        if future is None or future.done():
            return False

        if rc != 0:
            future.set_exception(_make_error(rc, detail))
        else:
            future.set_result(
                RpcResponse(payload=payload, reason_code=rc, correlation_id=corr)
            )
        return True

    def _handle_event(self, corr: bytes, msg: IncomingMessage) -> bool:
        q = self._streams.get(corr)
        if q is None:
            return False
        payload = decode_payload(msg.payload)
        event = StreamEvent(payload=payload, is_eof=False, correlation_id=corr)
        loop = asyncio.get_event_loop()
        loop.call_soon_threadsafe(
            lambda: asyncio.ensure_future(q.put(event))
        )
        return True

    async def call(
        self,
        thing_type: str,
        service: str,
        action: str,
        vin: str,
        params: Any = None,
        *,
        qos: int = 1,
        timeout: float = 10.0,
        expiry: Optional[int] = None,
    ) -> RpcResponse:
        """
        단일 RPC 호출. 응답을 기다려 RpcResponse를 반환한다.

        Args:
            thing_type: 토픽의 {ThingType}.
            service: 토픽의 {Service}.
            action: 요청 JSON에 삽입할 action.
            vin: 토픽의 {VIN}.
            params: RPC 인자 (dict 권장). action 키는 SDK가 덮어쓴다.
            qos: MQTT QoS (0 또는 1).
            timeout: 응답 대기 타임아웃(초). QoS 1이면 Message Expiry도 이 값과
                맞춘다(초 단위 올림, 최소 1초).
            expiry: Message Expiry Interval(초). **QoS 0일 때만** PUBLISH에 넣는다.
                QoS 1에서는 무시되고 ``timeout``에서 유도된다. QoS 0은 보통 비큐잉이라
                실효는 제한적이다.

        Raises:
            RpcTimeoutError: 타임아웃 초과.
            RpcServerError: 서버 오류 응답.
        """
        corr_id = new_correlation_id()
        request_topic = topics.build_request(thing_type, service, vin, self._client_id)
        response_topic = topics.build_response(thing_type, service, vin, self._client_id)

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        async with self._lock:
            self._pending[corr_id] = future

        eff_expiry = _publish_message_expiry_for_call(qos, timeout, expiry)
        props = build_publish_properties(
            response_topic=response_topic,
            correlation_data=corr_id,
            message_expiry=eff_expiry,
        )
        raw = _build_request_payload(action, params)

        try:
            await self._conn.publish(request_topic, raw, qos=qos, properties=props)
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            async with self._lock:
                self._pending.pop(corr_id, None)
            raise RpcTimeoutError(service, action, timeout)
        except Exception:
            async with self._lock:
                self._pending.pop(corr_id, None)
            raise

    async def stream(
        self,
        thing_type: str,
        service: str,
        action: str,
        vin: str,
        params: Any = None,
        *,
        qos: int = 1,
    ) -> AsyncIterator[StreamEvent]:
        """
        스트리밍 RPC 호출. EOF 신호가 올 때까지 StreamEvent를 yield한다.

        Args:
            thing_type: 토픽의 {ThingType}.
            service: 토픽의 {Service}.
            action: 요청 JSON에 삽입할 action.
            vin: 토픽의 {VIN}.
            params: RPC 인자.
            qos: MQTT QoS.

        Yields:
            StreamEvent (is_eof=False인 청크들, 마지막은 is_eof=True).

        Raises:
            RpcServerError: 서버 오류.
            StreamInterruptedError: 연결 끊김.
        """
        corr_id = new_correlation_id()
        request_topic = topics.build_request(thing_type, service, vin, self._client_id)
        response_topic = topics.build_response(thing_type, service, vin, self._client_id)

        q: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self._streams[corr_id] = q

        props = build_publish_properties(
            response_topic=response_topic,
            correlation_data=corr_id,
        )
        raw = _build_request_payload(action, params)

        try:
            await self._conn.publish(request_topic, raw, qos=qos, properties=props)
            while True:
                item = await q.get()
                if isinstance(item, Exception):
                    raise item
                yield item
                if item.is_eof:
                    break
        finally:
            async with self._lock:
                self._streams.pop(corr_id, None)


def _make_error(rc: int, detail: str) -> RpcServerError:
    """reason_code에 맞는 예외 인스턴스 생성."""
    if rc == _RC_NOT_AUTHORIZED:
        return NotAuthorizedError(detail)
    if rc == _RC_SERVER_BUSY:
        return ServerBusyError(detail)
    return RpcServerError(rc, detail)
