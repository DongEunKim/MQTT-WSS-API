#!/usr/bin/env python3
"""
비동기(Async) 발행 클라이언트 예제.

고급 사용자용. WssMqttClientAsync 사용.

Usage:
    python SDK/examples/run_mock_server.py  # 터미널 1
    python SDK/wss-mqtt-client/examples/publisher_async.py  # 터미널 2

환경변수:
    WSS_URL : 연결 URL (기본: ws://localhost:8765)
"""

import argparse
import asyncio
import json
import os

from wss_mqtt_client import WssMqttClientAsync

URL = os.environ.get("WSS_URL", "ws://localhost:8765")
TOPIC = os.environ.get("PUBLISH_TOPIC", "test/command")


async def main() -> None:
    parser = argparse.ArgumentParser(description="비동기 발행 클라이언트")
    parser.add_argument(
        "-m",
        "--message",
        default='{"action": "ping", "timestamp": 0}',
        help="발행할 JSON 메시지",
    )
    parser.add_argument(
        "-b",
        "--binary",
        action="store_true",
        help="bytes payload (MessagePack)",
    )
    parser.add_argument("-n", "--count", type=int, default=1)
    parser.add_argument("-i", "--interval", type=float, default=1.0)
    args = parser.parse_args()

    if args.binary:
        payload = args.message.encode("utf-8")
    else:
        payload = json.loads(args.message)

    print(f"[Async 발행] 연결 중: {URL}")

    async with WssMqttClientAsync(url=URL) as client:
        n = 0
        while args.count == 0 or n < args.count:
            n += 1
            if isinstance(payload, dict) and "timestamp" in payload:
                import time

                payload["timestamp"] = int(time.time() * 1000)
            await client.publish(TOPIC, payload)
            print(f"[발행 #{n}] {payload}")
            if args.count == 0 or n < args.count:
                await asyncio.sleep(args.interval)

    print("[발행] 완료")


if __name__ == "__main__":
    asyncio.run(main())
