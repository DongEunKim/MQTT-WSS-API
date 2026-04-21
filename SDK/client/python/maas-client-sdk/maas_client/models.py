"""
maas-client-sdk 데이터 모델.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class RpcResponse:
    """RPC 단일 응답."""

    payload: Any
    """서버가 반환한 페이로드 (dict 또는 bytes). 구조는 서버-클라이언트 계약에 따름."""

    reason_code: int = 0
    """응답 결과 코드. 0=성공, 0x80 이상=오류."""

    correlation_id: Optional[bytes] = None
    """요청과 응답을 매핑하는 UUID bytes."""


@dataclass
class StreamEvent:
    """스트리밍 청크 이벤트 (WMO/.../event 수신)."""

    payload: Any
    """청크 페이로드. 구조는 서버-클라이언트 계약에 따름."""

    is_eof: bool = False
    """마지막 청크 여부. True이면 스트림 종료."""

    correlation_id: Optional[bytes] = None


@dataclass
class Message:
    """단순 pub/sub 수신 메시지."""

    topic: str
    payload: bytes
    qos: int = 0
    user_properties: list[tuple[str, str]] = field(default_factory=list)
