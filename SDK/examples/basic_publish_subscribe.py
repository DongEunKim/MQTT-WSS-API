"""
기본 publish/subscribe 예제.

실행 전 URL과 토큰을 환경변수 또는 아래 변수에 설정하세요.
"""

import asyncio
import os

from wss_mqtt_client import WssMqttClient

URL = os.environ.get("WSS_MQTT_URL", "wss://api.example.com/v1/messaging")
TOKEN = os.environ.get("WSS_MQTT_TOKEN", "your_jwt_token")


async def main() -> None:
    """연결 → 발행 → 구독 → 수신 흐름 예제."""
    async with WssMqttClient(url=URL, token=TOKEN) as client:
        # 1. 토픽 구독 (응답 수신용)
        print("구독 시작: tgu/device_001/response")
        async with client.subscribe("tgu/device_001/response") as stream:
            # 2. 제어 명령 발행
            await client.publish(
                "tgu/device_001/command",
                {"action": "status", "device_id": "001"},
            )
            print("발행 완료: tgu/device_001/command")

            # 3. 응답 대기 (최대 30초)
            try:
                async for event in stream:
                    print(f"수신 [topic={event.topic}]: {event.payload}")
                    break
            except Exception as e:
                print(f"수신 실패: {e}")

    print("연결 종료")


if __name__ == "__main__":
    asyncio.run(main())
