"""
클라이언트 연결 상태 모니터 (Presence Monitor).

AWS IoT Core의 수명주기 이벤트 토픽을 구독하여
클라이언트 단절을 감지하고, 등록된 콜백을 호출한다.

주요 활용:
- 독점 세션 Lock 강제 해제 (세션 점유 클라이언트 단절 시)
- 스트리밍 중단 (수신 클라이언트 단절 시)
"""

from __future__ import annotations

import json
import logging
from typing import Callable

logger = logging.getLogger(__name__)

# AWS IoT Core 수명주기 이벤트 토픽
_DISCONNECTED_TOPIC = "$aws/events/presence/disconnected/+"
_CONNECTED_TOPIC = "$aws/events/presence/connected/+"

DisconnectCallback = Callable[[str], None]
ConnectCallback = Callable[[str], None]


class PresenceMonitor:
    """
    AWS IoT 수명주기 이벤트 기반 클라이언트 Presence 모니터.

    서버 연결 객체에 추가 구독을 등록하고,
    연결/단절 이벤트 발생 시 등록된 콜백을 호출한다.
    """

    def __init__(self) -> None:
        self._on_disconnect_callbacks: list[DisconnectCallback] = []
        self._on_connect_callbacks: list[ConnectCallback] = []

    def on_disconnect(self, callback: DisconnectCallback) -> None:
        """클라이언트 단절 이벤트 핸들러 등록."""
        self._on_disconnect_callbacks.append(callback)

    def on_connect(self, callback: ConnectCallback) -> None:
        """클라이언트 연결 이벤트 핸들러 등록."""
        self._on_connect_callbacks.append(callback)

    def get_subscription_topics(self) -> list[str]:
        """구독해야 할 수명주기 이벤트 토픽 목록."""
        return [_DISCONNECTED_TOPIC, _CONNECTED_TOPIC]

    def handle_message(self, topic: str, payload: bytes) -> None:
        """
        수명주기 이벤트 메시지 처리.

        AWS IoT 이벤트 페이로드에서 clientId를 추출하여 콜백 호출.
        """
        try:
            data = json.loads(payload.decode("utf-8"))
            client_id = data.get("clientId", "")
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning("수명주기 이벤트 페이로드 파싱 실패: topic=%s", topic)
            return

        if not client_id:
            return

        if "disconnected" in topic:
            logger.debug("클라이언트 단절 감지: client_id=%s", client_id)
            for cb in self._on_disconnect_callbacks:
                try:
                    cb(client_id)
                except Exception:
                    logger.exception("단절 콜백 오류: client_id=%s", client_id)

        elif "connected" in topic:
            logger.debug("클라이언트 연결 감지: client_id=%s", client_id)
            for cb in self._on_connect_callbacks:
                try:
                    cb(client_id)
                except Exception:
                    logger.exception("연결 콜백 오류: client_id=%s", client_id)
