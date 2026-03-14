"""통합 테스트 (Mock 서버 사용)."""

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

import pytest
import pytest_asyncio

from tgu_rpc import TguRpcClient


@pytest_asyncio.fixture
async def mock_server():
    """Mock WSS-MQTT 서버 (WMT/WMO 시뮬레이션 포함)."""
    server = MockWssMqttServer(host="localhost", port=0, simulate_tgu=True)
    await server.start()
    try:
        yield server
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_rpc_call_integration(mock_server: MockWssMqttServer) -> None:
    """TguRpcClient.call() — Mock 서버 통합 테스트 (동기 클라이언트)."""
    url = mock_server.url

    def run_sync_client() -> dict:
        with TguRpcClient(
            url=url,
            vehicle_id="v001",
            client_id="test_integ",
            transport="wss-mqtt-api",
        ) as client:
            return client.call(
                "RemoteUDS",
                {"action": "readDTC", "params": {"source": 1}},
            )

    # 동기 클라이언트는 별도 스레드에서 실행. run_in_executor 사용으로
    # 메인 이벤트 루프가 mock 서버 요청을 처리할 수 있음.
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor() as ex:
        result = await asyncio.wait_for(
            loop.run_in_executor(ex, run_sync_client),
            timeout=15.0,
        )

    assert result is not None
    assert result.get("action") == "readDTC"
    assert result.get("status") == "ok"
    assert "dtcList" in result
