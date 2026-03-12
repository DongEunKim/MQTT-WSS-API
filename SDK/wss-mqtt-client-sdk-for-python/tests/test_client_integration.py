"""
Mock 서버를 사용한 SDK 통합 테스트.
"""

import asyncio

import pytest
import pytest_asyncio

from wss_mqtt_client import WssMqttClient

from tests.mock_server import MockWssMqttServer


@pytest_asyncio.fixture
async def mock_server():
    """Mock WSS-MQTT 서버 인스턴스."""
    server = MockWssMqttServer(host="localhost", port=0)
    await server.start()
    try:
        yield server
    finally:
        await server.stop()


@pytest_asyncio.fixture
async def server_url(mock_server):
    """Mock 서버 URL."""
    return mock_server.url


@pytest.mark.asyncio
async def test_publish_receives_ack(
    server_url: str, mock_server: MockWssMqttServer
) -> None:
    """publish() 호출 시 ACK 200 수신."""
    async with WssMqttClient(url=server_url) as client:
        await client.publish("test/topic", {"key": "value"})

    pubs = mock_server.get_received_publishes()
    assert len(pubs) == 1
    assert pubs[0][0] == "test/topic"
    assert pubs[0][1] == {"key": "value"}


@pytest.mark.asyncio
async def test_subscribe_receives_injected_message(
    server_url: str, mock_server: MockWssMqttServer
) -> None:
    """subscribe() 후 서버가 주입한 SUBSCRIPTION 수신."""
    response_topic = "tgu/device_001/response"
    received: list[dict] = []

    async with WssMqttClient(url=server_url) as client:
        async with client.subscribe(response_topic) as stream:
            # 백그라운드에서 SUBSCRIPTION 주입
            async def inject():
                await asyncio.sleep(0.1)
                count = await mock_server.inject_subscription_to_topic(
                    response_topic, {"status": "ok"}
                )
                assert count == 1

            inject_task = asyncio.create_task(inject())
            async for event in stream:
                received.append(event.payload)
                break
            await inject_task

    assert len(received) == 1
    assert received[0] == {"status": "ok"}


@pytest.mark.asyncio
async def test_rpc_pattern(
    server_url: str, mock_server: MockWssMqttServer
) -> None:
    """RPC 패턴: 구독 → 발행 → 응답 수신."""
    command_topic = "tgu/device_001/command"
    response_topic = "tgu/device_001/response"
    response_payload = {"result": "success", "device_id": "001"}

    async with WssMqttClient(url=server_url) as client:
        async with client.subscribe(response_topic) as stream:
            # 명령 발행
            await client.publish(command_topic, {"action": "get_status"})
            # Mock: TGU 응답 시뮬레이션
            await asyncio.sleep(0.05)
            await mock_server.inject_subscription_to_topic(
                response_topic, response_payload
            )
            # 응답 수신
            async for event in stream:
                assert event.payload == response_payload
                assert event.topic == response_topic
                break

    pubs = mock_server.get_received_publishes()
    assert any(p[0] == command_topic for p in pubs)


@pytest.mark.asyncio
async def test_unsubscribe_on_context_exit(
    server_url: str, mock_server: MockWssMqttServer
) -> None:
    """subscribe() context 종료 시 UNSUBSCRIBE 전송."""
    response_topic = "test/unsub"

    async with WssMqttClient(url=server_url) as client:
        async with client.subscribe(response_topic):
            pass  # 바로 종료
        # UNSUBSCRIBE가 전송되었을 것이므로, 이후 inject해도 수신되지 않음
        await asyncio.sleep(0.05)
        count = await mock_server.inject_subscription_to_topic(
            response_topic, {"late": True}
        )
        # 구독 해제되었으므로 수신자 0
        assert count == 0


@pytest.mark.asyncio
async def test_multiple_publishes(
    server_url: str, mock_server: MockWssMqttServer
) -> None:
    """연속 publish 동작."""
    async with WssMqttClient(url=server_url) as client:
        await client.publish("topic/1", {"n": 1})
        await client.publish("topic/2", {"n": 2})

    pubs = mock_server.get_received_publishes()
    assert len(pubs) == 2
    assert [p[1]["n"] for p in pubs] == [1, 2]
