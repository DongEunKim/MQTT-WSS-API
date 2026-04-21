"""RPC 페이로드 빌더 동작 검증."""

import json

from maas_client._rpc import _build_request_payload


def test_action_overrides_payload_dict() -> None:
    raw = _build_request_payload("get", {"path": "/x", "action": "old"})
    data = json.loads(raw.decode("utf-8"))
    assert data["action"] == "get"
    assert data["path"] == "/x"


def test_none_payload_only_action() -> None:
    raw = _build_request_payload("ping", None)
    data = json.loads(raw.decode("utf-8"))
    assert data == {"action": "ping"}
