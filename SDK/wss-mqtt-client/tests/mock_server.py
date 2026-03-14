"""
WSS-MQTT API 사양을 따르는 Mock 서버.

통합 테스트용으로 SDK 클라이언트와 실제 통신한다.
로컬 테스트이므로 ws:// (비암호화)를 사용한다.
"""

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any, Optional

import websockets

logger = logging.getLogger(__name__)


class MockWssMqttServer:
    """
    WSS-MQTT API Mock 서버.

    - PUBLISH: ACK 200 반환
    - SUBSCRIBE: ACK 200 반환, Subscription Map 등록
    - UNSUBSCRIBE: ACK 200 반환, Subscription Map 제거
    - inject_subscription(): 테스트에서 SUBSCRIPTION 이벤트 주입
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 0,
        *,
        simulate_tgu: bool = False,
    ) -> None:
        self._host = host
        self._port = port
        self._simulate_tgu = simulate_tgu
        self._server: Optional[websockets.WebSocketServer] = None
        self._subscriptions: dict[str, list[tuple[Any, str]]] = (
            defaultdict(list)
        )
        self._received_publishes: list[tuple[str, Any]] = []
        self._lock = asyncio.Lock()

    @property
    def url(self) -> str:
        """클라이언트 연결 URL."""
        port = self._port
        if self._server and self._server.sockets:
            port = self._server.sockets[0].getsockname()[1]
        return f"ws://{self._host}:{port}"

    async def start(self) -> None:
        """서버 시작."""
        self._server = await websockets.serve(
            self._handle_connection,
            self._host,
            self._port,
        )
        if self._port == 0:
            self._port = self._server.sockets[0].getsockname()[1]
        logger.debug("Mock server started at %s", self.url)

    async def stop(self) -> None:
        """서버 종료."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    def _decode_message(self, raw: str | bytes) -> dict:
        """수신 메시지 디코딩. bytes는 MessagePack 우선."""
        if isinstance(raw, str):
            return json.loads(raw)
        try:
            import msgpack
            return msgpack.unpackb(raw, raw=False)
        except ImportError:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return json.loads(raw.decode("utf-8"))

    async def _handle_connection(self, websocket: Any) -> None:
        """클라이언트 연결 처리."""
        try:
            async for raw in websocket:
                try:
                    data = self._decode_message(raw)
                except (json.JSONDecodeError, ValueError):
                    await self._send_ack(
                        websocket, "unknown", 400, {"message": "Invalid message"}
                    )
                    continue
                await self._handle_request(websocket, data)
        except websockets.exceptions.ConnectionClosed:
            await self._cleanup_session(websocket)

    async def _handle_request(self, websocket: Any, data: dict[str, Any]) -> None:
        """요청 처리 및 ACK 응답."""
        action = data.get("action")
        req_id = data.get("req_id")
        topic = data.get("topic")
        payload = data.get("payload")

        if not req_id:
            await self._send_ack(
                websocket, "unknown", 400, {"message": "Missing req_id"}
            )
            return
        if not topic and action != "PUBLISH":
            await self._send_ack(
                websocket, req_id, 400, {"message": "Missing topic"}
            )
            return

        if action == "PUBLISH":
            async with self._lock:
                self._received_publishes.append((topic, payload))
            await self._send_ack(websocket, req_id, 200)
            if self._simulate_tgu:
                if "/command" in topic:
                    response_topic = topic.replace("/command", "/response")
                    await self.inject_subscription_to_topic(response_topic, payload)
                elif topic.endswith("/request") and isinstance(payload, dict):
                    # WMT/WMO RPC 패턴: payload에 response_topic, request_id, request
                    resp_topic = payload.get("response_topic")
                    req_id = payload.get("request_id")
                    req = payload.get("request", {})
                    if resp_topic and req_id:
                        action_name = req.get("action", "unknown")
                        result = {"action": action_name, "status": "ok"}
                        if action_name == "readDTC":
                            result["dtcList"] = []
                        rpc_response = {
                            "request_id": req_id,
                            "result": result,
                            "error": None,
                        }
                        await self.inject_subscription_to_topic(resp_topic, rpc_response)

        elif action == "SUBSCRIBE":
            async with self._lock:
                self._subscriptions[topic].append((websocket, req_id))
            await self._send_ack(websocket, req_id, 200)

        elif action == "UNSUBSCRIBE":
            # 사양 9.3: (topic, session)으로 제거 (req_id 무관)
            async with self._lock:
                subs = self._subscriptions.get(topic, [])
                self._subscriptions[topic] = [
                    (ws, rid) for ws, rid in subs if ws != websocket
                ]
                if not self._subscriptions[topic]:
                    del self._subscriptions[topic]
            await self._send_ack(websocket, req_id, 200)

        else:
            await self._send_ack(
                websocket, req_id, 400, {"message": f"Unknown action: {action}"}
            )

    async def _send_ack(
        self,
        websocket: Any,
        req_id: str,
        code: int,
        payload: Optional[Any] = None,
    ) -> None:
        """ACK 메시지 전송."""
        msg = {"event": "ACK", "req_id": req_id, "code": code}
        if payload is not None:
            msg["payload"] = payload
        await websocket.send(json.dumps(msg, ensure_ascii=False))

    async def inject_subscription(
        self, topic: str, req_id: str, payload: Any
    ) -> None:
        """
        구독자에게 SUBSCRIPTION 이벤트 전송 (테스트용).

        해당 topic을 req_id로 구독 중인 클라이언트에게 전달한다.
        """
        async with self._lock:
            subs = self._subscriptions.get(topic, [])
        msg = {
            "event": "SUBSCRIPTION",
            "req_id": req_id,
            "topic": topic,
            "payload": payload,
        }
        sent = False
        for ws, rid in subs:
            if rid == req_id:
                await ws.send(json.dumps(msg, ensure_ascii=False))
                sent = True
        if not sent:
            logger.warning(
                "inject_subscription: no subscriber for topic=%s req_id=%s",
                topic, req_id,
            )

    async def inject_subscription_to_topic(
        self, topic: str, payload: Any
    ) -> int:
        """
        topic을 구독 중인 모든 클라이언트에게 SUBSCRIPTION 전송.

        Returns:
            전송한 구독자 수
        """
        async with self._lock:
            subs = list(self._subscriptions.get(topic, []))
        msg_base = {"event": "SUBSCRIPTION", "topic": topic, "payload": payload}
        count = 0
        for ws, req_id in subs:
            msg = {**msg_base, "req_id": req_id}
            await ws.send(json.dumps(msg, ensure_ascii=False))
            count += 1
        return count

    async def _cleanup_session(self, websocket: Any) -> None:
        """연결 종료 시 구독 정리."""
        async with self._lock:
            for topic in list(self._subscriptions.keys()):
                self._subscriptions[topic] = [
                    (ws, rid) for ws, rid in self._subscriptions[topic]
                    if ws != websocket
                ]
                if not self._subscriptions[topic]:
                    del self._subscriptions[topic]

    def get_received_publishes(self) -> list[tuple[str, Any]]:
        """수신한 PUBLISH 목록 (테스트 검증용)."""
        return list(self._received_publishes)
