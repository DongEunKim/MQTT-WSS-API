# MaaS RPC Client SDK

**Machine as a Service** — 엣지 디바이스(Machine)를 서비스 제공자로 삼아
RPC를 쉽게 호출할 수 있는 클라이언트 SDK.

wss-mqtt-client 위에 구축되며, 표준화된 토픽 패턴(WMT/WMO)과 RPC 인터페이스를 제공합니다.

**기본**: RpcClient (동기). **고급**: RpcClientAsync (비동기).

## 상태

**Alpha** — RPC MVP (call), call_stream, subscribe_stream, stop() 구현 완료.

## 설치

이 패키지 디렉터리(`maas-rpc-client-sdk/`) 안에서 실행합니다.  
`wss-mqtt-client`가 의존 패키지이므로 **순서대로** 설치해야 합니다.

```bash
# 1. 의존 패키지 먼저
pip install -e ../wss-mqtt-client

# 2. 이 SDK
pip install -e .
```

msgpack 직렬화가 필요한 경우 (선택):

```bash
pip install -e "../wss-mqtt-client[msgpack]"
pip install -e .
```

> 두 패키지를 한 번에 설치하려면 상위 `python/` 폴더의 `install.sh`를 사용하세요.

## 사용법

### RPC 호출 (call) — 기본 (동기)

```python
from maas_rpc_client import RpcClient

with RpcClient(
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
with RpcClient(...) as client:
    client.call_stream(
        "RemoteUDS",
        {"action": "readDTCStream", "params": {}},
        callback=lambda chunk: print("chunk:", chunk),
        on_complete=lambda: print("완료"),
    )
```

### subscribe_stream (구독형 스트림) — 동기

```python
client = RpcClient(...)
client.connect()
client.subscribe_stream("RemoteDashboard", "vehicleSpeed", callback=lambda e: print(e.payload))
client.run_forever()  # stop() 또는 Ctrl+C로 종료
```

### RPC 호출 (call) — 고급 (비동기)

스트리밍·다중 구독 등 고급 기능이 필요하면 `RpcClientAsync`를 사용하세요.

```python
import asyncio
from maas_rpc_client import RpcClientAsync

async def main():
    async with RpcClientAsync(
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
with RpcClient(...) as client:
    client.publish("custom/topic", {"key": "value"})
    client.subscribe("custom/response", callback=lambda e: print(e.payload))
    client.run_forever()  # stop() 또는 Ctrl+C로 종료

# 비동기 — publish, subscribe, unsubscribe
async with RpcClientAsync(...) as client:
    await client.publish("custom/topic", {"key": "value"})
    async with client.subscribe("custom/response") as stream:
        async for event in stream:
            print(event.payload)
```

고급: `client.raw_client`로 subscribe_many, publish_many 등 직접 사용.

## 예제 실행

예제 목록·실행 방법: [SDK/examples/README.md](../examples/README.md)

```bash
# 한 번에 실행 (Mock 서버 자동 시작 + RPC 호출)
python SDK/client/python/maas-rpc-client-sdk/examples/run_rpc_example.py
```

## 토픽 유틸

```python
from maas_rpc_client import build_request_topic, build_response_topic, build_stream_topic

request_topic = build_request_topic("RemoteUDS", "v001")
# → "WMT/RemoteUDS/v001/request"

response_topic = build_response_topic("RemoteUDS", "v001", "client_A")
# → "WMO/RemoteUDS/v001/client_A/response"

stream_topic = build_stream_topic("RemoteDashboard", "v001", "client_A", "vehicleSpeed")
# → "WMO/RemoteDashboard/v001/client_A/stream/vehicleSpeed"
```

## 예외

- `RpcError`: 서버(Machine)가 error 필드로 응답한 경우
- `RpcTimeoutError`: RPC call 타임아웃

## 참조

- `docs/RPC_DESIGN.md` — RPC 방법론 및 전송 계층 설계
- `docs/RPC_CLIENT_SDK_DEVELOPMENT_PLAN.md` — RPC Client SDK 개발 계획
