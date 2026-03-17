"""
WssMqttClient (동기) 통합 테스트.

Mock 서버를 별도 스레드에서 실행하여 sync 클라이언트(자체 이벤트 루프)와
동시에 동작하도록 한다.
"""

import asyncio
import threading
from typing import Optional

import pytest

from wss_mqtt_client import WssMqttClient, WssConnectionError

from tests.mock_server import MockWssMqttServer


# 서버를 별도 스레드에서 실행 (sync 클라이언트가 자체 루프를 쓰므로)
_server: Optional[MockWssMqttServer] = None
_server_loop: Optional[asyncio.AbstractEventLoop] = None
_server_url: Optional[str] = None
_server_ready = threading.Event()


def _run_server(port: int = 0) -> None:
    """서버 스레드 진입점."""
    global _server, _server_loop, _server_url

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _server_loop = loop

    async def _start() -> None:
        global _server, _server_url
        _server = MockWssMqttServer(host="localhost", port=port)
        await _server.start()
        _server_url = _server.url
        _server_ready.set()

    loop.run_until_complete(_start())
    loop.run_forever()

    async def _stop() -> None:
        if _server:
            await _server.stop()

    if _server:
        loop.run_until_complete(_stop())
    loop.close()


@pytest.fixture(scope="module")
def sync_server_url() -> str:
    """Sync 테스트용 Mock 서버 URL."""
    global _server_url, _server_ready

    _server_ready.clear()
    t = threading.Thread(target=_run_server, kwargs={"port": 0}, daemon=True)
    t.start()
    _server_ready.wait(timeout=5.0)
    assert _server_url, "서버 시작 실패"
    yield _server_url

    if _server_loop and _server_loop.is_running():
        _server_loop.call_soon_threadsafe(_server_loop.stop)
    t.join(timeout=3.0)


@pytest.fixture
def mock_server_for_sync():
    """테스트에서 mock_server 접근용."""
    return _server


def test_sync_publish(sync_server_url: str, mock_server_for_sync) -> None:
    """Sync: context manager + publish."""
    with WssMqttClient(url=sync_server_url) as client:
        client.publish("test/topic", {"key": "value"})

    if mock_server_for_sync:
        pubs = mock_server_for_sync.get_received_publishes()
        assert len(pubs) == 1
        assert pubs[0][0] == "test/topic"
        assert pubs[0][1] == {"key": "value"}


def test_sync_connect_disconnect(sync_server_url: str) -> None:
    """Sync: connect/disconnect 수동 호출."""
    client = WssMqttClient(url=sync_server_url)
    client.connect()
    assert client.is_connected
    client.publish("manual/topic", {"n": 1})
    client.disconnect()
    assert not client.is_connected


def test_sync_subscribe_callback(sync_server_url: str, mock_server_for_sync) -> None:
    """Sync: subscribe(callback) + run(timeout) 수신."""
    received: list[dict] = []

    def on_message(event):
        received.append(event.payload)

    with WssMqttClient(url=sync_server_url) as client:
        client.subscribe("tgu/device_001/response", callback=on_message)
        # run으로 짧게 대기, 그 사이 inject
        import threading

        def inject():
            import asyncio

            if mock_server_for_sync:
                loop = _server_loop
                if loop:
                    asyncio.run_coroutine_threadsafe(
                        mock_server_for_sync.inject_subscription_to_topic(
                            "tgu/device_001/response", {"status": "ok"}
                        ),
                        loop,
                    ).result(timeout=2)

        t = threading.Thread(target=inject)
        t.start()
        client.run(timeout=2.0)
        t.join(timeout=1)

    assert len(received) >= 1
    assert received[0] == {"status": "ok"}


def test_sync_subscribe_before_connect(sync_server_url: str, mock_server_for_sync) -> None:
    """Sync: subscribe()를 connect() 전에 호출해도 동작."""
    received: list[dict] = []

    def on_message(event):
        received.append(event.payload)

    client = WssMqttClient(url=sync_server_url)
    client.subscribe("topic/early", callback=on_message)
    client.connect()

    import threading

    def inject():
        if mock_server_for_sync and _server_loop:
            import asyncio

            asyncio.run_coroutine_threadsafe(
                mock_server_for_sync.inject_subscription_to_topic(
                    "topic/early", {"early": True}
                ),
                _server_loop,
            ).result(timeout=2)

    t = threading.Thread(target=inject)
    t.start()
    client.run(timeout=2.0)
    t.join(timeout=1)
    client.disconnect(unsubscribe_first=True)

    assert len(received) >= 1
    assert received[0] == {"early": True}


