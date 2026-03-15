#!/usr/bin/env python3
"""
call_stream 예제 — 1요청 → 멀티 응답.

동기(콜백) / 비동기(iterator) 두 가지 사용법.
Mock 서버가 스트리밍 응답(done: true)을 지원해야 동작.

Usage:
    터미널 1: python SDK/examples/run_mock_server.py
    터미널 2: python SDK/tgu-rpc-sdk/examples/call_stream_example.py [--async]
"""

import argparse
import asyncio
import os

from tgu_rpc import TguRpcClient, TguRpcClientAsync

URL = os.environ.get("WSS_MQTT_URL", "ws://localhost:8765")
TOKEN = os.environ.get("WSS_MQTT_TOKEN", "")


def run_sync() -> None:
    """동기: callback + on_complete."""
    with TguRpcClient(
        url=URL,
        token=TOKEN or None,
        vehicle_id="v001",
        transport="wss-mqtt-api",
    ) as client:
        chunks: list = []

        def on_chunk(chunk) -> None:
            chunks.append(chunk)
            print("chunk:", chunk)

        def on_done() -> None:
            print("스트림 완료")

        try:
            client.call_stream(
                "RemoteUDS",
                {"action": "readDTCStream", "params": {"source": 1}},
                callback=on_chunk,
                on_complete=on_done,
                timeout=10.0,
            )
        except Exception as e:
            print("오류:", e)
        print("수신 청크 수:", len(chunks))


async def run_async() -> None:
    """비동기: async for chunk in call_stream(...)."""
    async with TguRpcClientAsync(
        url=URL,
        token=TOKEN or None,
        vehicle_id="v001",
        transport="wss-mqtt-api",
    ) as client:
        chunks: list = []
        try:
            async for chunk in client.call_stream(
                "RemoteUDS",
                {"action": "readDTCStream", "params": {"source": 1}},
                timeout=10.0,
            ):
                chunks.append(chunk)
                print("chunk:", chunk)
            print("스트림 완료")
        except Exception as e:
            print("오류:", e)
        print("수신 청크 수:", len(chunks))


def main() -> None:
    parser = argparse.ArgumentParser(description="call_stream 예제")
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
