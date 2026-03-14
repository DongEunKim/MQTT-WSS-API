"""
Mock 서버를 사용한 SDK 통합 테스트.
"""

import asyncio

import pytest
import pytest_asyncio

from wss_mqtt_client import WssMqttClientAsync, WssMqttApiTransport

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
    async with WssMqttClientAsync(url=server_url) as client:
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

    async with WssMqttClientAsync(url=server_url) as client:
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

    async with WssMqttClientAsync(url=server_url) as client:
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

    async with WssMqttClientAsync(url=server_url) as client:
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
    async with WssMqttClientAsync(url=server_url) as client:
        await client.publish("topic/1", {"n": 1})
        await client.publish("topic/2", {"n": 2})

    pubs = mock_server.get_received_publishes()
    assert len(pubs) == 2
    assert [p[1]["n"] for p in pubs] == [1, 2]


@pytest.mark.asyncio
async def test_transport_wss_mqtt_api_explicit(
    server_url: str, mock_server: MockWssMqttServer
) -> None:
    """transport='wss-mqtt-api' 명시 시 정상 동작."""
    async with WssMqttClientAsync(url=server_url, transport="wss-mqtt-api") as client:
        await client.publish("test/topic", {"key": "value"})

    pubs = mock_server.get_received_publishes()
    assert len(pubs) == 1
    assert pubs[0][0] == "test/topic"


@pytest.mark.asyncio
async def test_transport_invalid_raises() -> None:
    """알 수 없는 transport 문자열 시 ValueError."""
    with pytest.raises(ValueError, match="알 수 없는 transport"):
        WssMqttClientAsync(url="ws://localhost:9999", transport="invalid")


@pytest.mark.asyncio
async def test_disconnect_unsubscribe_first(
    server_url: str, mock_server: MockWssMqttServer
) -> None:
    """disconnect(unsubscribe_first=True) 시 UNSUBSCRIBE 전송."""
    topic = "test/unsub_first"
    async with WssMqttClientAsync(url=server_url) as client:
        async with client.subscribe(topic):
            pass
        # 구독 해제되었으나, disconnect 시 unsubscribe_first로 한 번 더
        # (이미 해제됐지만, 구독 중이었다면 UNSUBSCRIBE 전송하는지 확인)
    # 구독 상태에서 disconnect(unsubscribe_first=True) 시나리오
    client = WssMqttClientAsync(url=server_url)
    await client.connect()
    async with client.subscribe(topic):
        await client.disconnect(unsubscribe_first=True)
    # disconnect 후 inject 시 수신자 0이어야 함
    await asyncio.sleep(0.05)
    count = await mock_server.inject_subscription_to_topic(topic, {"x": 1})
    assert count == 0


@pytest.mark.asyncio
async def test_publish_bytes_messagepack(
    server_url: str, mock_server: MockWssMqttServer
) -> None:
    """payload가 bytes이면 MessagePack 직렬화로 발행."""
    pytest.importorskip("msgpack")
    async with WssMqttClientAsync(url=server_url) as client:
        await client.publish("test/binary", b"binary_payload")

    pubs = mock_server.get_received_publishes()
    assert len(pubs) == 1
    assert pubs[0][0] == "test/binary"
    assert pubs[0][1] == b"binary_payload"


@pytest.mark.asyncio
async def test_auto_reconnect_init_params() -> None:
    """auto_reconnect 등 재연결 파라미터 초기화."""
    client = WssMqttClientAsync(
        url="ws://localhost:9999",
        auto_reconnect=True,
        reconnect_max_attempts=3,
        reconnect_base_delay=0.1,
        reconnect_max_delay=5.0,
        auto_resubscribe=True,
    )
    assert client._auto_reconnect is True
    assert client._reconnect_max_attempts == 3


@pytest.mark.asyncio
async def test_topic_validation_rejects_invalid(
    server_url: str, mock_server: MockWssMqttServer
) -> None:
    """토픽 검증: 잘못된 토픽 시 ValueError (validate_topic 기본 True)."""
    async with WssMqttClientAsync(url=server_url) as client:
        with pytest.raises(ValueError, match="빈 문자열"):
            await client.publish("", {"x": 1})
        with pytest.raises(ValueError, match="와일드카드"):
            await client.publish("sensor/+/temp", {"x": 1})
        with pytest.raises(ValueError, match="와일드카드"):
            client.subscribe("sensor/#")


@pytest.mark.asyncio
async def test_validate_topic_disabled_allows(
    server_url: str, mock_server: MockWssMqttServer
) -> None:
    """validate_topic=False 시 검증 생략 (와일드카드는 서버에서 거부할 수 있음)."""
    async with WssMqttClientAsync(url=server_url, validate_topic=False) as client:
        await client.publish("test/ok", {"key": "value"})
    pubs = mock_server.get_received_publishes()
    assert len(pubs) == 1


