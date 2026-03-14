"""
TguRpcClientAsync - TGU RPC 비동기 클라이언트.

스트리밍·다중 구독 등 고급 기능용. 기본 사용은 TguRpcClient(동기)를 권장한다.
"""

import asyncio
import uuid
from typing import Any, Optional, Union

from wss_mqtt_client import (
    SubscriptionTimeoutError,
    WssMqttClientAsync,
)
from wss_mqtt_client.transport import TransportInterface

from .exceptions import RpcError, RpcTimeoutError
from .topics import build_request_topic, build_response_topic


class TguRpcClientAsync:
    """
    TGU RPC 비동기 클라이언트.

    MQTT/WSS를 통해 TGU 서비스에 RPC 호출을 수행한다.
    내부적으로 WssMqttClientAsync를 사용한다.
    고급 기능(스트리밍 등)이 필요할 때 사용. 기본 사용은 TguRpcClient(동기)를 권장한다.
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

    async def __aenter__(self) -> "TguRpcClientAsync":
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
            TGU 응답의 result 필드 값

        Raises:
            ValueError: payload에 action이 없는 경우
            RpcError: TGU가 error 필드로 응답한 경우
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
