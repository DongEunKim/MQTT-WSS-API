#!/usr/bin/env python3
"""
MQTT Transport 발행 예제.

네이티브 MQTT 브로커(Mosquitto 등)에 연결하여 메시지를 발행한다.

Usage:
    # MQTT 브로커 실행 (Docker)
    # cd SDK && docker compose up -d

    python examples/mqtt_publisher.py
    python examples/mqtt_publisher.py --message '{"sensor": 42}'

환경변수:
    MQTT_URL  : MQTT 브로커 URL (기본: mqtt://localhost:1883)
    MQTT_TOPIC: 발행 토픽 (기본: test/mqtt)
"""

import argparse
import asyncio
import json
import os

from wss_mqtt_client import WssMqttClientAsync

URL = os.environ.get("MQTT_URL", "mqtt://localhost:1883")
TOPIC = os.environ.get("MQTT_TOPIC", "test/mqtt")


async def main() -> None:
    parser = argparse.ArgumentParser(description="MQTT 발행 클라이언트")
    parser.add_argument(
        "-m",
        "--message",
        default='{"message": "hello", "from": "mqtt_publisher"}',
        help="발행할 JSON 메시지",
    )
    parser.add_argument(
        "-n",
        "--count",
        type=int,
        default=1,
        help="발행 횟수 (기본: 1)",
    )
    args = parser.parse_args()

    try:
        payload = json.loads(args.message)
    except json.JSONDecodeError as e:
        print(f"[MQTT 발행] JSON 파싱 오류: {e}")
        return

    print(f"[MQTT 발행] 연결 중: {URL}")
    print(f"[MQTT 발행] 토픽: {TOPIC}")

    async with WssMqttClientAsync(url=URL, transport="mqtt") as client:
        for i in range(args.count):
            await client.publish(TOPIC, payload)
            print(f"[MQTT 발행 #{i+1}] {payload}")

    print("[MQTT 발행] 완료")


if __name__ == "__main__":
    asyncio.run(main())
