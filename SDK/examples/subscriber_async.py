#!/usr/bin/env python3
"""
비동기(Async) 구독 클라이언트 예제.

고급 사용자용. async for 스트리밍, 자동 재연결 등.

Usage:
    python examples/run_mock_server.py  # 터미널 1
    python examples/subscriber_async.py  # 터미널 2

    # 자동 재연결
    AUTO_RECONNECT=1 python examples/subscriber_async.py

환경변수:
    WSS_URL       : 연결 URL (기본: ws://localhost:8765)
    AUTO_RECONNECT: 1이면 자동 재연결·구독 복구
"""

import asyncio
import os

from wss_mqtt_client import WssConnectionError, WssMqttClientAsync

URL = os.environ.get("WSS_URL", "ws://localhost:8765")
TOPIC = os.environ.get("TOPIC", "test/response")
AUTO_RECONNECT = os.environ.get("AUTO_RECONNECT", "").lower() in ("1", "true", "yes")


async def main() -> None:
    print(f"[Async 구독] 연결 중: {URL}")
    print(f"[Async 구독] 토픽: {TOPIC}")
    if AUTO_RECONNECT:
        print("[Async 구독] 자동 재연결: 활성화")
    print("[Async 구독] 메시지 대기 중... (Ctrl+C 종료)\n")

    try:
        async with WssMqttClientAsync(
            url=URL,
            auto_reconnect=AUTO_RECONNECT,
            auto_resubscribe=AUTO_RECONNECT,
        ) as client:
            async with client.subscribe(TOPIC, timeout=None) as stream:
                async for event in stream:
                    print(f"[수신] topic={event.topic} payload={event.payload}")
    except asyncio.CancelledError:
        pass
    except KeyboardInterrupt:
        pass
    except WssConnectionError as e:
        print(f"[구독] 연결 끊김: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
