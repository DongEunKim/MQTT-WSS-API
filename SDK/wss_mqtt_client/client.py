"""
WssMqttClientAsync - WSS-MQTT API 비동기 클라이언트.

고급 사용자용. 스트리밍, 다중 구독, async/await 통합에 적합.
"""

import asyncio
import logging
import queue
from typing import Any, AsyncIterator, Iterable, Optional, Union

from .constants import (
    ACK_TIMEOUT_DEFAULT,
    CODE_OK,
    CONNECTION_CLOSED_SENTINEL,
    SUBSCRIPTION_QUEUE_MAXSIZE_DEFAULT,
)
from .exceptions import (
    AckError,
    AckTimeoutError,
    SubscriptionTimeoutError,
    WssConnectionError,
)
from .models import AckEvent, Action as ActionEnum, SubscriptionEvent
from .protocol import build_request, encode_request, encode_request_binary
from .transport import TransportInterface, MqttTransport, WssMqttApiTransport
from .validation import validate_topic as _validate_topic

logger = logging.getLogger(__name__)


class SubscriptionStream:
    """
    구독 스트림. async for로 SUBSCRIPTION 이벤트를 소비한다.

    동일 토픽 다중 구독 시 참조 카운트로 관리하여, 마지막 스트림 종료 시에만
    UNSUBSCRIBE를 전송한다.

    주의:
        async for로 이벤트를 소비하지 않으면 구독 큐(queue_maxsize)가 쌓여
        메모리가 증가할 수 있다. 메시지를 사용하지 않는 구독은 적극적으로
        소비하거나, queue_maxsize를 적게 설정하라.

    Usage:
        async for event in client.subscribe("topic/response"):
            print(event.payload)
    """

    def __init__(
        self,
        client: "WssMqttClientAsync",
        topic: str,
        timeout: Optional[float] = None,
        queue_maxsize: Optional[int] = None,
    ) -> None:
        self._client = client
        self._topic = topic
        self._timeout = timeout
        maxsize = (
            queue_maxsize
            if queue_maxsize is not None
            else SUBSCRIPTION_QUEUE_MAXSIZE_DEFAULT
        )
        self._queue: asyncio.Queue[SubscriptionEvent] = (
            asyncio.Queue(maxsize=maxsize) if maxsize > 0 else asyncio.Queue()
        )
        self._req_id: Optional[str] = None
        self._subscribed = False
        self._closed = False

    async def __aenter__(self) -> "SubscriptionStream":
        req = build_request(ActionEnum.SUBSCRIBE, self._topic)
        self._req_id = req.req_id
        self._client._register_subscription_handler(self._req_id, self._queue)
        try:
            await self._client._send_and_wait_ack(req)
            self._subscribed = True
            self._client._add_topic_subscriber(self._topic, self._req_id)
        except Exception:
            self._client._unregister_subscription_handler(self._req_id)
            raise
        return self

    async def __aexit__(self, *args: Any) -> None:
        self._closed = True
        try:
            if self._subscribed and self._req_id and self._client._transport.is_connected:
                await self._client._unsubscribe_and_unregister(
                    self._topic, self._req_id
                )
        except (WssConnectionError, OSError, ConnectionError):
            pass  # 연결 끊김 시 UNSUBSCRIBE 생략
        except Exception as e:
            if "ConnectionClosed" in type(e).__name__:
                pass  # websockets.exceptions.ConnectionClosed* 처리
            else:
                raise
        finally:
            self._client._unregister_subscription_handler(self._req_id or "")

    def __aiter__(self) -> AsyncIterator[SubscriptionEvent]:
        return self

    async def __anext__(self) -> SubscriptionEvent:
        if not self._subscribed:
            raise RuntimeError(
                "SubscriptionStream must be used as async context manager: "
                "async with client.subscribe(topic) as stream:"
            )
        try:
            item = await asyncio.wait_for(
                self._queue.get(),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError as e:
            raise SubscriptionTimeoutError(
                self._topic, self._req_id or "", self._timeout or 0
            ) from e
        if item is CONNECTION_CLOSED_SENTINEL:
            raise WssConnectionError("연결이 끊어졌습니다")
        return item


class MultiTopicSubscriptionStream:
    """
    다수 토픽 통합 구독 스트림.

    subscribe_many()로 반환된다. async with 진입 시 모든 토픽에 SUBSCRIBE하고,
    async for로 수신 시 event.topic으로 발신 토픽을 구분한다.
    """

    def __init__(
        self,
        client: "WssMqttClientAsync",
        topics: Iterable[str],
        timeout: Optional[float] = None,
        queue_maxsize: Optional[int] = None,
    ) -> None:
        self._client = client
        self._topics = list(topics)
        self._timeout = timeout
        maxsize = (
            queue_maxsize
            if queue_maxsize is not None
            else SUBSCRIPTION_QUEUE_MAXSIZE_DEFAULT
        )
        self._queue: asyncio.Queue[SubscriptionEvent] = (
            asyncio.Queue(maxsize=maxsize) if maxsize > 0 else asyncio.Queue()
        )
        self._topic_to_req_id: dict[str, str] = {}
        self._subscribed = False
        self._closed = False

    async def __aenter__(self) -> "MultiTopicSubscriptionStream":
        for topic in self._topics:
            req = build_request(ActionEnum.SUBSCRIBE, topic)
            self._topic_to_req_id[topic] = req.req_id
            self._client._register_subscription_handler(req.req_id, self._queue)
            try:
                await self._client._send_and_wait_ack(req)
                self._client._add_topic_subscriber(topic, req.req_id)
            except Exception:
                for t, rid in list(self._topic_to_req_id.items()):
                    self._client._unregister_subscription_handler(rid)
                    self._client._remove_topic_subscriber(t, rid)
                self._topic_to_req_id.clear()
                raise
        self._subscribed = True
        return self

    async def __aexit__(self, *args: Any) -> None:
        self._closed = True
        if self._subscribed and self._client._transport.is_connected:
            for topic, req_id in list(self._topic_to_req_id.items()):
                try:
                    await self._client._unsubscribe_and_unregister(
                        topic, req_id
                    )
                except (WssConnectionError, OSError, ConnectionError):
                    pass
                except Exception as e:
                    if "ConnectionClosed" not in type(e).__name__:
                        raise
        for req_id in self._topic_to_req_id.values():
            self._client._unregister_subscription_handler(req_id)
        self._topic_to_req_id.clear()

    def __aiter__(self) -> AsyncIterator[SubscriptionEvent]:
        return self

    async def __anext__(self) -> SubscriptionEvent:
        if not self._subscribed:
            raise RuntimeError(
                "MultiTopicSubscriptionStream must be used as async context "
                "manager: async with client.subscribe_many(topics) as stream:"
            )
        try:
            item = await asyncio.wait_for(
                self._queue.get(),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            raise SubscriptionTimeoutError(
                ",".join(self._topics), "", self._timeout or 0
            )
        if item is CONNECTION_CLOSED_SENTINEL:
            raise WssConnectionError("연결이 끊어졌습니다")
        return item


class WssMqttClientAsync:
    """
    WSS-MQTT API 클라이언트.

    TGU/MQTT와 토픽 기반 publish/subscribe로 통신한다.

    고급 사용자용. 기본 사용은 WssMqttClient(sync)를 권장.
    """

    def __init__(
        self,
        url: str,
        token: Optional[str] = None,
        *,
        transport: Union[str, TransportInterface] = "wss-mqtt-api",
        ack_timeout: float = ACK_TIMEOUT_DEFAULT,
        use_query_token: bool = False,
        ping_interval: float = 30.0,
        ping_timeout: float = 10.0,
        auto_reconnect: bool = False,
        reconnect_max_attempts: int = 5,
        reconnect_base_delay: float = 1.0,
        reconnect_max_delay: float = 60.0,
        auto_resubscribe: bool = True,
        validate_topic: bool = True,
        topic_max_length: int = 512,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        """
        Args:
            url: wss://[API_DOMAIN]/v1/messaging
            token: JWT 또는 API 키
            transport: "wss-mqtt-api" 또는 TransportInterface 인스턴스. 기본 wss-mqtt-api
            ack_timeout: ACK 수신 대기 시간(초). 기본 5초
            use_query_token: True면 토큰을 쿼리 파라미터로 전달
            ping_interval: WebSocket Ping 간격(초). wss-mqtt-api 전용
            ping_timeout: Pong 미수신 시 연결 종료(초). wss-mqtt-api 전용
            auto_reconnect: 연결 끊김 시 자동 재연결
            reconnect_max_attempts: 최대 재시도 횟수
            reconnect_base_delay: 재연결 대기 기본 시간(초), exponential backoff 적용
            reconnect_max_delay: 재연결 대기 최대 시간(초)
            auto_resubscribe: 재연결 후 구독 자동 복구
            validate_topic: True면 publish/subscribe/unsubscribe 시 토픽 형식 검증
            topic_max_length: 토픽 최대 길이 (validate_topic True 시)
            logger: 로거
        """
        if isinstance(transport, str):
            if transport == "wss-mqtt-api":
                self._transport = WssMqttApiTransport(
                    url,
                    token,
                    use_query_token=use_query_token,
                    ping_interval=ping_interval,
                    ping_timeout=ping_timeout,
                    logger=logger,
                )
            elif transport == "mqtt":
                self._transport = MqttTransport(url, token, logger=logger)
            else:
                raise ValueError(
                    f"알 수 없는 transport: {transport!r}. "
                    "'wss-mqtt-api', 'mqtt' 또는 TransportInterface 인스턴스를 사용하세요."
                )
        else:
            self._transport = transport
        self._ack_timeout = ack_timeout
        self._log = logger if logger is not None else logging.getLogger(__name__)
        self._auto_reconnect = auto_reconnect
        self._reconnect_max_attempts = reconnect_max_attempts
        self._reconnect_base_delay = reconnect_base_delay
        self._reconnect_max_delay = reconnect_max_delay
        self._auto_resubscribe = auto_resubscribe
        self._validate_topic = validate_topic
        self._topic_max_length = topic_max_length
        self._user_disconnect = False
        self._reconnect_task: Optional[asyncio.Task[None]] = None

        self._ack_futures: dict[str, asyncio.Future[AckEvent]] = {}
        self._subscription_handlers: dict[
            str, asyncio.Queue[SubscriptionEvent]
        ] = {}
        self._topic_to_req_ids: dict[str, set[str]] = {}
        self._receive_task: Optional[asyncio.Task[None]] = None

    async def connect(self) -> None:
        """WebSocket 연결 수립 및 수신 루프 시작."""
        self._user_disconnect = False
        await self._transport.connect()
        self._transport.set_receive_callback(self._on_message)
        if hasattr(self._transport, "set_on_connection_lost"):
            self._transport.set_on_connection_lost(self._on_connection_lost)
        self._receive_task = asyncio.create_task(
            self._transport.receive_loop()
        )
        if self._auto_reconnect:
            self._receive_task.add_done_callback(
                self._on_receive_task_done
            )

    def _on_connection_lost(self) -> None:
        """연결 끊김 시 모든 구독 스트림에 sentinel 투입."""
        for handler_queue in self._subscription_handlers.values():
            try:
                handler_queue.put_nowait(CONNECTION_CLOSED_SENTINEL)
            except queue.Full:
                pass

    def _on_receive_task_done(self, task: asyncio.Task[None]) -> None:
        """receive_task 완료 시 재연결 시도 (auto_reconnect인 경우)."""
        if self._user_disconnect:
            return
        if not self._auto_reconnect:
            return
        if task.cancelled():
            return
        try:
            task.result()
        except Exception:
            pass
        loop = task.get_loop()
        if loop.is_running():
            self._reconnect_task = loop.create_task(
                self._reconnect_loop()
            )

    async def _reconnect_loop(self) -> None:
        """exponential backoff 재연결."""
        for attempt in range(self._reconnect_max_attempts):
            if self._user_disconnect:
                return
            delay = min(
                self._reconnect_base_delay * (2**attempt),
                self._reconnect_max_delay,
            )
            self._log.info("재연결 시도 %d/%d (%.1f초 후)", attempt + 1, self._reconnect_max_attempts, delay)
            await asyncio.sleep(delay)
            if self._user_disconnect:
                return
            try:
                await self._transport.connect()
                self._transport.set_receive_callback(self._on_message)
                if hasattr(self._transport, "set_on_connection_lost"):
                    self._transport.set_on_connection_lost(self._on_connection_lost)
                if self._auto_resubscribe:
                    await self._resubscribe_all()
                self._receive_task = asyncio.create_task(
                    self._transport.receive_loop()
                )
                if self._auto_reconnect:
                    self._receive_task.add_done_callback(
                        self._on_receive_task_done
                    )
                self._reconnect_task = None
                self._log.info("재연결 성공")
                return
            except Exception as e:
                self._log.warning("재연결 실패: %s", e)
        self._reconnect_task = None
        self._log.warning("재연결 최대 시도 횟수 초과")

    async def _resubscribe_all(self) -> None:
        """재연결 후 모든 구독 복구."""
        subs: list[tuple[str, str, asyncio.Queue[SubscriptionEvent]]] = []
        for topic in list(self._topic_to_req_ids.keys()):
            req_ids = self._topic_to_req_ids.get(topic)
            if req_ids:
                for req_id in list(req_ids):
                    q = self._subscription_handlers.get(req_id)
                    if q is not None:
                        subs.append((topic, req_id, q))
        for topic, old_req_id, queue in subs:
            self._unregister_subscription_handler(old_req_id)
            self._remove_topic_subscriber(topic, old_req_id)
        for topic, _old_req_id, queue in subs:
            req = build_request(ActionEnum.SUBSCRIBE, topic)
            self._register_subscription_handler(req.req_id, queue)
            self._add_topic_subscriber(topic, req.req_id)
            try:
                await self._send_and_wait_ack(req)
            except Exception as e:
                self._log.warning("구독 복구 실패 topic=%s: %s", topic, e)
                self._unregister_subscription_handler(req.req_id)
                self._remove_topic_subscriber(topic, req.req_id)
                try:
                    queue.put_nowait(CONNECTION_CLOSED_SENTINEL)
                except queue.Full:
                    pass

    async def disconnect(
        self, unsubscribe_first: bool = False
    ) -> None:
        """
        연결 종료 및 정리.

        Args:
            unsubscribe_first: True면 종료 전 활성 구독에 UNSUBSCRIBE 전송
        """
        self._user_disconnect = True
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
            self._reconnect_task = None
        if self._receive_task and self._auto_reconnect:
            self._receive_task.remove_done_callback(self._on_receive_task_done)
        if unsubscribe_first and self._transport.is_connected:
            for topic in list(self._topic_to_req_ids.keys()):
                req_ids = self._topic_to_req_ids.get(topic)
                if req_ids:
                    for req_id in list(req_ids):
                        self._unregister_subscription_handler(req_id)
                        self._remove_topic_subscriber(topic, req_id)
                    try:
                        req = build_request(ActionEnum.UNSUBSCRIBE, topic)
                        await self._transport.send(encode_request(req))
                    except WssConnectionError:
                        pass

        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None
        for future in self._ack_futures.values():
            if not future.done():
                future.cancel()
        self._ack_futures.clear()
        self._subscription_handlers.clear()
        self._topic_to_req_ids.clear()
        await self._transport.disconnect()

    async def __aenter__(self) -> "WssMqttClientAsync":
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.disconnect()

    def subscribe(
        self,
        topic: str,
        timeout: Optional[float] = None,
        queue_maxsize: Optional[int] = None,
    ) -> SubscriptionStream:
        """
        토픽 구독. async context manager와 async iterator로 사용.

        동일 토픽을 여러 스트림으로 구독 가능. 마지막 스트림 종료 시에만
        UNSUBSCRIBE가 전송된다.

        구독 후 stream을 반드시 async for로 소비할 것. 미소비 시 큐가
        쌓여 메모리가 증가할 수 있다.

        Args:
            topic: 구독할 MQTT 토픽
            timeout: SUBSCRIPTION 수신 대기 시간(초). None이면 무제한
            queue_maxsize: 구독 큐 최대 크기. None이면 기본값(10000) 사용.
                0이면 제한 없음. 초과 시 메시지 폐기 및 로그 출력

        Usage:
            async with client.subscribe("tgu/device_001/response") as stream:
                async for event in stream:
                    print(event.payload)
                    break  # RPC 패턴: 1건 수신 후 종료
        """
        if self._validate_topic:
            _validate_topic(topic, max_len=self._topic_max_length)
        return SubscriptionStream(
            self, topic, timeout=timeout, queue_maxsize=queue_maxsize
        )

    async def publish(self, topic: str, payload: Any) -> None:
        """
        토픽에 메시지 발행.

        Args:
            topic: MQTT 토픽
            payload: 발행할 데이터 (JSON 직렬화 가능한 객체)

        Raises:
            ValueError: 토픽 형식 오류 (validate_topic True 시)
            AckError: ACK 4xx/5xx 수신 시
            AckTimeoutError: ACK 타임아웃
            WssConnectionError: 연결되지 않음
        """
        if self._validate_topic:
            _validate_topic(topic, max_len=self._topic_max_length)
        req = build_request(ActionEnum.PUBLISH, topic, payload)
        await self._send_and_wait_ack(req)

    async def publish_many(
        self,
        topic_payloads: Iterable[tuple[str, Any]],
        *,
        stop_on_error: bool = True,
    ) -> list[tuple[str, Any, Optional[Exception]]]:
        """
        다수 토픽에 메시지 발행.

        Args:
            topic_payloads: (topic, payload) 튜플의 iterable
            stop_on_error: True면 첫 실패 시 중단, False면 계속 시도

        Returns:
            (topic, payload, error) 리스트. 성공 시 error는 None
        """
        results: list[tuple[str, Any, Optional[Exception]]] = []
        for topic, payload in topic_payloads:
            try:
                await self.publish(topic, payload)
                results.append((topic, payload, None))
            except Exception as e:
                results.append((topic, payload, e))
                if stop_on_error:
                    break
        return results

    def subscribe_many(
        self,
        topics: Iterable[str],
        timeout: Optional[float] = None,
        queue_maxsize: Optional[int] = None,
    ) -> MultiTopicSubscriptionStream:
        """
        다수 토픽 동시 구독. 단일 스트림으로 수신한다.

        event.topic으로 발신 토픽을 구분할 수 있다.

        Args:
            topics: 구독할 MQTT 토픽 목록
            timeout: SUBSCRIPTION 수신 대기 시간(초). None이면 무제한
            queue_maxsize: 구독 큐 최대 크기. None이면 기본값 사용

        Returns:
            MultiTopicSubscriptionStream (async context manager)
        """
        topic_list = list(topics)
        if self._validate_topic:
            for t in topic_list:
                _validate_topic(t, max_len=self._topic_max_length)
        return MultiTopicSubscriptionStream(
            self, topic_list, timeout=timeout, queue_maxsize=queue_maxsize
        )

    async def unsubscribe(self, topic: str) -> None:
        """
        토픽 구독 해제.

        해당 토픽의 모든 구독 스트림을 해제한다. 이미 구독이 없으면
        무시(idempotent)한다.

        참고: subscribe()의 async with를 벗어나면 자동으로 호출된다.
        """
        if self._validate_topic:
            _validate_topic(topic, max_len=self._topic_max_length)
        req_ids = self._topic_to_req_ids.get(topic)
        if req_ids:
            for req_id in list(req_ids):
                await self._unsubscribe_and_unregister(topic, req_id)

    def _on_message(self, msg: AckEvent | SubscriptionEvent) -> None:
        """수신 메시지 분배."""
        if isinstance(msg, AckEvent):
            future = self._ack_futures.pop(msg.req_id, None)
            if future and not future.done():
                future.set_result(msg)
        elif isinstance(msg, SubscriptionEvent):
            handler_queue = self._subscription_handlers.get(msg.req_id)
            if handler_queue:
                try:
                    handler_queue.put_nowait(msg)
                except queue.Full:
                    self._log.warning(
                        "구독 큐 가득 참, 메시지 폐기: topic=%s req_id=%s",
                        msg.topic,
                        msg.req_id,
                    )
            else:
                self._log.warning(
                    "미등록 req_id의 SUBSCRIPTION 수신, 폐기: req_id=%s topic=%s",
                    msg.req_id,
                    msg.topic,
                )

    def _register_subscription_handler(
        self, req_id: str, queue: asyncio.Queue[SubscriptionEvent]
    ) -> None:
        self._subscription_handlers[req_id] = queue

    def _add_topic_subscriber(self, topic: str, req_id: str) -> None:
        """토픽 구독자 추가 (참조 카운트)."""
        if topic not in self._topic_to_req_ids:
            self._topic_to_req_ids[topic] = set()
        self._topic_to_req_ids[topic].add(req_id)

    def _remove_topic_subscriber(
        self, topic: str, req_id: str
    ) -> bool:
        """
        토픽 구독자 제거.

        Returns:
            해당 토픽에 대한 구독자가 더 이상 없으면 True (UNSUBSCRIBE 필요)
        """
        req_ids = self._topic_to_req_ids.get(topic)
        if not req_ids:
            return False
        req_ids.discard(req_id)
        if not req_ids:
            del self._topic_to_req_ids[topic]
            return True
        return False

    def _unregister_subscription_handler(self, req_id: str) -> None:
        self._subscription_handlers.pop(req_id, None)

    async def _send_and_wait_ack(self, req: Any) -> None:
        """요청 전송 후 ACK 대기."""
        if not self._transport.is_connected:
            raise WssConnectionError("연결되지 않음")
        future: asyncio.Future[AckEvent] = (
            asyncio.get_running_loop().create_future()
        )
        self._ack_futures[req.req_id] = future
        data = (
            encode_request_binary(req)
            if isinstance(getattr(req, "payload", None), bytes)
            else encode_request(req)
        )
        await self._transport.send(data)
        try:
            ack = await asyncio.wait_for(future, timeout=self._ack_timeout)
        except asyncio.TimeoutError as e:
            self._ack_futures.pop(req.req_id, None)
            raise AckTimeoutError(req.req_id, self._ack_timeout) from e
        if ack.code != CODE_OK:
            raise AckError(ack.code, ack.req_id, ack.payload)

    async def _unsubscribe_and_unregister(
        self, topic: str, req_id: str
    ) -> None:
        """구독자 제거 및, 마지막 구독자일 때만 UNSUBSCRIBE 전송."""
        self._unregister_subscription_handler(req_id)
        should_unsubscribe = self._remove_topic_subscriber(topic, req_id)
        if should_unsubscribe:
            req = build_request(ActionEnum.UNSUBSCRIBE, topic)
            await self._send_and_wait_ack(req)
