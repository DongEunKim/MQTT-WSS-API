"""
프로토콜 계층 단위 테스트.
"""

import pytest

from wss_mqtt_client.models import Action
from wss_mqtt_client.protocol import (
    build_request,
    decode_message,
    encode_request,
    encode_request_binary,
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
    """알 수 없는 event 타입 시 ValueError (event, req_id, raw_preview 포함)."""
    raw = '{"event":"UNKNOWN","req_id":"r1"}'
    with pytest.raises(ValueError) as exc_info:
        decode_message(raw)
    err = str(exc_info.value)
    assert "Unknown event" in err
    assert "event=UNKNOWN" in err
    assert "req_id=r1" in err
    assert "raw_preview" in err


def test_decode_message_missing_req_id() -> None:
    """req_id 누락 시 ValueError (event, keys 포함)."""
    raw = '{"event":"ACK","code":200}'
    with pytest.raises(ValueError) as exc_info:
        decode_message(raw)
    err = str(exc_info.value)
    assert "Missing req_id" in err
    assert "event=ACK" in err
    assert "keys=" in err


def test_decode_message_missing_code() -> None:
    """ACK에서 code 누락 시 ValueError (req_id 포함)."""
    raw = '{"event":"ACK","req_id":"r1"}'
    with pytest.raises(ValueError) as exc_info:
        decode_message(raw)
    err = str(exc_info.value)
    assert "Missing code" in err
    assert "req_id=r1" in err


def test_decode_message_missing_topic() -> None:
    """SUBSCRIPTION에서 topic 누락 시 ValueError (req_id 포함)."""
    raw = '{"event":"SUBSCRIPTION","req_id":"r1","payload":{}}'
    with pytest.raises(ValueError) as exc_info:
        decode_message(raw)
    err = str(exc_info.value)
    assert "Missing topic" in err
    assert "req_id=r1" in err


def test_decode_message_parse_failure() -> None:
    """직렬화 파싱 실패 시 ValueError (raw_preview 포함)."""
    raw = '{"event":"ACK","req_id":"r1",invalid json'
    with pytest.raises(ValueError) as exc_info:
        decode_message(raw)
    err = str(exc_info.value)
    assert "직렬화 파싱 실패" in err or "raw_preview" in err


def test_encode_request_binary() -> None:
    """MessagePack 바이너리 직렬화 (msgpack 설치 시)."""
    pytest.importorskip("msgpack")
    req = build_request(Action.PUBLISH, "topic/1", b"binary_data")
    data = encode_request_binary(req)
    assert isinstance(data, bytes)
    import msgpack
    obj = msgpack.unpackb(data, raw=False)
    assert obj["action"] == "PUBLISH"
    assert obj["topic"] == "topic/1"
    assert obj["payload"] == b"binary_data"


def test_decode_message_msgpack() -> None:
    """MessagePack 바이너리 파싱 (msgpack 설치 시)."""
    pytest.importorskip("msgpack")
    import msgpack

    data = {
        "event": "SUBSCRIPTION",
        "req_id": "r1",
        "topic": "t",
        "payload": {"ok": True},
    }
    raw = msgpack.packb(data)
    msg = decode_message(raw)
    assert msg.event == "SUBSCRIPTION"
    assert msg.req_id == "r1"
    assert msg.topic == "t"
    assert msg.payload == {"ok": True}
