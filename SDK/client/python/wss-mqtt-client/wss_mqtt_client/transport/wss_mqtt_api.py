"""
WSS-MQTT API 전송 계층.

wss-mqtt-api 게이트웨이와 WebSocket으로 통신한다.
"""

import logging
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import websockets
from websockets.asyncio.client import ClientConnection

from ..exceptions import WssConnectionError
from ..protocol import decode_message

logger = logging.getLogger(__name__)


def _build_ws_url(url: str, token: Optional[str] = None) -> str:
    """
    토큰을 쿼리 파라미터로 포함한 WebSocket URL 생성.

    사양 4.3: 쿼리 파라미터 ?token= 옵션 지원
    """
    if not token:
        return url
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    query["token"] = [token]
    new_query = urlencode(query, doseq=True)
    new_parts = list(parsed)
    new_parts[4] = new_query
    return urlunparse(new_parts)


def _build_headers(token: Optional[str] = None) -> dict[str, str]:
    """Authorization Bearer 헤더 생성."""
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


class WssMqttApiTransport:
    """
    wss-mqtt-api 게이트웨이용 WebSocket 전송 계층.

    연결 수립, 메시지 송수신, 수신 메시지 콜백 분배를 담당한다.
    """

    def __init__(
        self,
        url: str,
        token: Optional[str] = None,
        *,
        use_query_token: bool = False,
        ping_interval: float = 30.0,
        ping_timeout: float = 10.0,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        """
        Args:
            url: wss://[API_DOMAIN]/v1/messaging
            token: JWT 또는 API 키
            use_query_token: True면 토큰을 쿼리 파라미터로 전달 (헤더 대신)
            ping_interval: Ping 전송 간격(초). 0이면 비활성화
            ping_timeout: Pong 미수신 시 연결 종료 간격(초)
            logger: 로거 인스턴스
        """
        self._url = _build_ws_url(url, token) if use_query_token else url
        self._token = token if not use_query_token else None
        self._use_query_token = use_query_token
        self._ping_interval = ping_interval
        self._ping_timeout = ping_timeout
        self._log = logger if logger is not None else logging.getLogger(__name__)
        self._ws: Optional[ClientConnection] = None
        self._receive_callback: Optional[Callable[[Any], None]] = None
        self._on_connection_lost: Optional[Callable[[], None]] = None
        self._closed = False

    def set_on_connection_lost(self, callback: Optional[Callable[[], None]]) -> None:
        """연결 끊김 시 호출될 콜백 등록."""
        self._on_connection_lost = callback

    async def connect(self) -> None:
        """WebSocket 연결 수립."""
        try:
            headers = _build_headers(self._token) if self._token else None
            self._ws = await websockets.connect(
                self._url,
                additional_headers=headers,
                ping_interval=self._ping_interval,
                ping_timeout=self._ping_timeout,
                close_timeout=5,
            )
            self._closed = False
            self._log.debug("WebSocket connected: %s", self._url)
        except Exception as e:
            raise WssConnectionError(f"연결 실패: {e}") from e

    async def disconnect(self) -> None:
        """WebSocket 연결 종료."""
        self._closed = True
        if self._ws:
            await self._ws.close()
            self._ws = None
            self._log.debug("WebSocket disconnected")

    def set_receive_callback(self, callback: Callable[[Any], None]) -> None:
        """수신 메시지 콜백 등록. decode_message 결과가 전달된다."""
        self._receive_callback = callback

    async def send(self, data: str | bytes) -> None:
        """
        메시지 전송.

        Args:
            data: JSON 문자열 또는 MessagePack 바이너리
        """
        if not self._ws or self._closed:
            raise WssConnectionError("연결되지 않음")
        await self._ws.send(data)

    async def receive_loop(self) -> None:
        """
        수신 루프. 연결이 유지되는 동안 메시지를 수신하고 콜백으로 전달한다.
        """
        if not self._ws or not self._receive_callback:
            return
        try:
            async for raw in self._ws:
                if self._closed:
                    break
                try:
                    msg = decode_message(raw)
                    self._receive_callback(msg)
                except ValueError as e:
                    self._log.warning("메시지 파싱 실패: %s", e)
        except websockets.exceptions.ConnectionClosed as e:
            if not self._closed:
                self._log.debug("WebSocket 연결 종료: %s", e)
                if self._on_connection_lost:
                    try:
                        self._on_connection_lost()
                    except Exception:  # noqa: BLE001
                        self._log.exception("on_connection_lost 콜백 오류")

    @property
    def is_connected(self) -> bool:
        """연결 상태."""
        return self._ws is not None and not self._closed
