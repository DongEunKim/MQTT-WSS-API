#!/usr/bin/env python3
"""
구독 클라이언트 예제 (기본 - 동기).

test/response 토픽을 구독하고 수신 메시지를 출력한다.
콜백 기반. 먼저 Mock 서버를 실행한 뒤, 이 스크립트를 실행하세요.

Usage:
    # 터미널 1: Mock 서버
    python SDK/examples/run_mock_server.py

    # 터미널 2: 구독 클라이언트 (프로젝트 루트에서)
    python SDK/client/python/wss-mqtt-client/examples/subscriber.py

    # 테스트용 (5초 후 자동 종료)
    RUN_TIMEOUT=5 python SDK/client/python/wss-mqtt-client/examples/subscriber.py

환경변수:
    WSS_URL    : 연결 URL (기본: ws://localhost:8765)
    TOPIC      : 구독 토픽 (기본: test/response)
    RUN_TIMEOUT: run 대기 시간(초). 없으면 무한 (Ctrl+C로 종료)
"""

import os

from wss_mqtt_client import WssMqttClient

URL = os.environ.get("WSS_URL", "ws://localhost:8765")
TOPIC = os.environ.get("TOPIC", "test/response")
RUN_TIMEOUT = os.environ.get("RUN_TIMEOUT")


def on_message(event):
    """수신 메시지 콜백."""
    print(f"[수신] topic={event.topic} payload={event.payload}")


def main() -> None:
    print(f"[구독] 연결 중: {URL}")
    print(f"[구독] 토픽: {TOPIC}")
    if RUN_TIMEOUT:
        print(f"[구독] {RUN_TIMEOUT}초 후 종료")
    else:
        print("[구독] Ctrl+C로 종료")
    print()

    with WssMqttClient(url=URL) as client:
        client.subscribe(TOPIC, callback=on_message)
        try:
            if RUN_TIMEOUT:
                client.run(timeout=float(RUN_TIMEOUT))
            else:
                client.run_forever()
        except KeyboardInterrupt:
            print("\n종료")


if __name__ == "__main__":
    main()
