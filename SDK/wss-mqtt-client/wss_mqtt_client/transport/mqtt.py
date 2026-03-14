"""
MQTT 전송 계층 (순수 MQTT 및 MQTT over WebSocket).

URL scheme에 따라 TCP 또는 WebSocket 전송을 사용한다.
- mqtt://, mqtts:// → TCP
- ws://, wss:// → WebSocket (AWS IoT Core, Mosquitto 9001 등)
"""

import asyncio
import json
import logging
import threading
from typing import Any, Callable, Optional
from urllib.parse import urlparse

from ..constants import CODE_OK, EVENT_ACK, EVENT_SUBSCRIPTION
from ..exceptions import WssConnectionError
from ..models import AckEvent, Action, SubscriptionEvent

logger = logging.getLogger(__name__)


def _parse_mqtt_url(url: str) -> dict[str, Any]:
    """
    MQTT/WebSocket URL을 파싱하여 paho-mqtt 연결 파라미터로 변환.

    Returns:
        host, port, transport, use_ssl, path (WebSocket용)
    """
    parsed = urlparse(url)
    scheme = (parsed.scheme or "mqtt").lower()
    host = parsed.hostname or "localhost"
    port = parsed.port
    path = parsed.path or "/"
    if path == "":
        path = "/"

    # scheme별 기본값
    schemes = {
        "mqtt": ("tcp", 1883, False),
        "mqtts": ("tcp", 8883, True),
        "ws": ("websockets", 80, False),
        "wss": ("websockets", 443, True),
    }
    transport, default_port, use_ssl = schemes.get(
        scheme, ("tcp", 1883, False)
    )
    port = port if port is not None else default_port

    return {
        "host": host,
        "port": port,
        "transport": transport,
        "use_ssl": use_ssl,
        "path": path if transport == "websockets" else None,
    }


