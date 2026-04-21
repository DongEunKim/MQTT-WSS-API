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


def _build_request_payload(action: str, payload: Any) -> bytes:
    """
    action을 페이로드에 주입하여 직렬화.

    action은 항상 최종 값이 되도록 payload dict보다 후순위로 덮어쓴다.
    """
    if isinstance(payload, dict):
        data = {**payload, "action": action}
    elif payload is None:
        data = {"action": action}
    else:
        data = {
            "action": action,
            "data": payload
            if not isinstance(payload, bytes)
            else payload.decode("utf-8", errors="replace"),
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
        payload: Any = None,
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
            action: 페이로드에 삽입할 action.
            vin: 토픽의 {VIN}.
            payload: 추가 페이로드 (dict 권장). action 필드는 SDK가 자동 삽입.
            qos: MQTT QoS (0 또는 1).
            timeout: 응답 대기 타임아웃(초).
            expiry: Message Expiry Interval(초). 패턴 D용.

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

        props = build_publish_properties(
            response_topic=response_topic,
            correlation_data=corr_id,
            message_expiry=expiry,
        )
        raw = _build_request_payload(action, payload)

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
        payload: Any = None,
        *,
        qos: int = 1,
    ) -> AsyncIterator[StreamEvent]:
        """
        스트리밍 RPC 호출. EOF 신호가 올 때까지 StreamEvent를 yield한다.

        Args:
            thing_type: 토픽의 {ThingType}.
            service: 토픽의 {Service}.
            action: 페이로드에 삽입할 action.
            vin: 토픽의 {VIN}.
            payload: 추가 페이로드.
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
        raw = _build_request_payload(action, payload)

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
