"""
기본 publish/subscribe 예제 (동기).

연결 → 구독 → 발행 → 수신 흐름. asyncio 없이 동작.

실행 전 URL과 토큰을 환경변수 또는 아래 변수에 설정하세요.

Mock 서버 테스트:
    WSS_MQTT_URL=ws://localhost:8765 WSS_MQTT_TOKEN= python basic_publish_subscribe.py

환경변수:
    WSS_MQTT_URL   : API URL
    WSS_MQTT_TOKEN : JWT 토큰
"""

import os

from wss_mqtt_client import WssMqttClient

URL = os.environ.get("WSS_MQTT_URL", "wss://api.example.com/v1/messaging")
TOKEN = os.environ.get("WSS_MQTT_TOKEN", "your_jwt_token")

RECEIVED: list[dict] = []


def on_message(event):
    RECEIVED.append(event.payload)


def main() -> None:
    """연결 → 구독 → 발행 → 수신 대기."""
    print("구독 시작: tgu/device_001/response")

    with WssMqttClient(url=URL, token=TOKEN) as client:
        client.subscribe("tgu/device_001/response", callback=on_message)
        client.publish(
            "tgu/device_001/command",
            {"action": "status", "device_id": "001"},
        )
        print("발행 완료: tgu/device_001/command")

        try:
            client.run(timeout=5.0)
        except KeyboardInterrupt:
            pass

    if RECEIVED:
        print(f"수신 [topic=tgu/device_001/response]: {RECEIVED[0]}")
    else:
        print("수신 없음 (타임아웃 또는 Mock 미연결)")

    print("연결 종료")


if __name__ == "__main__":
    main()
