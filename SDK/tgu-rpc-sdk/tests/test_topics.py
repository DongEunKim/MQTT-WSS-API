"""topics 모듈 단위 테스트."""

import pytest

from tgu_rpc.topics import (
    build_request_topic,
    build_response_topic,
    build_stream_topic,
)


def test_build_request_topic() -> None:
    """요청 토픽 생성."""
    assert build_request_topic("RemoteUDS", "v001") == "WMT/RemoteUDS/v001/request"
    assert build_request_topic("VISS", "vehicle_001") == "WMT/VISS/vehicle_001/request"


def test_build_response_topic() -> None:
    """응답 토픽 생성."""
    assert build_response_topic(
        "RemoteUDS", "v001", "client_A"
    ) == "WMO/RemoteUDS/v001/client_A/response"
    assert build_response_topic(
        "VISS", "vehicle_001", "client_xyz"
    ) == "WMO/VISS/vehicle_001/client_xyz/response"


def test_build_request_topic_empty_service() -> None:
    """빈 service 거부."""
    with pytest.raises(ValueError, match="service"):
        build_request_topic("", "v001")
    with pytest.raises(ValueError, match="빈 문자열"):
        build_request_topic("   ", "v001")


def test_build_request_topic_empty_vehicle_id() -> None:
    """빈 vehicle_id 거부."""
    with pytest.raises(ValueError, match="vehicle_id"):
        build_request_topic("RemoteUDS", "")


def test_build_request_topic_slash_in_service() -> None:
    """service에 / 포함 거부."""
    with pytest.raises(ValueError, match="/"):
        build_request_topic("Remote/UDS", "v001")


def test_build_response_topic_slash_in_client_id() -> None:
    """client_id에 / 포함 거부."""
    with pytest.raises(ValueError, match="/"):
        build_response_topic("RemoteUDS", "v001", "client/A")


def test_build_stream_topic() -> None:
    """스트림 토픽 생성."""
    assert build_stream_topic(
        "RemoteDashboard", "v001", "client_A", "vehicleSpeed"
    ) == "WMO/RemoteDashboard/v001/client_A/stream/vehicleSpeed"


def test_build_stream_topic_empty_api() -> None:
    """빈 api 거부."""
    with pytest.raises(ValueError, match="api"):
        build_stream_topic("RemoteDashboard", "v001", "c", "")
