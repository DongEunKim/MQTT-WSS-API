"""
독점 세션 Lock 관리 (패턴 E).

VIN별로 단 하나의 클라이언트만 세션을 점유할 수 있다.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)


class SessionManager:
    """
    VIN별 독점 세션 Lock 관리자.

    Thread-safe하게 구현되어 있으며,
    idle_timeout이 설정된 경우 점유 클라이언트가 응답 없을 시 자동 해제한다.
    """

    def __init__(self, idle_timeout: float = 300.0) -> None:
        """
        Args:
            idle_timeout: 세션 유휴 자동 해제 시간(초). 0이면 자동 해제 없음.
        """
        self._idle_timeout = idle_timeout
        # vin → (client_id, acquired_at)
        self._locks: dict[str, tuple[str, float]] = {}
        self._mutex = threading.Lock()

    def acquire(self, vin: str, client_id: str) -> bool:
        """
        세션 Lock 획득 시도.

        Returns:
            True: 획득 성공 (신규 또는 동일 클라이언트 재획득).
            False: 다른 클라이언트가 점유 중.
        """
        with self._mutex:
            existing = self._locks.get(vin)
            if existing:
                locked_by, acquired_at = existing
                if locked_by == client_id:
                    # 동일 클라이언트 재획득 → 타임스탬프 갱신
                    self._locks[vin] = (client_id, time.monotonic())
                    return True
                # idle_timeout 초과 시 강제 해제
                if (
                    self._idle_timeout > 0
                    and time.monotonic() - acquired_at > self._idle_timeout
                ):
                    logger.info(
                        "세션 idle_timeout 초과로 강제 해제: vin=%s, locked_by=%s",
                        vin, locked_by,
                    )
                    self._locks[vin] = (client_id, time.monotonic())
                    return True
                return False
            self._locks[vin] = (client_id, time.monotonic())
            logger.info("세션 획득: vin=%s, client_id=%s", vin, client_id)
            return True

    def release(self, vin: str, client_id: str) -> bool:
        """
        세션 Lock 해제.

        Returns:
            True: 해제 성공.
            False: 해당 클라이언트가 점유자가 아님.
        """
        with self._mutex:
            existing = self._locks.get(vin)
            if not existing:
                return False
            locked_by, _ = existing
            if locked_by != client_id:
                logger.warning(
                    "세션 해제 실패 (점유자 불일치): vin=%s, 요청=%s, 점유=%s",
                    vin, client_id, locked_by,
                )
                return False
            del self._locks[vin]
            logger.info("세션 해제: vin=%s, client_id=%s", vin, client_id)
            return True

    def force_release(self, client_id: str) -> list[str]:
        """
        특정 클라이언트가 점유한 모든 VIN 세션을 강제 해제.
        클라이언트 연결 끊김 시 호출한다.

        Returns:
            해제된 VIN 목록.
        """
        released = []
        with self._mutex:
            for vin, (locked_by, _) in list(self._locks.items()):
                if locked_by == client_id:
                    del self._locks[vin]
                    released.append(vin)
        if released:
            logger.info(
                "클라이언트 단절로 세션 강제 해제: client_id=%s, vins=%s",
                client_id, released,
            )
        return released

    def get_owner(self, vin: str) -> Optional[str]:
        """VIN의 현재 세션 점유자 client_id. 없으면 None."""
        with self._mutex:
            existing = self._locks.get(vin)
            return existing[0] if existing else None

    def is_locked(self, vin: str) -> bool:
        """VIN의 세션이 점유 중인지 확인."""
        return self.get_owner(vin) is not None

    def refresh(self, vin: str, client_id: str) -> None:
        """세션 타임스탬프 갱신 (heartbeat 대용)."""
        with self._mutex:
            existing = self._locks.get(vin)
            if existing and existing[0] == client_id:
                self._locks[vin] = (client_id, time.monotonic())
