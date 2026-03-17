#!/usr/bin/env python3
"""
subscribe_stream 예제 — 구독형 스트림 (VISSv3 스타일).

동기: callback + run_forever() (+ stop()으로 종료)
비동기: async with subscribe_stream(...) as stream: async for ...

엣지 디바이스/Mock이 WMO/.../stream/{api} 토픽에 발행해야 동작.

Usage:
    터미널 1: python SDK/examples/run_mock_server.py  # 또는 디바이스 시뮬레이터
    터미널 2: python SDK/client/python/maas-rpc-client-sdk/examples/subscribe_stream_example.py [--async]
              동기 모드: 5초 후 stop()으로 종료. 비동기: 5초 수신 후 종료.
"""

import argparse
import asyncio
import os
import threading
import time

from maas_rpc_client import RpcClient, RpcClientAsync

URL = os.environ.get("WSS_MQTT_URL", "ws://localhost:8765")
TOKEN = os.environ.get("WSS_MQTT_TOKEN", "")


def run_sync() -> None:
    """동기: subscribe_stream(callback) + run_forever(). 5초 후 stop()."""
    client = RpcClient(
        url=URL,
        token=TOKEN or None,
        vehicle_id="v001",
        transport="wss-mqtt-api",
    )
    client.connect()
    count = [0]

    def on_event(event) -> None:
        count[0] += 1
        print("event:", getattr(event, "payload", event))

    client.subscribe_stream("RemoteDashboard", "vehicleSpeed", callback=on_event)

    def stop_after() -> None:
        time.sleep(5.0)
        print("stop() 호출")
        client.stop()

    threading.Thread(target=stop_after, daemon=True).start()
    print("run_forever() 시작 (5초 후 stop)")
    client.run_forever()
    client.disconnect()
    print("수신 이벤트 수:", count[0])


async def run_async() -> None:
    """비동기: async with subscribe_stream(...) as stream: async for ..."""
    count = [0]

    async with RpcClientAsync(
        url=URL,
        token=TOKEN or None,
        vehicle_id="v001",
        transport="wss-mqtt-api",
    ) as client:
        async with client.subscribe_stream(
            "RemoteDashboard", "vehicleSpeed", timeout=5.0
        ) as stream:
            async for event in stream:
                count[0] += 1
                print("event:", getattr(event, "payload", event))
                if count[0] >= 10:
                    break

    print("수신 이벤트 수:", count[0])


def main() -> None:
    parser = argparse.ArgumentParser(description="subscribe_stream 예제")
    parser.add_argument(
        "--async",
        dest="use_async",
        action="store_true",
        help="비동기(iterator) 방식 사용",
    )
    args = parser.parse_args()
    if args.use_async:
        asyncio.run(run_async())
    else:
        run_sync()


if __name__ == "__main__":
    main()
