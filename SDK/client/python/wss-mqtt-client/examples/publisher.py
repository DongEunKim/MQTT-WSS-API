#!/usr/bin/env python3
"""
발행 클라이언트 예제 (기본 - 동기).

test/command 토픽에 메시지를 발행한다.
Mock 서버의 TGU 시뮬레이션이 활성화되어 있으면,
test/response 구독자가 메시지를 수신한다.

Usage:
    # 터미널 1: Mock 서버
    python SDK/examples/run_mock_server.py

    # 터미널 2: 구독 클라이언트
    python SDK/client/python/wss-mqtt-client/examples/subscriber.py

    # 터미널 3: 발행 클라이언트
    python SDK/client/python/wss-mqtt-client/examples/publisher.py
    python SDK/client/python/wss-mqtt-client/examples/publisher.py --message '{"action":"start"}'
    python SDK/client/python/wss-mqtt-client/examples/publisher.py --binary  # bytes(MessagePack) 발행
    python SDK/client/python/wss-mqtt-client/examples/publisher.py -n 5 -i 2  # 5회 발행, 2초 간격

환경변수:
    WSS_URL  : 연결 URL (기본: ws://localhost:8765)
"""

import argparse
import json
import os
import time

from wss_mqtt_client import WssMqttClient

URL = os.environ.get("WSS_URL", "ws://localhost:8765")
TOPIC = os.environ.get("PUBLISH_TOPIC", "test/command")


def main() -> None:
    parser = argparse.ArgumentParser(description="발행 클라이언트")
    parser.add_argument(
        "-m",
        "--message",
        default='{"action": "ping", "timestamp": 0}',
        help="발행할 JSON 메시지 (기본: {\"action\": \"ping\"})",
    )
    parser.add_argument(
        "-b",
        "--binary",
        action="store_true",
        help="bytes payload로 MessagePack 직렬화 발행 (msgpack 패키지 필요)",
    )
    parser.add_argument(
        "-n",
        "--count",
        type=int,
        default=1,
        help="발행 횟수 (기본: 1, 0=무한)",
    )
    parser.add_argument(
        "-i",
        "--interval",
        type=float,
        default=1.0,
        help="발행 간격(초) (기본: 1.0)",
    )
    args = parser.parse_args()

    if args.binary:
        payload = args.message.encode("utf-8")
    else:
        try:
            payload = json.loads(args.message)
        except json.JSONDecodeError as e:
            print(f"[발행] JSON 파싱 오류: {e}")
            return

    print(f"[발행] 연결 중: {URL}")
    print(f"[발행] 토픽: {TOPIC}")

    with WssMqttClient(url=URL) as client:
        n = 0
        while args.count == 0 or n < args.count:
            n += 1
            if isinstance(payload, dict) and "timestamp" in payload:
                payload = dict(payload)
                payload["timestamp"] = int(time.time() * 1000)
            client.publish(TOPIC, payload)
            print(f"[발행 #{n}] {payload}")
            if args.count == 0 or n < args.count:
                time.sleep(args.interval)

    print("[발행] 완료")


if __name__ == "__main__":
    main()
