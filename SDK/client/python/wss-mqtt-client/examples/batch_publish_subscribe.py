#!/usr/bin/env python3
"""
배치 publish/subscribe 예제.

publish_many()와 subscribe_many() 사용법을 보여준다.

Mock 서버 테스트:
    # 터미널 1: Mock 서버
    python SDK/examples/run_mock_server.py

    # 터미널 2: 배치 예제 실행 (프로젝트 루트에서)
    WSS_MQTT_URL=ws://localhost:8765 python SDK/client/python/wss-mqtt-client/examples/batch_publish_subscribe.py

환경변수:
    WSS_MQTT_URL : API URL (기본: ws://localhost:8765)
"""

import asyncio
import os

from wss_mqtt_client import WssConnectionError, WssMqttClientAsync

URL = os.environ.get("WSS_MQTT_URL", "ws://localhost:8765")


async def main() -> None:
    """배치 발행 및 다수 토픽 구독 예제."""
    async with WssMqttClientAsync(url=URL) as client:
        # 1. publish_many: 다수 토픽에 순차 발행
        topic_payloads = [
            ("batch/topic/a", {"id": 1, "msg": "first"}),
            ("batch/topic/b", {"id": 2, "msg": "second"}),
            ("batch/topic/c", {"id": 3, "msg": "third"}),
        ]
        print("[배치 발행] publish_many()")
        results = await client.publish_many(topic_payloads)
        for topic, payload, err in results:
            if err:
                print(f"  실패: {topic} - {err}")
            else:
                print(f"  성공: {topic} -> {payload}")

        # 2. subscribe_many: 다수 토픽 동시 구독
        topics = [
            "tgu/device_001/response",
            "tgu/device_002/response",
        ]
        print("\n[다수 토픽 구독] subscribe_many()")
        async with client.subscribe_many(topics) as stream:
            # 명령 발행 (Mock 서버 TGU 시뮬레이션)
            await client.publish(
                "tgu/device_001/command",
                {"action": "status", "device_id": "001"},
            )
            try:
                async for event in stream:
                    print(f"  수신 [topic={event.topic}]: {event.payload}")
                    break
            except WssConnectionError as e:
                print(f"  연결 끊김: {e}")

    print("\n연결 종료")


if __name__ == "__main__":
    asyncio.run(main())
