#!/usr/bin/env python3
"""
RPC 예제 실행 (Mock 서버 자동 시작).

Mock 서버를 백그라운드로 시작한 후 rpc_call_wss_api.py 를 실행한다.
실제 운영 시에는 Mock 서버를 별도로 실행하고, WSS_MQTT_URL만 설정한다.

Usage:
    python SDK/client/python/maas-rpc-client-sdk/examples/run_rpc_example.py
"""

import asyncio
import concurrent.futures
import importlib.util
import sys
from pathlib import Path

# wss-mqtt-client mock_server 로드
_wss_root = Path(__file__).resolve().parent.parent.parent / "wss-mqtt-client"
_mock_path = _wss_root / "tests" / "mock_server.py"
_spec = importlib.util.spec_from_file_location("mock_server", _mock_path)
assert _spec and _spec.loader
_mock_module = importlib.util.module_from_spec(_spec)
sys.modules["mock_server"] = _mock_module
_spec.loader.exec_module(_mock_module)
MockWssMqttServer = _mock_module.MockWssMqttServer

from maas_rpc_client import RpcClient


async def main() -> None:
    """Mock 서버 시작 후 RPC 호출 (동기 클라이언트)."""
    server = MockWssMqttServer(host="localhost", port=0, simulate_tgu=True)
    await server.start()
    url = server.url
    print(f"Mock 서버: {url}")

    try:
        def run_sync_rpc() -> None:
            with RpcClient(
                url=url,
                vehicle_id="v001",
                transport="wss-mqtt-api",
            ) as client:
                result = client.call(
                    "RemoteUDS",
                    {"action": "readDTC", "params": {"source": 1}},
                )
                print("RPC 결과:", result)

        # 동기 클라이언트를 별도 스레드에서 실행 (서버 이벤트 루프와 분리)
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as ex:
            await loop.run_in_executor(ex, run_sync_rpc)
    finally:
        await server.stop()
        print("서버 종료")


if __name__ == "__main__":
    asyncio.run(main())