def test_sync_disconnect_before_connect() -> None:
    """Sync: connect 없이 disconnect 호출해도 예외 없음."""
    client = WssMqttClient(url="ws://localhost:9999")
    client.disconnect()


def test_sync_publish_without_connect() -> None:
    """Sync: connect 없이 publish 시 WssConnectionError."""
    client = WssMqttClient(url="ws://invalid:9999")
    with pytest.raises(WssConnectionError, match="연결되지 않음"):
        client.publish("topic", {"x": 1})


def test_sync_invalid_transport() -> None:
    """Sync: 잘못된 transport 문자열 시 connect에서 ValueError."""
    client = WssMqttClient(url="ws://localhost:9999", transport="invalid")
    with pytest.raises(ValueError, match="알 수 없는 transport"):
        client.connect()


def test_sync_topic_validation(sync_server_url: str) -> None:
    """Sync: 토픽 검증 (빈 문자열 시 ValueError)."""
    with WssMqttClient(url=sync_server_url) as client:
        with pytest.raises(ValueError, match="빈 문자열"):
            client.publish("", {"x": 1})


def test_sync_run_without_subscribe(sync_server_url: str) -> None:
    """Sync: subscribe 없이 run(timeout) 호출해도 동작 (그냥 대기)."""
    with WssMqttClient(url=sync_server_url) as client:
        client.run(timeout=0.5)


def test_sync_callback_exception_does_not_crash(
    sync_server_url: str, mock_server_for_sync
) -> None:
    """Sync: 콜백에서 예외 발생해도 수신 루프 유지."""
    received = []
    call_count = [0]

    def on_message(event):
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("콜백 의도적 예외")
        received.append(event.payload)

    with WssMqttClient(url=sync_server_url) as client:
        client.subscribe("topic/err", callback=on_message)

        def inject_twice():
            if mock_server_for_sync and _server_loop:
                import asyncio

                for i in range(2):
                    asyncio.run_coroutine_threadsafe(
                        mock_server_for_sync.inject_subscription_to_topic(
                            "topic/err", {"n": i}
                        ),
                        _server_loop,
                    ).result(timeout=1)

        t = threading.Thread(target=inject_twice)
        t.start()
        client.run(timeout=2.0)
        t.join(timeout=1)

    assert call_count[0] == 2
    assert len(received) == 1
    assert received[0] == {"n": 1}


def test_sync_multiple_subscriptions(
    sync_server_url: str, mock_server_for_sync
) -> None:
    """Sync: 다수 토픽 구독, 각각 콜백."""
    received_a: list[dict] = []
    received_b: list[dict] = []

    def on_a(event):
        received_a.append(event.payload)

    def on_b(event):
        received_b.append(event.payload)

    with WssMqttClient(url=sync_server_url) as client:
        client.subscribe("topic/a", callback=on_a)
        client.subscribe("topic/b", callback=on_b)

        def inject():
            if mock_server_for_sync and _server_loop:
                import asyncio

                asyncio.run_coroutine_threadsafe(
                    mock_server_for_sync.inject_subscription_to_topic(
                        "topic/a", {"id": "a"}
                    ),
                    _server_loop,
                ).result(timeout=1)
                asyncio.run_coroutine_threadsafe(
                    mock_server_for_sync.inject_subscription_to_topic(
                        "topic/b", {"id": "b"}
                    ),
                    _server_loop,
                ).result(timeout=1)

        t = threading.Thread(target=inject)
        t.start()
        client.run(timeout=2.0)
        t.join(timeout=1)

    assert len(received_a) >= 1
    assert len(received_b) >= 1
    assert received_a[0] == {"id": "a"}
    assert received_b[0] == {"id": "b"}


def test_sync_stop_returns_run_forever(sync_server_url: str) -> None:
    """stop() 호출 시 run_forever()가 반환한다."""
    import time

    with WssMqttClient(url=sync_server_url) as client:
        client.subscribe("dummy", callback=lambda e: None)
        stop_done = threading.Event()

        def stopper() -> None:
            time.sleep(0.3)
            client.stop()
            stop_done.set()

        threading.Thread(target=stopper, daemon=True).start()
        client.run_forever()  # stop()으로 반환되어야 함
        stop_done.wait(timeout=1.0)

    assert stop_done.is_set()
