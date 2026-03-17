#!/usr/bin/env python3
"""
RPC 호출 예제 (MQTT 브로커 직접 연결).

실제 MQTT 브로커에 직접 연결하여 RPC를 수행한다.
엣지 디바이스 시뮬레이터가 브로커에 연결되어 있어야 한다.

Usage:
    # 터미널 1: cd SDK && docker compose up -d
    # 터미널 2: python SDK/examples/tgu_simulator_mqtt.py
    # 터미널 3 (선택): python SDK/examples/mqtt_topic_monitor.py
    # 터미널 4: python SDK/client/python/maas-rpc-client-sdk/examples/rpc_call_mqtt.py

환경변수:
    MQTT_URL   : MQTT 브로커 URL (기본: mqtt://localhost:1883)
    MQTT_TOKEN : JWT 토큰 (선택)
"""

import os

from maas_rpc_client import RpcClient

URL = os.environ.get("MQTT_URL", "mqtt://localhost:1883")
TOKEN = os.environ.get("MQTT_TOKEN", "")


def main() -> None:
    """RemoteUDS readDTC RPC 호출 (MQTT 직접 연결)."""
    with RpcClient(
        url=URL,
        token=TOKEN or None,
        thing_name="device_001",
        oem="acme",
        asset="VIN123",
        transport="mqtt",
    ) as client:
        result = client.call(
            "RemoteUDS",
            {"action": "readDTC", "params": {"source": 1}},
        )
        print("RPC 결과:", result)


if __name__ == "__main__":
    main()
