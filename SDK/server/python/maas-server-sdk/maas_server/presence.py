"""
클라이언트 연결 상태 모니터 (Presence Monitor).

MQTT 브로커가 **연결/단절 이벤트**를 특정 토픽으로 알려주는 경우,
해당 토픽을 구독해 단절을 감지하고 등록된 콜백을 호출한다.

기본값은 구독 토픽이 비어 있다(로컬 개발용 브로커 등).
운영 브로커가 수명주기 이벤트를 제공하면 ``MaasServer(..., lifecycle_topics=[...])`` 로 패턴을 넘긴다.

주요 활용:

- 독점 세션 Lock 강제 해제 (세션 점유 클라이언트 단절 시)
- 스트리밍 중단 (수신 클라이언트 단절 시)
"""

from __future__ import annotations

import json
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

DisconnectCallback = Callable[[str], None]
ConnectCallback = Callable[[str], None]


def _topic_matches(pattern: str, topic: str) -> bool:
    """MQTT ``+`` / ``#`` 와일드카드 패턴 매칭."""
    pattern_parts = pattern.split("/")
    topic_parts = topic.split("/")
    for i, pp in enumerate(pattern_parts):
        if pp == "#":
            return True
        if i >= len(topic_parts):
            return False
        if pp != "+" and pp != topic_parts[i]:
            return False
    return len(pattern_parts) == len(topic_parts)


class PresenceMonitor:
    """
    브로커 수명주기(연결/단절) 이벤트 기반 Presence 모니터.

    ``lifecycle_topics`` 에 와일드카드 패턴을 넣으면 해당 토픽만 구독한다.
    """

    def __init__(self, lifecycle_topics: Optional[list[str]] = None) -> None:
        self._lifecycle_topics: list[str] = list(lifecycle_topics or [])
        self._on_disconnect_callbacks: list[DisconnectCallback] = []
        self._on_connect_callbacks: list[ConnectCallback] = []

    def on_disconnect(self, callback: DisconnectCallback) -> None:
        """클라이언트 단절 이벤트 핸들러 등록."""
        self._on_disconnect_callbacks.append(callback)

    def on_connect(self, callback: ConnectCallback) -> None:
        """클라이언트 연결 이벤트 핸들러 등록."""
        self._on_connect_callbacks.append(callback)

    def get_subscription_topics(self) -> list[str]:
        """구독할 수명주기 이벤트 토픽 패턴 목록."""
        return list(self._lifecycle_topics)

    def matches_lifecycle_topic(self, topic: str) -> bool:
        """수신 토픽이 등록된 수명주기 패턴 중 하나와 일치하는지 여부."""
        for pat in self._lifecycle_topics:
            if _topic_matches(pat, topic):
                return True
        return False

    def handle_message(self, topic: str, payload: bytes) -> None:
        """
        수명주기 이벤트 메시지 처리.

        페이로드는 JSON이고 ``clientId`` 필드를 포함한다고 가정한다(브로커 구현에 따름).
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
