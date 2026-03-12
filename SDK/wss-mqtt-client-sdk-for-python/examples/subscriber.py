#!/usr/bin/env python3
"""
구독 클라이언트 예제.

test/response 토픽을 구독하고 수신 메시지를 출력한다.
먼저 Mock 서버를 실행한 뒤, 이 스크립트를 실행하세요.

Usage:
    # 터미널 1: Mock 서버
    python examples/run_mock_server.py

    # 터미널 2: 구독 클라이언트
    python examples/subscriber.py

환경변수:
    WSS_URL  : 연결 URL (기본: ws://localhost:8765)
"""

import asyncio
import os

from wss_mqtt_client import WssMqttClient

URL = os.environ.get("WSS_URL", "ws://localhost:8765")
TOPIC = os.environ.get("SUBSCRIBE_TOPIC", "test/response")


async def main() -> None:
    print(f"[구독] 연결 중: {URL}")
    print(f"[구독] 토픽: {TOPIC}")
    print("[구독] 메시지 대기 중... (Ctrl+C 종료)\n")

    try:
        async with WssMqttClient(url=URL) as client:
            async with client.subscribe(TOPIC, timeout=None) as stream:
                async for event in stream:
                    print(f"[수신] topic={event.topic} payload={event.payload}")
    except asyncio.CancelledError:
        pass
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"[구독] 오류: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
