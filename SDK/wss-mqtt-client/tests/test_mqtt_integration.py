"""
MQTT Transport 통합 테스트.

Mosquitto 브로커가 필요하다. docker compose up -d로 실행 후 테스트.
브로커 미실행 시 테스트는 스킵된다.
"""

import asyncio

import pytest
import pytest_asyncio

from wss_mqtt_client import WssMqttClientAsync, WssConnectionError

# MQTT 브로커 URL (환경변수로 오버라이드 가능)
MQTT_TCP_URL = "mqtt://localhost:1883"
MQTT_WS_URL = "ws://localhost:9001"


def _is_mqtt_broker_available(url: str) -> bool:
    """MQTT 브로커 연결 가능 여부 확인."""
    try:
        import socket
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or (1883 if "mqtt" in (parsed.scheme or "") else 9001)
        with socket.create_connection((host, port), timeout=2):
            return True
    except (OSError, ValueError):
        return False


@pytest.fixture(scope="module")
def mqtt_tcp_available():
    """MQTT TCP 브로커 사용 가능 여부."""
    return _is_mqtt_broker_available(MQTT_TCP_URL)


@pytest.fixture(scope="module")
def mqtt_ws_available():
    """MQTT WebSocket 브로커 사용 가능 여부."""
    return _is_mqtt_broker_available(MQTT_WS_URL)


@pytest.mark.asyncio
async def test_mqtt_transport_publish_tcp(mqtt_tcp_available: bool) -> None:
    """transport=mqtt, mqtt:// TCP로 발행."""
    if not mqtt_tcp_available:
        pytest.skip("MQTT 브로커(localhost:1883) 미실행")

    async with WssMqttClientAsync(
        url=MQTT_TCP_URL,
        transport="mqtt",
    ) as client:
        await client.publish("test/mqtt/tcp", {"key": "value"})


@pytest.mark.asyncio
async def test_mqtt_transport_publish_subscribe_tcp(
    mqtt_tcp_available: bool,
) -> None:
    """transport=mqtt TCP로 발행 후 구독 수신."""
    if not mqtt_tcp_available:
        pytest.skip("MQTT 브로커(localhost:1883) 미실행")

    topic = "test/mqtt/sub_tcp"
    payload = {"status": "ok", "transport": "tcp"}

    async with WssMqttClientAsync(url=MQTT_TCP_URL, transport="mqtt") as client:
        async with client.subscribe(topic) as stream:
            await client.publish(topic, payload)
            async for event in stream:
                assert event.payload == payload
                assert event.topic == topic
                break


@pytest.mark.asyncio
async def test_mqtt_transport_publish_subscribe_ws(
    mqtt_ws_available: bool,
) -> None:
    """transport=mqtt, ws:// WebSocket으로 발행·구독."""
    if not mqtt_ws_available:
        pytest.skip("MQTT WebSocket 브로커(localhost:9001) 미실행")

    topic = "test/mqtt/sub_ws"
    payload = {"status": "ok", "transport": "ws"}

    async with WssMqttClientAsync(url=MQTT_WS_URL, transport="mqtt") as client:
        async with client.subscribe(topic) as stream:
            await client.publish(topic, payload)
            async for event in stream:
                assert event.payload == payload
                assert event.topic == topic
                break


@pytest.mark.asyncio
async def test_mqtt_transport_invalid_raises() -> None:
    """알 수 없는 transport 문자열 시 ValueError."""
    with pytest.raises(ValueError, match="알 수 없는 transport"):
        WssMqttClientAsync(url="mqtt://localhost:1883", transport="invalid")
