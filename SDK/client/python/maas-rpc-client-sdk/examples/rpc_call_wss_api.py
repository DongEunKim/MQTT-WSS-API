#!/usr/bin/env python3
"""
RPC 호출 예제 (wss-mqtt-api transport).

Mock 서버와 함께 실행:
    터미널 1: python SDK/examples/run_mock_server.py
    터미널 2: WSS_MQTT_URL=ws://localhost:8765 python SDK/client/python/maas-rpc-client-sdk/examples/rpc_call_wss_api.py

환경변수:
    WSS_MQTT_URL   : API URL (기본: ws://localhost:8765)
    WSS_MQTT_TOKEN : JWT 토큰 (선택)
"""

import os

from maas_rpc_client import RpcClient

URL = os.environ.get("WSS_MQTT_URL", "ws://localhost:8765")
TOKEN = os.environ.get("WSS_MQTT_TOKEN", "")


def main() -> None:
    """RemoteUDS readDTC RPC 호출 예제."""
    with RpcClient(
        url=URL,
        token=TOKEN or None,
        vehicle_id="v001",
        transport="wss-mqtt-api",
    ) as client:
        result = client.call(
            "RemoteUDS",
            {"action": "readDTC", "params": {"source": 1}},
        )
        print("RPC 결과:", result)


if __name__ == "__main__":
    main()
