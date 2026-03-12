"""
WSS-MQTT API 메시지 모델.

요청(Request), ACK, SUBSCRIPTION 이벤트의 데이터 구조를 정의한다.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class Action(str, Enum):
    """클라이언트 요청 액션 유형."""

    PUBLISH = "PUBLISH"
    SUBSCRIBE = "SUBSCRIBE"
    UNSUBSCRIBE = "UNSUBSCRIBE"


@dataclass
class Request:
    """
    클라이언트 → API 게이트웨이 요청.

    action, req_id, topic은 필수이며, payload는 PUBLISH 시에만 사용한다.
    """

    action: Action
    req_id: str
    topic: str
    payload: Optional[Any] = None

    def to_dict(self) -> dict[str, Any]:
        """Envelope 직렬화용 딕셔너리로 변환."""
        data: dict[str, Any] = {
            "action": self.action.value,
            "req_id": self.req_id,
            "topic": self.topic,
        }
        if self.payload is not None:
            data["payload"] = self.payload
        return data


@dataclass
class AckEvent:
    """
    API 게이트웨이 → 클라이언트 요청 응답.

    req_id로 원본 요청과 1:1 매핑된다.
    code 200이면 성공, 4xx/5xx면 실패.
    """

    event: str  # "ACK"
    req_id: str
    code: int
    payload: Optional[Any] = None


@dataclass
class SubscriptionEvent:
    """
    API 게이트웨이 → 클라이언트 구독 이벤트.

    구독한 토픽에 TGU가 메시지를 발행했을 때 수신한다.
    """

    event: str  # "SUBSCRIPTION"
    req_id: str
    topic: str
    payload: Any
