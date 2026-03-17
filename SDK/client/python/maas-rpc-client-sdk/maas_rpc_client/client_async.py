"""
RpcClientAsync - MaaS RPC 비동기 클라이언트.

스트리밍·다중 구독 등 고급 기능용. 기본 사용은 RpcClient(동기)를 권장한다.
"""

import asyncio
import uuid
from typing import Any, AsyncIterator, Optional, Union

from wss_mqtt_client import (
    SubscriptionTimeoutError,
    WssMqttClientAsync,
)
from wss_mqtt_client.transport import TransportInterface

from .exceptions import RpcError, RpcTimeoutError
from .topics import (
    build_request_topic,
    build_response_topic,
    build_stream_topic,
)


class RpcClientAsync:
    """
    MaaS RPC 비동기 클라이언트.

    MQTT/WSS를 통해 엣지 디바이스(Machine) 서비스에 RPC 호출을 수행한다.
    내부적으로 WssMqttClientAsync를 사용한다.
    고급 기능(스트리밍 등)이 필요할 때 사용. 기본 사용은 RpcClient(동기)를 권장한다.
    """

    def __init__(
        self,
        url: str,
        token: Optional[str] = None,
        *,
        vehicle_id: str,
        client_id: Optional[str] = None,
        transport: Union[str, TransportInterface] = "wss-mqtt-api",
        call_timeout: float = 30.0,
        **kwargs: Any,
    ) -> None:
        """
        Args:
            url: wss-mqtt-api URL 또는 MQTT 브로커 URL
            token: JWT 또는 API 키
            vehicle_id: 차량 식별자
            client_id: 클라이언트 식별자. None이면 자동 생성
            transport: "wss-mqtt-api" 또는 "mqtt"
            call_timeout: RPC call 기본 타임아웃(초)
            **kwargs: WssMqttClientAsync 추가 인자 (ack_timeout, auto_reconnect 등)
        """
        self._vehicle_id = vehicle_id
        self._client_id = client_id if client_id else uuid.uuid4().hex[:16]
        self._call_timeout = call_timeout
        self._call_lock = asyncio.Lock()

        self._wss_client = WssMqttClientAsync(
            url=url,
            token=token,
            transport=transport,
            **kwargs,
        )

    @property
    def raw_client(self) -> WssMqttClientAsync:
        """내부 WssMqttClientAsync 인스턴스. 기본 pub/sub 직접 사용 시."""
        return self._wss_client

    async def __aenter__(self) -> "RpcClientAsync":
        await self._wss_client.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._wss_client.disconnect()

    async def call(
        self,
        service: str,
        payload: dict[str, Any],
        *,
        timeout: Optional[float] = None,
    ) -> Any:
        """
        RPC 호출. Request-Response 패턴.

        Args:
            service: 서비스 식별자 (예: RemoteUDS, VISS)
            payload: 요청 payload. {"action": str, "params": object?} 규격
            timeout: 타임아웃(초). None이면 call_timeout 사용

        Returns:
            서버(Machine) 응답의 result 필드 값

        Raises:
            ValueError: payload에 action이 없는 경우
            RpcError: 서버가 error 필드로 응답한 경우
            RpcTimeoutError: 타임아웃
        """
        if "action" not in payload:
            raise ValueError("payload에 'action' 필드가 필요합니다")

        request_id = uuid.uuid4().hex
        response_topic = build_response_topic(
            service, self._vehicle_id, self._client_id
        )
        request_topic = build_request_topic(service, self._vehicle_id)

        request_payload = {
            "action": payload["action"],
            "params": payload.get("params", {}),
        }
        rpc_payload = {
            "request_id": request_id,
            "response_topic": response_topic,
            "request": request_payload,
        }

        used_timeout = timeout if timeout is not None else self._call_timeout

        async def _do_call() -> Any:
            async with self._call_lock:
                async with self._wss_client.subscribe(
                    response_topic, timeout=used_timeout
                ) as stream:
                    await self._wss_client.publish(request_topic, rpc_payload)

                    async for event in stream:
                        data = event.payload
                        if not isinstance(data, dict):
                            continue
                        if data.get("request_id") != request_id:
                            continue

                        if data.get("error"):
                            raise RpcError(data["error"])
                        return data.get("result")

            raise RuntimeError("unreachable")  # 응답 수신 후 반드시 return/raise

        try:
            return await _do_call()
        except SubscriptionTimeoutError as e:
            raise RpcTimeoutError(
                service, request_id, used_timeout
            ) from e

    async def call_stream(
        self,
        service: str,
        payload: dict[str, Any],
        *,
        timeout: Optional[float] = None,
    ) -> AsyncIterator[Any]:
        """
        1회 요청 → 멀티 응답. async for chunk in client.call_stream(...): 사용.

        Args:
            service: 서비스 식별자
            payload: 요청 payload. {"action": str, "params": object?}
            timeout: 구독 대기 타임아웃(초). None이면 call_timeout 사용

        Yields:
            각 청크의 result 값. done: true 또는 stream_end: true 수신 시 종료.
        """
        if "action" not in payload:
            raise ValueError("payload에 'action' 필드가 필요합니다")

        request_id = uuid.uuid4().hex
        response_topic = build_response_topic(
            service, self._vehicle_id, self._client_id
        )
        request_topic = build_request_topic(service, self._vehicle_id)
        request_payload = {
            "action": payload["action"],
            "params": payload.get("params", {}),
        }
        rpc_payload = {
            "request_id": request_id,
            "response_topic": response_topic,
            "request": request_payload,
        }
        used_timeout = timeout if timeout is not None else self._call_timeout

        async with self._call_lock:
            async with self._wss_client.subscribe(
                response_topic, timeout=used_timeout
            ) as stream:
                await self._wss_client.publish(request_topic, rpc_payload)
                async for event in stream:
                    data = event.payload
                    if not isinstance(data, dict) or data.get("request_id") != request_id:
                        continue
                    if data.get("error"):
                        raise RpcError(data["error"])
                    result = data.get("result")
                    if result is not None:
                        yield result
                    if data.get("done") or data.get("stream_end"):
                        return

    def subscribe_stream(
        self,
        service: str,
        api: str,
        *,
        params: Optional[dict[str, Any]] = None,
        timeout: Optional[float] = None,
        queue_maxsize: Optional[int] = None,
    ):
        """
        구독형 스트림 (VISSv3 스타일). async with client.subscribe_stream(...) as stream: ...

        Args:
            service: 서비스 식별자 (예: RemoteDashboard)
            api: 스트림 API 식별자 (예: vehicleSpeed)
            params: 선택 파라미터 (서버 규격 확정 시 RPC 연동용)
            timeout: 구독 대기 타임아웃
            queue_maxsize: 구독 큐 최대 크기

        Returns:
            SubscriptionStream. async with ... as stream: async for event in stream:
        """
        _ = params  # RPC action: "subscribe" 연동은 추후
        stream_topic = build_stream_topic(
            service, self._vehicle_id, self._client_id, api
        )
        return self._wss_client.subscribe(
            stream_topic, timeout=timeout, queue_maxsize=queue_maxsize
        )

    async def publish(self, topic: str, payload: Any) -> None:
        """토픽에 메시지 발행. raw_client.publish 위임."""
        await self._wss_client.publish(topic, payload)

    def subscribe(
        self,
        topic: str,
        *,
        timeout: Optional[float] = None,
        queue_maxsize: Optional[int] = None,
    ):
        """
        토픽 구독. raw_client.subscribe 위임.

        Returns:
            SubscriptionStream. async with client.subscribe(topic) as stream: async for event in stream:
        """
        return self._wss_client.subscribe(
            topic, timeout=timeout, queue_maxsize=queue_maxsize
        )

    async def unsubscribe(self, topic: str) -> None:
        """토픽 구독 해제. raw_client.unsubscribe 위임."""
        await self._wss_client.unsubscribe(topic)
