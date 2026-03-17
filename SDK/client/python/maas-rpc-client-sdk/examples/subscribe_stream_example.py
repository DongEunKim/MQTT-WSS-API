#!/usr/bin/env python3
"""
토픽 구독 예제 — 동기 / 비동기 두 가지 사용법.

구독할 토픽을 직접 지정하고, 수신 이벤트를 처리한다.
(구독형 스트림 토픽은 별도 사양으로 확정되지 않았음. 범용 subscribe 예제로 사용.)

Usage:
    터미널 1: python SDK/examples/run_mock_server.py
    터미널 2: python SDK/client/python/maas-rpc-client-sdk/examples/subscribe_stream_example.py [--async]
              동기 모드: 5초 후 자동 종료. 비동기: 5초 수신 후 종료.
"""

import argparse
import asyncio
import os
import threading

from maas_rpc_client import RpcClient, RpcClientAsync

URL = os.environ.get("WSS_MQTT_URL", "ws://localhost:8765")
TOKEN = os.environ.get("WSS_MQTT_TOKEN", "")

# 구독할 토픽 (환경변수 또는 직접 지정)
TOPIC = os.environ.get("SUBSCRIBE_TOPIC", "WMO/RemoteDashboard/device_001/acme/VIN123/client_demo/response")


def run_sync() -> None:
    """동기: subscribe(callback) + run_forever(). 5초 후 stop()."""
    client = RpcClient(
        url=URL,
        token=TOKEN or None,
        thing_name="device_001",
        oem="acme",
        asset="VIN123",
        transport="wss-mqtt-api",
    )
    client.connect()
    received: list = []

    def on_event(event) -> None:
        """수신 이벤트 처리."""
        received.append(event.payload)
        print(f"[동기] 수신: {event.payload}")

    client.subscribe(TOPIC, on_event)

    def auto_stop() -> None:
        import time
        time.sleep(5)
        client.stop()

    t = threading.Thread(target=auto_stop, daemon=True)
    t.start()

    print(f"[동기] 구독 시작: {TOPIC} (5초 후 종료)")
    client.run_forever()
    client.disconnect()
    print(f"[동기] 종료. 수신 건수: {len(received)}")


async def run_async() -> None:
    """비동기: subscribe() async with ... as stream."""
    async with RpcClientAsync(
        url=URL,
        token=TOKEN or None,
        thing_name="device_001",
        oem="acme",
        asset="VIN123",
        transport="wss-mqtt-api",
    ) as client:
        print(f"[비동기] 구독 시작: {TOPIC} (5초 후 종료)")
        try:
            async with client.subscribe(TOPIC, timeout=5.0) as stream:
                async for event in stream:
                    print(f"[비동기] 수신: {event.payload}")
        except Exception as e:
            print(f"[비동기] 종료: {e}")


def main() -> None:
    """CLI 진입점."""
    parser = argparse.ArgumentParser(description="토픽 구독 예제")
    parser.add_argument("--async", dest="use_async", action="store_true", help="비동기 모드")
    args = parser.parse_args()

    if args.use_async:
        asyncio.run(run_async())
    else:
        run_sync()


if __name__ == "__main__":
    main()