@pytest.mark.asyncio
async def test_publish_many(
    server_url: str, mock_server: MockWssMqttServer
) -> None:
    """publish_many 다수 토픽 순차 발행."""
    topic_payloads = [
        ("topic/a", {"n": 1}),
        ("topic/b", {"n": 2}),
        ("topic/c", {"n": 3}),
    ]
    async with WssMqttClientAsync(url=server_url) as client:
        results = await client.publish_many(topic_payloads)
    assert len(results) == 3
    for (topic, payload, err) in results:
        assert err is None
    pubs = mock_server.get_received_publishes()
    assert len(pubs) == 3
    assert [p[0] for p in pubs] == ["topic/a", "topic/b", "topic/c"]


@pytest.mark.asyncio
async def test_publish_many_stop_on_error(
    server_url: str, mock_server: MockWssMqttServer
) -> None:
    """publish_many stop_on_error=True 시 첫 실패에서 중단."""
    topic_payloads = [
        ("topic/ok", {"n": 1}),
        ("", {"n": 2}),  # 빈 토픽 → ValueError
        ("topic/never", {"n": 3}),
    ]
    async with WssMqttClientAsync(url=server_url) as client:
        results = await client.publish_many(topic_payloads)
    assert len(results) == 2  # ok, 빈토픽에서 중단
    assert results[0][2] is None
    assert results[1][2] is not None
    pubs = mock_server.get_received_publishes()
    assert len(pubs) == 1


@pytest.mark.asyncio
async def test_publish_many_continue_on_error(
    server_url: str, mock_server: MockWssMqttServer
) -> None:
    """publish_many stop_on_error=False 시 실패 후에도 계속 시도."""
    topic_payloads = [
        ("topic/ok1", {"n": 1}),
        ("", {"n": 2}),  # 빈 토픽
        ("topic/ok2", {"n": 3}),
    ]
    async with WssMqttClientAsync(url=server_url) as client:
        results = await client.publish_many(
            topic_payloads, stop_on_error=False
        )
    assert len(results) == 3
    assert results[0][2] is None
    assert results[1][2] is not None
    assert results[2][2] is None
    pubs = mock_server.get_received_publishes()
    assert len(pubs) == 2


@pytest.mark.asyncio
async def test_subscribe_many(
    server_url: str, mock_server: MockWssMqttServer
) -> None:
    """subscribe_many 다수 토픽 구독, event.topic으로 구분."""
    topics = ["tgu/dev1/response", "tgu/dev2/response"]
    received: list[tuple[str, dict]] = []

    async with WssMqttClientAsync(url=server_url) as client:
        async with client.subscribe_many(topics) as stream:
            async def inject():
                await asyncio.sleep(0.1)
                await mock_server.inject_subscription_to_topic(
                    "tgu/dev1/response", {"id": 1}
                )
                await mock_server.inject_subscription_to_topic(
                    "tgu/dev2/response", {"id": 2}
                )

            inject_task = asyncio.create_task(inject())
            count = 0
            async for event in stream:
                received.append((event.topic, event.payload))
                count += 1
                if count >= 2:
                    break
            await inject_task

    assert len(received) == 2
    topics_received = [r[0] for r in received]
    assert "tgu/dev1/response" in topics_received
    assert "tgu/dev2/response" in topics_received


@pytest.mark.asyncio
async def test_unsubscribe_idempotent(server_url: str) -> None:
    """unsubscribe(topic) 구독 없을 때 호출해도 예외 없음 (idempotent)."""
    async with WssMqttClientAsync(url=server_url) as client:
        await client.unsubscribe("nonexistent/topic")  # 구독 없음
        await client.unsubscribe("nonexistent/topic")  # 중복 호출


@pytest.mark.asyncio
async def test_connection_closed_sentinel_raises(
    server_url: str, mock_server: MockWssMqttServer
) -> None:
    """연결 끊김 sentinel 수신 시 구독 스트림에서 WssConnectionError 발생."""
    from wss_mqtt_client import WssConnectionError

    client = WssMqttClientAsync(url=server_url)
    await client.connect()

    # 구독 후 서버가 닫히기 전에 on_connection_lost 수동 호출 (sentinel 투입)
    topic = "test/sentinel"
    async with client.subscribe(topic) as stream:
        client._on_connection_lost()
        with pytest.raises(WssConnectionError, match="연결이 끊어졌습니다"):
            async for _ in stream:
                break
