"""
WMT/WMO 토픽 빌더 및 파서 (서버 측).

토픽 구조:
    {WMT|WMO}/{ThingType}/{Service}/{VIN}/{ClientId}/{request|response|event}
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

_SEG_REQUEST = "request"
_SEG_RESPONSE = "response"
_SEG_EVENT = "event"
_PREFIX_WMT = "WMT"
_PREFIX_WMO = "WMO"


@dataclass(frozen=True)
class ParsedRequestTopic:
    """파싱된 요청 토픽 세그먼트."""

    thing_type: str
    service: str
    vin: str
    client_id: str


def build_response(
    thing_type: str,
    service: str,
    vin: str,
    client_id: str,
) -> str:
    """응답 토픽: WMO/{thing_type}/{service}/{vin}/{client_id}/response."""
    return f"{_PREFIX_WMO}/{thing_type}/{service}/{vin}/{client_id}/{_SEG_RESPONSE}"


def build_event(
    thing_type: str,
    service: str,
    vin: str,
    client_id: str,
) -> str:
    """이벤트(스트림) 토픽: WMO/{thing_type}/{service}/{vin}/{client_id}/event."""
    return f"{_PREFIX_WMO}/{thing_type}/{service}/{vin}/{client_id}/{_SEG_EVENT}"


def build_subscription(
    thing_type: str,
    service_name: str,
    vin: str,
) -> str:
    """서버가 구독할 와일드카드 토픽: WMT/{thing_type}/{service_name}/{vin}/+/request."""
    return f"{_PREFIX_WMT}/{thing_type}/{service_name}/{vin}/+/{_SEG_REQUEST}"


def parse_request(topic: str) -> Optional[ParsedRequestTopic]:
    """
    요청 토픽을 파싱하여 ParsedRequestTopic 반환.

    형식: WMT/{thing_type}/{service}/{vin}/{client_id}/request
    유효하지 않으면 None 반환.
    """
    parts = topic.split("/")
    if len(parts) != 6:
        return None
    direction, thing_type, service, vin, client_id, suffix = parts
    if direction != _PREFIX_WMT or suffix != _SEG_REQUEST:
        return None
    return ParsedRequestTopic(
        thing_type=thing_type,
        service=service,
        vin=vin,
        client_id=client_id,
    )
