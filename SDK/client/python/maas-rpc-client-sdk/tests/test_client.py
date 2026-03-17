"""RpcClientAsync 단위 테스트 (Mock 기반)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from maas_rpc_client import RpcClientAsync
from maas_rpc_client.exceptions import RpcError, RpcTimeoutError


@pytest_asyncio.fixture
def mock_wss_client():
    """WssMqttClientAsync Mock."""
    client = AsyncMock()
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_call_returns_result(mock_wss_client: AsyncMock) -> None:
    """call() 성공 시 result 반환."""
    request_id = "abc123"
    result_data = {"dtcList": []}

    async def fake_subscribe_enter(*args, **kwargs):
        return fake_stream

    async def fake_subscribe_exit(*args):
        pass

    received_publish: list[tuple[str, dict]] = []

    async def fake_publish(topic: str, payload: dict) -> None:
        received_publish.append((topic, payload))
        # 시뮬레이션: 발행 직후 응답 주입
        if payload.get("response_topic") and payload.get("request_id"):
            response = {
                "request_id": payload["request_id"],
                "result": result_data,
                "error": None,
            }
            await fake_stream._queue.put(
                MagicMock(payload=response, topic=payload["response_topic"])
            )

    import asyncio

    fake_stream = AsyncMock()
    fake_stream.__aenter__ = AsyncMock(return_value=fake_stream)
    fake_stream.__aexit__ = AsyncMock(return_value=None)
    fake_stream._queue = asyncio.Queue()
    fake_stream.__aiter__ = lambda self: self
    fake_stream._iter_done = False

    _count = [0]

    async def fake_anext(self):
        _count[0] += 1
        if _count[0] > 1:
            raise StopAsyncIteration
        return await asyncio.wait_for(fake_stream._queue.get(), timeout=2.0)

    fake_stream.__anext__ = fake_anext

    mock_wss_client.subscribe = MagicMock(return_value=fake_stream)
    mock_wss_client.publish = AsyncMock(side_effect=fake_publish)

    with patch(
        "maas_rpc_client.client_async.WssMqttClientAsync",
        return_value=mock_wss_client,
    ):
        async with RpcClientAsync(
            url="ws://test",
            thing_name="device_001",
            oem="acme",
            asset="VIN123",
            client_id="test_client",
        ) as client:
            client._wss_client = mock_wss_client
            result = await client.call(
                "RemoteUDS",
                {"action": "readDTC", "params": {"source": 1}},
            )

    assert result == result_data
    assert len(received_publish) == 1
    topic, payload = received_publish[0]
    assert topic == "WMT/RemoteUDS/device_001/acme/VIN123/request"
    assert payload["request"]["action"] == "readDTC"
    assert payload["request"]["params"] == {"source": 1}
    assert "request_id" in payload
    assert payload["response_topic"] == "WMO/RemoteUDS/device_001/acme/VIN123/test_client/response"


@pytest.mark.asyncio
async def test_call_raises_rpc_error_on_error_field(mock_wss_client: AsyncMock) -> None:
    """call() 시 error 필드 있으면 RpcError 발생."""
    import asyncio

    fake_stream = AsyncMock()
    fake_stream.__aenter__ = AsyncMock(return_value=fake_stream)
    fake_stream.__aexit__ = AsyncMock(return_value=None)
    fake_stream._queue = asyncio.Queue()
    fake_stream._iter_done = False

    async def fake_publish(topic: str, payload: dict) -> None:
        error_response = {
            "request_id": payload["request_id"],
            "result": None,
            "error": {"code": "TIMEOUT", "message": "처리 시간 초과"},
        }
        await fake_stream._queue.put(MagicMock(payload=error_response))

    async def fake_anext(self):
        if fake_stream._iter_done:
            raise StopAsyncIteration
        fake_stream._iter_done = True
        return await asyncio.wait_for(fake_stream._queue.get(), timeout=2.0)

    fake_stream.__aiter__ = lambda self: self
    fake_stream.__anext__ = fake_anext

    mock_wss_client.subscribe = MagicMock(return_value=fake_stream)
    mock_wss_client.publish = AsyncMock(side_effect=fake_publish)

    with patch(
        "maas_rpc_client.client_async.WssMqttClientAsync",
        return_value=mock_wss_client,
    ):
        async with RpcClientAsync(
            url="ws://test",
            thing_name="device_001",
            oem="acme",
            asset="VIN123",
            client_id="test_client",
        ) as client:
            client._wss_client = mock_wss_client
            with pytest.raises(RpcError) as exc_info:
                await client.call("RemoteUDS", {"action": "readDTC"})
            assert exc_info.value.code == "TIMEOUT"
            assert "처리 시간 초과" in str(exc_info.value)


@pytest.mark.asyncio
async def test_call_raises_on_missing_action(mock_wss_client: AsyncMock) -> None:
    """payload에 action 없으면 ValueError."""
    with patch(
        "maas_rpc_client.client_async.WssMqttClientAsync",
        return_value=mock_wss_client,
    ):
        async with RpcClientAsync(
            url="ws://test", thing_name="device_001", oem="acme", asset="VIN123"
        ) as client:
            with pytest.raises(ValueError, match="action"):
                await client.call("RemoteUDS", {"params": {}})
