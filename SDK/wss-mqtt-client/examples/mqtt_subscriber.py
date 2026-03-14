#!/usr/bin/env python3
"""
MQTT Transport 구독 예제.

네이티브 MQTT 브로커(Mosquitto 등)에 연결하여 토픽을 구독한다.

Usage:
    # MQTT 브로커 실행 (Docker)
    # cd SDK && docker compose up -d

    # TCP 연결 (기본)
    python SDK/wss-mqtt-client/examples/mqtt_subscriber.py

    # WebSocket 연결
    MQTT_URL=ws://localhost:9001 python SDK/wss-mqtt-client/examples/mqtt_subscriber.py

환경변수:
    MQTT_URL       : MQTT 브로커 URL (기본: mqtt://localhost:1883)
    MQTT_TOPIC     : 구독 토픽 (기본: test/mqtt)
    AUTO_RECONNECT : 1이면 자동 재연결 활성화
"""

import asyncio
import os

from wss_mqtt_client import WssConnectionError, WssMqttClientAsync

URL = os.environ.get("MQTT_URL", "mqtt://localhost:1883")
TOPIC = os.environ.get("MQTT_TOPIC", "test/mqtt")
AUTO_RECONNECT = os.environ.get("AUTO_RECONNECT", "").lower() in ("1", "true", "yes")


async def main() -> None:
    print(f"[MQTT 구독] 연결 중: {URL}")
    print(f"[MQTT 구독] 토픽: {TOPIC}")
    if AUTO_RECONNECT:
        print("[MQTT 구독] 자동 재연결: 활성화")
    print("[MQTT 구독] 메시지 대기 중... (Ctrl+C 종료)\n")

    try:
        async with WssMqttClientAsync(
            url=URL,
            transport="mqtt",
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
        print(f"[MQTT 구독] 연결 끊김: {e}")
    except Exception as e:
        print(f"[MQTT 구독] 오류: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
