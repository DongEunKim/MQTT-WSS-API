"""
RPC 패턴 예제: 제어 명령 발행 후 응답 토픽에서 1건 수신.

사양서 8.4: 응답 토픽 구독은 제어 명령 발행 직전에 수행하는 것을 권장.
"""

import asyncio
import os

from wss_mqtt_client import WssMqttClient

URL = os.environ.get("WSS_MQTT_URL", "wss://api.example.com/v1/messaging")
TOKEN = os.environ.get("WSS_MQTT_TOKEN", "your_jwt_token")

# 예시 토픽 (실제 API 사양에 맞게 수정)
COMMAND_TOPIC = "tgu/device_001/command"
RESPONSE_TOPIC = "tgu/device_001/response"


async def request_response(
    client: WssMqttClient,
    command_topic: str,
    response_topic: str,
    payload: dict,
    timeout: float = 30.0,
) -> dict | None:
    """
    제어 명령 발행 후 응답 1건 수신 (RPC 패턴).

    Returns:
        응답 payload 또는 타임아웃 시 None
    """
    async with client.subscribe(response_topic, timeout=timeout) as stream:
        await client.publish(command_topic, payload)
        async for event in stream:
            return event.payload
    return None


async def main() -> None:
    """RPC 흐름: command 발행 → response 1건 수신."""
    async with WssMqttClient(url=URL, token=TOKEN) as client:
        result = await request_response(
            client,
            COMMAND_TOPIC,
            RESPONSE_TOPIC,
            {"action": "get_status"},
        )
        if result is not None:
            print("응답:", result)
        else:
            print("타임아웃 또는 응답 없음")


if __name__ == "__main__":
    asyncio.run(main())
