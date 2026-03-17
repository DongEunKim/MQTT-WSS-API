"""topics 모듈 단위 테스트."""

import pytest

from maas_rpc_client.topics import (
    build_request_topic,
    build_response_topic,
)


def test_build_request_topic() -> None:
    """요청 토픽 생성."""
    assert (
        build_request_topic("RemoteUDS", "device_001", "acme", "VIN123")
        == "WMT/RemoteUDS/device_001/acme/VIN123/request"
    )
    assert (
        build_request_topic("VISS", "gw_01", "oem_x", "asset_99")
        == "WMT/VISS/gw_01/oem_x/asset_99/request"
    )


def test_build_response_topic() -> None:
    """응답 토픽 생성."""
    assert (
        build_response_topic("RemoteUDS", "device_001", "acme", "VIN123", "client_A")
        == "WMO/RemoteUDS/device_001/acme/VIN123/client_A/response"
    )
    assert (
        build_response_topic("VISS", "gw_01", "oem_x", "asset_99", "client_xyz")
        == "WMO/VISS/gw_01/oem_x/asset_99/client_xyz/response"
    )


def test_build_request_topic_empty_service() -> None:
    """빈 service 거부."""
    with pytest.raises(ValueError, match="service"):
        build_request_topic("", "device_001", "acme", "VIN123")
    with pytest.raises(ValueError, match="빈 문자열"):
        build_request_topic("   ", "device_001", "acme", "VIN123")


def test_build_request_topic_empty_thing_name() -> None:
    """빈 thing_name 거부."""
    with pytest.raises(ValueError, match="thing_name"):
        build_request_topic("RemoteUDS", "", "acme", "VIN123")


def test_build_request_topic_empty_oem() -> None:
    """빈 oem 거부."""
    with pytest.raises(ValueError, match="oem"):
        build_request_topic("RemoteUDS", "device_001", "", "VIN123")


def test_build_request_topic_empty_asset() -> None:
    """빈 asset 거부."""
    with pytest.raises(ValueError, match="asset"):
        build_request_topic("RemoteUDS", "device_001", "acme", "")


def test_build_request_topic_slash_in_service() -> None:
    """service에 / 포함 거부."""
    with pytest.raises(ValueError, match="/"):
        build_request_topic("Remote/UDS", "device_001", "acme", "VIN123")


def test_build_request_topic_slash_in_oem() -> None:
    """oem에 / 포함 거부."""
    with pytest.raises(ValueError, match="/"):
        build_request_topic("RemoteUDS", "device_001", "ac/me", "VIN123")


def test_build_response_topic_slash_in_client_id() -> None:
    """client_id에 / 포함 거부."""
    with pytest.raises(ValueError, match="/"):
        build_response_topic("RemoteUDS", "device_001", "acme", "VIN123", "client/A")