class MqttTransport:
    """
    네이티브 MQTT 전송 계층.

    WssMqttClient의 Envelope 형식을 MQTT 프로토콜로 변환한다.
    URL scheme에 따라 TCP 또는 WebSocket을 사용한다.
    """

    def __init__(
        self,
        url: str,
        token: Optional[str] = None,
        *,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        """
        Args:
            url: mqtt://host:1883, ws://host:9001, wss://xxx.iot.amazonaws.com/mqtt 등
            token: JWT (username으로 전달, 초기 구현)
            logger: 로거 인스턴스
        """
        self._url = url
        self._token = token
        self._log = logger if logger is not None else logging.getLogger(__name__)
        self._params = _parse_mqtt_url(url)
        self._client: Any = None
        self._receive_callback: Optional[Callable[[Any], None]] = None
        self._on_connection_lost: Optional[Callable[[], None]] = None
        self._connected = False
        self._closed = False
        self._mid_to_req_id: dict[int, str] = {}
        self._topic_to_req_ids: dict[str, set[str]] = {}
        self._disconnected_event = threading.Event()
        self._connected_event = threading.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _safe_callback(self, msg: Any) -> None:
        """
        paho 스레드에서 호출 시, asyncio 이벤트 루프에 안전하게 전달.

        paho-mqtt 콜백은 별도 스레드에서 실행되므로, Future.set_result() 등이
        메인 루프를 제대로 깨우지 못할 수 있다. call_soon_threadsafe 사용.
        """
        if not self._receive_callback:
            return
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._receive_callback, msg)
        else:
            self._receive_callback(msg)

    def set_on_connection_lost(
        self, callback: Optional[Callable[[], None]]
    ) -> None:
        """연결 끊김 시 호출될 콜백 등록."""
        self._on_connection_lost = callback

    async def connect(self) -> None:
        """MQTT 브로커 연결."""
        self._loop = asyncio.get_running_loop()
        self._connected_event.clear()
        try:
            await asyncio.to_thread(self._do_connect)
            ok = await asyncio.to_thread(
                self._connected_event.wait, 10
            )
            if not ok:
                raise WssConnectionError("연결 대기 타임아웃")
        except Exception as e:
            if self._client:
                try:
                    self._client.loop_stop()
                except Exception:
                    pass
            raise WssConnectionError(f"연결 실패: {e}") from e

    def _do_connect(self) -> None:
        """동기 연결 (스레드에서 실행)."""
        import paho.mqtt.client as mqtt

        transport = self._params["transport"]
        self._client = mqtt.Client(
            transport=transport,
            protocol=mqtt.MQTTv311,
        )
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_publish = self._on_publish
        self._client.on_subscribe = self._on_subscribe
        self._client.on_unsubscribe = self._on_unsubscribe
        self._client.on_message = self._on_message

        host = self._params["host"]
        port = self._params["port"]
        use_ssl = self._params["use_ssl"]

        if self._token:
            self._client.username_pw_set(self._token, "")

        if transport == "websockets":
            path = self._params.get("path") or "/mqtt"
            self._client.ws_set_options(path=path)
        if use_ssl:
            self._client.tls_set()

        self._disconnected_event.clear()
        self._client.connect(host, port, keepalive=60)
        self._client.loop_start()

    def _on_connect(
        self, _client: Any, _userdata: Any, _flags: Any, rc: int
    ) -> None:
        """연결 완료 콜백."""
        if rc == 0:
            self._connected = True
            self._closed = False
            self._connected_event.set()
            self._log.debug("MQTT connected: %s:%s", self._params["host"], self._params["port"])
        else:
            self._log.warning("MQTT connect failed: rc=%s", rc)

    def _on_disconnect(
        self, _client: Any, _userdata: Any, rc: int, properties: Any = None
    ) -> None:
        """연결 끊김 콜백."""
        self._connected = False
        self._disconnected_event.set()
        if not self._closed:
            self._log.debug("MQTT disconnected: rc=%s", rc)
            if self._on_connection_lost:
                try:
                    self._on_connection_lost()
                except Exception:  # noqa: BLE001
                    self._log.exception("on_connection_lost 콜백 오류")

    def _on_publish(
        self, _client: Any, _userdata: Any, mid: int
    ) -> None:
        """PUBACK 수신 (발행 완료)."""
        req_id = self._mid_to_req_id.pop(mid, None)
        if req_id:
            ack = AckEvent(
                event=EVENT_ACK,
                req_id=req_id,
                code=CODE_OK,
                payload=None,
            )
            self._safe_callback(ack)

    def _on_subscribe(
        self,
        _client: Any,
        _userdata: Any,
        mid: int,
        _granted_qos: Any,
    ) -> None:
        """SUBACK 수신."""
        req_id = self._mid_to_req_id.pop(mid, None)
        if req_id:
            ack = AckEvent(
                event=EVENT_ACK,
                req_id=req_id,
                code=CODE_OK,
                payload=None,
            )
            self._safe_callback(ack)

    def _on_unsubscribe(
        self, _client: Any, _userdata: Any, mid: int
    ) -> None:
        """UNSUBACK 수신."""
        req_id = self._mid_to_req_id.pop(mid, None)
        if req_id:
            ack = AckEvent(
                event=EVENT_ACK,
                req_id=req_id,
                code=CODE_OK,
                payload=None,
            )
            self._safe_callback(ack)

    def _on_message(
        self, _client: Any, _userdata: Any, msg: Any
    ) -> None:
        """구독 토픽 메시지 수신 (PUBLISH)."""
        topic = msg.topic
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = msg.payload

        req_ids = self._topic_to_req_ids.get(topic, set())
        if not req_ids:
            self._log.warning(
                "미등록 토픽의 메시지 수신, 폐기: topic=%s",
                topic,
            )
            return
        for req_id in req_ids:
            event = SubscriptionEvent(
                event=EVENT_SUBSCRIPTION,
                req_id=req_id,
                topic=topic,
                payload=payload,
            )
            self._safe_callback(event)

    def set_receive_callback(self, callback: Callable[[Any], None]) -> None:
        """수신 메시지 콜백 등록."""
        self._receive_callback = callback

    def _parse_envelope(self, data: str | bytes) -> dict:
        """Envelope 파싱. bytes는 MessagePack 우선, str은 JSON."""
        if isinstance(data, str):
            return json.loads(data)
        try:
            import msgpack
            return msgpack.unpackb(data, raw=False)
        except ImportError:
            return json.loads(data.decode("utf-8"))
        except Exception:
            return json.loads(data.decode("utf-8"))

    async def send(self, data: str | bytes) -> None:
        """
        Envelope 전송. JSON 또는 MessagePack 파싱 후 MQTT publish/subscribe/unsubscribe 실행.
        """
        envelope = self._parse_envelope(data)
        action = envelope.get("action")
        req_id = envelope.get("req_id")
        topic = envelope.get("topic")
        payload = envelope.get("payload")

        if not action or not req_id or not topic:
            raise ValueError("Envelope에 action, req_id, topic 필수")

        await asyncio.to_thread(
            self._do_send,
            action=action,
            req_id=req_id,
            topic=topic,
            payload=payload,
        )

    def _do_send(
        self,
        action: str,
        req_id: str,
        topic: str,
        payload: Any,
    ) -> None:
        """동기 전송 (스레드에서 실행)."""
        if not self._client or not self._connected:
            raise WssConnectionError("연결되지 않음")

        if action == Action.PUBLISH.value:
            if payload is None:
                body = ""
            elif isinstance(payload, bytes):
                body = payload
            else:
                body = json.dumps(payload, ensure_ascii=False)
            result = self._client.publish(topic, body, qos=1)
            mid = getattr(result, "mid", None)
            if mid is not None:
                self._mid_to_req_id[mid] = req_id
            else:
                ack = AckEvent(
                    event=EVENT_ACK,
                    req_id=req_id,
                    code=CODE_OK,
                    payload=None,
                )
                self._safe_callback(ack)
        elif action == Action.SUBSCRIBE.value:
            already_subscribed = topic in self._topic_to_req_ids
            if topic not in self._topic_to_req_ids:
                self._topic_to_req_ids[topic] = set()
            self._topic_to_req_ids[topic].add(req_id)
            if already_subscribed:
                ack = AckEvent(
                    event=EVENT_ACK,
                    req_id=req_id,
                    code=CODE_OK,
                    payload=None,
                )
                self._safe_callback(ack)
            else:
                result = self._client.subscribe(topic, qos=1)
                mid = result[1] if isinstance(result, tuple) else getattr(result, "mid", None)
                if mid is not None:
                    self._mid_to_req_id[mid] = req_id
                else:
                    ack = AckEvent(
                        event=EVENT_ACK,
                        req_id=req_id,
                        code=CODE_OK,
                        payload=None,
                    )
                    self._safe_callback(ack)
        elif action == Action.UNSUBSCRIBE.value:
            # MQTT UNSUBSCRIBE는 토픽 전체 해제. envelope의 req_id는 UNSUBACK용.
            # _topic_to_req_ids에서 해당 토픽을 제거해야 재구독 시 paho subscribe 전송됨.
            if topic in self._topic_to_req_ids:
                del self._topic_to_req_ids[topic]
            result = self._client.unsubscribe(topic)
            mid = result[1] if isinstance(result, tuple) else getattr(result, "mid", None)
            if mid is not None:
                self._mid_to_req_id[mid] = req_id
            else:
                ack = AckEvent(
                    event=EVENT_ACK,
                    req_id=req_id,
                    code=CODE_OK,
                    payload=None,
                )
                self._safe_callback(ack)
        else:
            raise ValueError(f"Unknown action: {action}")

    async def disconnect(self) -> None:
        """연결 종료."""
        self._closed = True
        if self._client:
            await asyncio.to_thread(self._do_disconnect)
            self._client = None

    def _do_disconnect(self) -> None:
        """동기 종료."""
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            self._log.debug("MQTT disconnected")

    async def receive_loop(self) -> None:
        """수신 루프. 연결 끊김까지 대기."""
        await asyncio.to_thread(self._disconnected_event.wait)

    @property
    def is_connected(self) -> bool:
        """연결 상태."""
        return self._connected and not self._closed
