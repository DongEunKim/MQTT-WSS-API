"""
RPC 디스패처 (내부 모듈).

수신된 요청 토픽과 페이로드를 파싱하여
등록된 핸들러 함수로 라우팅하고, 응답을 자동 발행한다.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import traceback
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .connection import (
    Mqtt5ServerConnection,
    IncomingMessage,
    build_response_properties,
    encode_payload,
)
from .context import RpcContext
from .exceptions import HandlerError
from .session import SessionManager
from . import topics as topic_utils

logger = logging.getLogger(__name__)

# MQTT5 User Property reason_code 값
_RC_UNSPECIFIED = 0x80
_RC_PAYLOAD_INVALID = 0x99
_RC_SERVER_BUSY = 0x8A

HandlerFunc = Callable[[RpcContext], Any]


@dataclass
class HandlerEntry:
    """등록된 핸들러 메타데이터."""

    func: HandlerFunc
    streaming: bool
    exclusive: bool
    acquire_lock: bool
    release_lock: bool


class Dispatcher:
    """
    요청 토픽 + 페이로드 라우터.

    페이로드의 ``action`` 값으로 핸들러를 등록·조회한다.
    토픽의 ``{Service}`` 는 ``MaasServer.service_name`` 과 일치할 때만 처리한다.
    응답은 SDK가 자동 발행한다.
    """

    def __init__(
        self,
        conn: Mqtt5ServerConnection,
        session: SessionManager,
        thing_type: str,
        service_name: str,
        vin: str,
    ) -> None:
        self._conn = conn
        self._session = session
        self._thing_type = thing_type
        self._service_name = service_name
        self._vin = vin
        self._handlers: dict[str, HandlerEntry] = {}
        self._pubsub_handlers: dict[str, list[Callable]] = {}

    def register(
        self,
        action: str,
        func: HandlerFunc,
        *,
        streaming: bool = False,
        exclusive: bool = False,
        acquire_lock: bool = False,
        release_lock: bool = False,
    ) -> None:
        """핸들러 등록 (action 이름은 페이로드 ``action`` 과 동일해야 함)."""
        if action in self._handlers:
            logger.warning("핸들러 중복 등록: action=%s", action)
        self._handlers[action] = HandlerEntry(
            func=func,
            streaming=streaming,
            exclusive=exclusive,
            acquire_lock=acquire_lock,
            release_lock=release_lock,
        )
        logger.debug("핸들러 등록: action=%s", action)

    def register_pubsub(self, topic: str, func: Callable) -> None:
        """pub/sub 핸들러 등록."""
        if topic not in self._pubsub_handlers:
            self._pubsub_handlers[topic] = []
        self._pubsub_handlers[topic].append(func)

    async def handle(self, msg: IncomingMessage) -> None:
        """수신 메시지 처리."""
        parsed = topic_utils.parse_request(msg.topic)
        if not parsed:
            return

        if (
            parsed.thing_type != self._thing_type
            or parsed.service != self._service_name
            or parsed.vin != self._vin
        ):
            logger.debug(
                "이 서버와 일치하지 않는 토픽 무시: %s (기대: %s/%s/%s)",
                msg.topic,
                self._thing_type,
                self._service_name,
                self._vin,
            )
            return

        try:
            payload_dict = json.loads(msg.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            await self._reply_error(msg, _RC_PAYLOAD_INVALID, "페이로드 JSON 파싱 실패")
            return

        action = payload_dict.pop("action", None)
        if not action:
            await self._reply_error(msg, _RC_PAYLOAD_INVALID, "action 필드 누락")
            return

        entry = self._handlers.get(action)
        if not entry:
            logger.warning("핸들러 없음: action=%s", action)
            await self._reply_error(msg, 0x90, f"미지원 action: {action}")
            return

        ctx = RpcContext(
            thing_type=parsed.thing_type,
            service=parsed.service,
            action=action,
            vin=parsed.vin,
            client_id=parsed.client_id,
            payload=payload_dict,
            correlation_id=msg.correlation_data,
            response_topic=msg.response_topic,
            user_props=dict(msg.user_props),
        )

        if entry.acquire_lock:
            if not self._session.acquire(ctx.vin, ctx.client_id):
                owner = self._session.get_owner(ctx.vin)
                await self._reply_error(
                    msg, _RC_SERVER_BUSY, f"세션 점유 중: {owner}"
                )
                return

        if entry.release_lock:
            self._session.release(ctx.vin, ctx.client_id)

        if entry.exclusive and not entry.acquire_lock:
            owner = self._session.get_owner(ctx.vin)
            if owner and owner != ctx.client_id:
                await self._reply_error(
                    msg, _RC_SERVER_BUSY, f"세션 점유 중: {owner}"
                )
                return

        if entry.streaming:
            await self._invoke_streaming(ctx, entry.func)
        else:
            await self._invoke_single(ctx, entry.func)

    async def _invoke_single(self, ctx: RpcContext, func: HandlerFunc) -> None:
        """단일 응답 핸들러 실행."""
        try:
            if inspect.iscoroutinefunction(func):
                result = await func(ctx)
            else:
                result = await asyncio.to_thread(func, ctx)

            await self._reply_success(ctx, result)

        except HandlerError as exc:
            await self._reply_error_ctx(ctx, exc.reason_code, str(exc))
        except Exception:
            logger.exception(
                "핸들러 미처리 예외: action=%s", ctx.action
            )
            await self._reply_error_ctx(ctx, _RC_UNSPECIFIED, "handler error")

    async def _invoke_streaming(self, ctx: RpcContext, func: HandlerFunc) -> None:
        """스트리밍 핸들러 실행. 청크를 event 토픽으로 발행."""
        event_topic = topic_utils.build_event(
            ctx.thing_type, ctx.service, ctx.vin, ctx.client_id
        )
        try:
            if inspect.isasyncgenfunction(func):
                gen = func(ctx)
                async for chunk in gen:
                    await self._publish_event(event_topic, ctx.correlation_id, chunk)
            elif inspect.isgeneratorfunction(func):
                for chunk in func(ctx):
                    await self._publish_event(event_topic, ctx.correlation_id, chunk)
            else:
                raise TypeError(
                    f"streaming=True 핸들러는 generator 또는 async generator이어야 한다: {func}"
                )

            await self._reply_success(ctx, None, is_eof=True)

        except HandlerError as exc:
            await self._reply_error_ctx(ctx, exc.reason_code, str(exc))
        except Exception:
            logger.exception(
                "스트리밍 핸들러 예외: action=%s", ctx.action
            )
            await self._reply_error_ctx(ctx, _RC_UNSPECIFIED, "streaming error")

    async def _publish_event(
        self,
        event_topic: str,
        correlation_id: Optional[bytes],
        chunk: Any,
    ) -> None:
        """청크를 event 토픽으로 발행."""
        props = build_response_properties(correlation_id, reason_code=0)
        raw = encode_payload(chunk)
        await self._conn.publish(event_topic, raw, qos=1, properties=props)

    async def _reply_success(
        self,
        ctx: RpcContext,
        result: Any,
        is_eof: bool = False,
    ) -> None:
        """성공 응답 발행."""
        if not ctx.response_topic:
            return
        props = build_response_properties(
            ctx.correlation_id, reason_code=0, is_eof=is_eof
        )
        raw = encode_payload(result)
        await self._conn.publish(ctx.response_topic, raw, qos=1, properties=props)

    async def _reply_error(
        self,
        msg: IncomingMessage,
        reason_code: int,
        detail: str,
    ) -> None:
        """IncomingMessage 기반 오류 응답 발행."""
        if not msg.response_topic:
            return
        props = build_response_properties(
            msg.correlation_data, reason_code=reason_code, error_detail=detail
        )
        await self._conn.publish(msg.response_topic, b"", qos=1, properties=props)

    async def _reply_error_ctx(
        self,
        ctx: RpcContext,
        reason_code: int,
        detail: str,
    ) -> None:
        """RpcContext 기반 오류 응답 발행."""
        if not ctx.response_topic:
            return
        props = build_response_properties(
            ctx.correlation_id, reason_code=reason_code, error_detail=detail
        )
        await self._conn.publish(ctx.response_topic, b"", qos=1, properties=props)
