"""
RpcContext: 핸들러에 전달되는 요청 컨텍스트.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class RpcContext:
    """
    RPC 핸들러에 전달되는 요청 컨텍스트.

    핸들러는 이 객체를 통해 요청 정보를 읽고
    필요 시 직접 응답을 발행할 수 있다.
    """

    thing_type: str
    """토픽의 {ThingType} (예: CGU)."""

    service: str
    """토픽의 {Service} (예: viss, diagnostics)."""

    action: str
    """페이로드에서 추출된 action 값."""

    vin: str
    """토픽의 {VIN}. 대상 장비 식별자."""

    client_id: str
    """토픽의 {ClientId}. 응답 라우팅에 사용."""

    payload: Any
    """action 필드가 제거된 나머지 페이로드 (dict 또는 bytes)."""

    correlation_id: Optional[bytes]
    """MQTT5 Correlation Data. 응답 발행 시 그대로 반환해야 한다."""

    response_topic: Optional[str]
    """MQTT5 Response Topic. SDK가 자동으로 응답을 발행하므로 직접 사용할 필요 없음."""

    user_props: dict[str, str] = field(default_factory=dict)
    """수신 메시지의 MQTT5 User Properties."""
