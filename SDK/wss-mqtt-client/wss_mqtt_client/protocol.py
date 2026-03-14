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


def encode_request_binary(request: Request) -> bytes:
    """
    Request를 MessagePack 바이너리로 직렬화.

    payload가 bytes이면 사양 5.1에 따라 전체 Envelope을 MessagePack 직렬화.
    msgpack 미설치 시 TypeError 발생.

    Returns:
        MessagePack 직렬화된 바이너리

    Raises:
        TypeError: msgpack 패키지가 없는 경우
    """
    try:
        import msgpack
    except ImportError as e:
        raise TypeError(
            "bytes payload 사용 시 msgpack 패키지가 필요합니다. "
            "pip install msgpack 또는 pip install wss-mqtt-client[msgpack]"
        ) from e
    data = request.to_dict()
    return msgpack.packb(data, use_bin_type=True)


def _truncate(raw: Union[str, bytes], max_len: int = 200) -> str:
    """raw를 문자열로 변환 후 max_len 초과 시 truncate. 로깅용."""
    if isinstance(raw, bytes):
        s = raw.decode("utf-8", errors="replace")
    else:
        s = str(raw)
    if len(s) > max_len:
        s = s[:max_len] + "..."
    return repr(s)


def _decode_data(raw: Union[str, bytes]) -> dict:
    """raw를 dict로 디코딩. bytes는 MessagePack 우선, 실패 시 JSON."""
    try:
        if isinstance(raw, str):
            return json.loads(raw)
        try:
            import msgpack
            return msgpack.unpackb(raw, raw=False)
        except ImportError:
            pass
        except Exception:
            pass
        return json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise ValueError(
            "직렬화 파싱 실패: %s. raw_preview=%s" % (e, _truncate(raw))
        ) from e


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
    data = _decode_data(raw)
    if not isinstance(data, dict):
        raise ValueError(
            "메시지가 dict가 아님: type=%s. raw_preview=%s"
            % (type(data).__name__, _truncate(raw))
        )

    event = data.get("event")
    req_id = data.get("req_id")
    if not req_id:
        raise ValueError(
            "Missing req_id in message. event=%s keys=%s. raw_preview=%s"
            % (event, list(data.keys()), _truncate(raw))
        )

    if event == EVENT_ACK:
        code = data.get("code")
        if code is None:
            raise ValueError(
                "Missing code in ACK message. req_id=%s. raw_preview=%s"
                % (req_id, _truncate(raw))
            )
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
            raise ValueError(
                "Missing topic in SUBSCRIPTION message. req_id=%s. raw_preview=%s"
                % (req_id, _truncate(raw))
            )
        return SubscriptionEvent(
            event=event,
            req_id=req_id,
            topic=topic,
            payload=payload,
        )
    else:
        topic = data.get("topic", "")
        raise ValueError(
            "Unknown event type: event=%s req_id=%s topic=%s. raw_preview=%s"
            % (event, req_id, topic, _truncate(raw))
        )


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
