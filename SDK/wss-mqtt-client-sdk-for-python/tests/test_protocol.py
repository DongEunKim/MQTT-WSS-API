"""
프로토콜 계층 단위 테스트.
"""

import pytest

from wss_mqtt_client.models import Action
from wss_mqtt_client.protocol import (
    build_request,
    decode_message,
    encode_request,
    generate_req_id,
)


def test_generate_req_id() -> None:
    """req_id는 UUID 형식 문자열."""
    rid = generate_req_id()
    assert isinstance(rid, str)
    assert len(rid) == 36
    assert rid.count("-") == 4


def test_encode_request_publish() -> None:
    """PUBLISH 요청 직렬화."""
    req = build_request(Action.PUBLISH, "topic/1", {"key": "value"})
    data = encode_request(req)
    import json

    obj = json.loads(data)
    assert obj["action"] == "PUBLISH"
    assert obj["topic"] == "topic/1"
    assert obj["payload"] == {"key": "value"}
    assert "req_id" in obj


def test_encode_request_subscribe() -> None:
    """SUBSCRIBE 요청 직렬화 (payload 없음)."""
    req = build_request(Action.SUBSCRIBE, "topic/sub")
    data = encode_request(req)
    import json

    obj = json.loads(data)
    assert obj["action"] == "SUBSCRIBE"
    assert obj["topic"] == "topic/sub"
    assert obj.get("payload") is None or "payload" not in obj


def test_decode_message_ack() -> None:
    """ACK 메시지 파싱."""
    raw = '{"event":"ACK","req_id":"r1","code":200}'
    msg = decode_message(raw)
    assert msg.event == "ACK"
    assert msg.req_id == "r1"
    assert msg.code == 200
    assert msg.payload is None


def test_decode_message_subscription() -> None:
    """SUBSCRIPTION 메시지 파싱."""
    raw = '{"event":"SUBSCRIPTION","req_id":"r1","topic":"t","payload":{"ok":true}}'
    msg = decode_message(raw)
    assert msg.event == "SUBSCRIPTION"
    assert msg.req_id == "r1"
    assert msg.topic == "t"
    assert msg.payload == {"ok": True}


def test_decode_message_invalid_event() -> None:
    """알 수 없는 event 타입 시 ValueError."""
    raw = '{"event":"UNKNOWN","req_id":"r1"}'
    with pytest.raises(ValueError, match="Unknown event"):
        decode_message(raw)
