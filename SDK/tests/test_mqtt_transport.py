"""
MqttTransport 단위 테스트.

실제 브로커 없이 URL 파싱 및 초기화를 검증한다.
"""

import pytest

from wss_mqtt_client.transport.mqtt import _parse_mqtt_url, MqttTransport


def test_parse_mqtt_url_tcp() -> None:
    """mqtt:// URL 파싱."""
    p = _parse_mqtt_url("mqtt://localhost:1883")
    assert p["host"] == "localhost"
    assert p["port"] == 1883
    assert p["transport"] == "tcp"
    assert p["use_ssl"] is False


def test_parse_mqtt_url_websocket() -> None:
    """ws:// URL 파싱."""
    p = _parse_mqtt_url("ws://localhost:9001")
    assert p["host"] == "localhost"
    assert p["port"] == 9001
    assert p["transport"] == "websockets"
    assert p["use_ssl"] is False


def test_parse_mqtt_url_wss() -> None:
    """wss:// URL 파싱 (AWS IoT Core 형식)."""
    p = _parse_mqtt_url("wss://xxx.iot.ap-northeast-2.amazonaws.com/mqtt")
    assert p["host"] == "xxx.iot.ap-northeast-2.amazonaws.com"
    assert p["port"] == 443
    assert p["transport"] == "websockets"
    assert p["use_ssl"] is True
    assert p["path"] == "/mqtt"


def test_parse_mqtt_url_default_port() -> None:
    """기본 포트 적용."""
    p = _parse_mqtt_url("mqtt://broker.example.com")
    assert p["port"] == 1883
    p2 = _parse_mqtt_url("wss://broker.example.com")
    assert p2["port"] == 443


def test_mqtt_transport_init() -> None:
    """MqttTransport 초기화."""
    t = MqttTransport("mqtt://localhost:1883")
    assert t._params["host"] == "localhost"
    assert t._params["port"] == 1883
    assert not t.is_connected
