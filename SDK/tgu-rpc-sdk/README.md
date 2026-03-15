# TGU RPC SDK

TGU(Telematics Gateway Unit) 서비스/API 명세만으로 RPC를 쉽게 구현할 수 있는 SDK.

wss-mqtt-client 위에 구축되며, 표준화된 토픽 패턴(WMT/WMO)과 RPC 인터페이스를 제공합니다.

**기본**: TguRpcClient (동기). **고급**: TguRpcClientAsync (비동기).

## 상태

**Alpha** — RPC MVP (call), call_stream, subscribe_stream, stop() 구현 완료.

## 설치

```bash
# wss-mqtt-client 의존성 포함
pip install -e SDK/tgu-rpc-sdk

# 로컬 개발 시 wss-mqtt-client 먼저 설치
pip install -e SDK/wss-mqtt-client
pip install -e SDK/tgu-rpc-sdk
```

## 사용법

### RPC 호출 (call) — 기본 (동기)

```python
from tgu_rpc import TguRpcClient

with TguRpcClient(
    url="wss://api.example.com/v1/messaging",
    token="jwt",
    vehicle_id="v001",
    transport="wss-mqtt-api",
) as client:
    result = client.call(
        "RemoteUDS",
        {"action": "readDTC", "params": {"source": 1}},
    )
    print(result)
```

**payload 규격**: `{"action": str, "params": object?}` — params 생략 시 `{}`

### call_stream (1요청→멀티응답) — 동기

```python
with TguRpcClient(...) as client:
    client.call_stream(
        "RemoteUDS",
        {"action": "readDTCStream", "params": {}},
        callback=lambda chunk: print("chunk:", chunk),
        on_complete=lambda: print("완료"),
    )
```

### subscribe_stream (구독형 스트림) — 동기

```python
client = TguRpcClient(...)
client.connect()
client.subscribe_stream("RemoteDashboard", "vehicleSpeed", callback=lambda e: print(e.payload))
client.run_forever()  # stop() 또는 Ctrl+C로 종료
```

### RPC 호출 (call) — 고급 (비동기)

스트리밍·다중 구독 등 고급 기능이 필요하면 `TguRpcClientAsync`를 사용하세요.

```python
import asyncio
from tgu_rpc import TguRpcClientAsync

async def main():
    async with TguRpcClientAsync(
        url="wss://api.example.com/v1/messaging",
        token="jwt",
        vehicle_id="v001",
        transport="wss-mqtt-api",
    ) as client:
        result = await client.call(
            "RemoteUDS",
            {"action": "readDTC", "params": {"source": 1}},
        )
        print(result)

asyncio.run(main())
```

### call_stream / subscribe_stream — 비동기

```python
# call_stream
async for chunk in client.call_stream("RemoteUDS", {"action": "readDTCStream", ...}):
    print(chunk)

# subscribe_stream
async with client.subscribe_stream("RemoteDashboard", "vehicleSpeed") as stream:
    async for event in stream:
        print(event.payload)
```

### 기본 pub/sub (위임 메서드)

RPC와 동일한 연결로 publish/subscribe. wss-mqtt-client를 따로 쓰지 않아도 됨.

```python
# 동기 — publish, subscribe(callback), run_forever(), stop()
with TguRpcClient(...) as client:
    client.publish("custom/topic", {"key": "value"})
    client.subscribe("custom/response", callback=lambda e: print(e.payload))
    client.run_forever()  # stop() 또는 Ctrl+C로 종료

# 비동기 — publish, subscribe, unsubscribe
async with TguRpcClientAsync(...) as client:
    await client.publish("custom/topic", {"key": "value"})
    async with client.subscribe("custom/response") as stream:
        async for event in stream:
            print(event.payload)
```

고급: `client.raw_client`로 subscribe_many, publish_many 등 직접 사용.

## 예제 실행

```bash
# Mock 서버 자동 시작 + RPC 호출
python SDK/tgu-rpc-sdk/examples/run_rpc_example.py

# Mock 서버를 별도 터미널에서 실행한 경우
# 터미널 1: python SDK/examples/run_mock_server.py
# 터미널 2: WSS_MQTT_URL=ws://localhost:8765 python SDK/tgu-rpc-sdk/examples/rpc_call_wss_api.py

# call_stream / subscribe_stream 예제
python SDK/tgu-rpc-sdk/examples/call_stream_example.py
python SDK/tgu-rpc-sdk/examples/call_stream_example.py --async
python SDK/tgu-rpc-sdk/examples/subscribe_stream_example.py
python SDK/tgu-rpc-sdk/examples/subscribe_stream_example.py --async
```

## 토픽 유틸

```python
from tgu_rpc import build_request_topic, build_response_topic, build_stream_topic

request_topic = build_request_topic("RemoteUDS", "v001")
# → "WMT/RemoteUDS/v001/request"

response_topic = build_response_topic("RemoteUDS", "v001", "client_A")
# → "WMO/RemoteUDS/v001/client_A/response"

stream_topic = build_stream_topic("RemoteDashboard", "v001", "client_A", "vehicleSpeed")
# → "WMO/RemoteDashboard/v001/client_A/stream/vehicleSpeed"
```

## 예외

- `RpcError`: TGU가 error 필드로 응답한 경우
- `RpcTimeoutError`: RPC call 타임아웃

## 참조

- `docs/MQTT_RPC_METHODOLOGY.md` — MQTT RPC 방법론
- `docs/RPC_TRANSPORT_LAYER_DESIGN.md` — 전송 계층 설계
- `docs/TGU_RPC_SDK_DEVELOPMENT_PLAN.md` — 개발 계획
