"""
WSS-MQTT 프로토콜 계층.

Envelope 직렬화/역직렬화, req_id 생성, 메시지 파싱을 담당한다.
"""

import json
import uuid
from typing import Any, Union

from .constants import EVENT_ACK, EVENT_SUBSCRIPTION
from .models import AckEvent, Action, Request, SubscriptionEvent


def generate_req_id() -> str:
    """요청 식별자 생성 (UUID v4)."""
    return str(uuid.uuid4())


def encode_request(request: Request) -> str:
    """
    Request를 JSON 문자열로 직렬화.

    Returns:
        JSON 직렬화된 문자열 (WebSocket 텍스트 프레임용)
    """
    return json.dumps(request.to_dict(), ensure_ascii=False)


def decode_message(raw: Union[str, bytes]) -> Union[AckEvent, SubscriptionEvent]:
    """
    수신 메시지를 파싱하여 ACK 또는 SUBSCRIPTION 이벤트로 변환.

    Args:
        raw: JSON 문자열 또는 MessagePack 바이너리

    Returns:
        AckEvent 또는 SubscriptionEvent

    Raises:
        ValueError: 파싱 실패 또는 알 수 없는 event 타입
    """
    if isinstance(raw, bytes):
        data = json.loads(raw.decode("utf-8"))
    else:
        data = json.loads(raw) if isinstance(raw, str) else raw

    event = data.get("event")
    req_id = data.get("req_id")
    if not req_id:
        raise ValueError("Missing req_id in message")

    if event == EVENT_ACK:
        code = data.get("code")
        if code is None:
            raise ValueError("Missing code in ACK message")
        return AckEvent(
            event=event,
            req_id=req_id,
            code=int(code),
            payload=data.get("payload"),
        )
    elif event == EVENT_SUBSCRIPTION:
        topic = data.get("topic")
        payload = data.get("payload")
        if topic is None:
            raise ValueError("Missing topic in SUBSCRIPTION message")
        return SubscriptionEvent(
            event=event,
            req_id=req_id,
            topic=topic,
            payload=payload,
        )
    else:
        raise ValueError(f"Unknown event type: {event}")


def build_request(action: Action, topic: str, payload: Any = None) -> Request:
    """
    Request 객체 생성. req_id는 자동 생성.

    Args:
        action: PUBLISH, SUBSCRIBE, UNSUBSCRIBE 중 하나
        topic: 대상 MQTT 토픽
        payload: PUBLISH 시에만 사용

    Returns:
        Request 인스턴스
    """
    return Request(
        action=action,
        req_id=generate_req_id(),
        topic=topic,
        payload=payload,
    )
