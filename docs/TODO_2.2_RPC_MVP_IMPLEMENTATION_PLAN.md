# TODO 2.2 RPC MVP 구현 계획

> **상태**: ✅ 구현 완료  
> **목표**: TGU RPC SDK의 `call(service, payload)` 및 토픽 유틸 구현.  
> **참조**: `docs/MQTT_RPC_METHODOLOGY.md`, `docs/RPC_TRANSPORT_LAYER_DESIGN.md`, `docs/TGU_RPC_SDK_DEVELOPMENT_PLAN.md`

---

## 1. 구현 범위

| 항목 | 설명 | 우선순위 |
|------|------|----------|
| topics.py | `build_request_topic`, `build_response_topic` | P0 |
| TguRpcClient | WssMqttClientAsync 래핑, client_id 자동 생성 | P0 |
| call(service, payload) | RPC 호출: 요청 발행 → 응답 수신 → 매칭 | P0 |
| 타임아웃·예외 처리 | RpcTimeoutError, RpcError 등 | P0 |
| exceptions.py | TGU 전용 예외 (선택) | P1 |

---

## 2. 작업 순서

### Step 1: topics.py

**파일**: `SDK/tgu-rpc-sdk/tgu_rpc/topics.py` (신규)

**함수 시그니처**:

```python
def build_request_topic(service: str, vehicle_id: str) -> str:
    """요청 토픽 생성. WMT/{service}/{vehicle_id}/request"""
    ...

def build_response_topic(service: str, vehicle_id: str, client_id: str) -> str:
    """응답 토픽 생성. WMO/{service}/{vehicle_id}/{client_id}/response"""
    ...
```

**검증**:
- `service`, `vehicle_id`, `client_id`: 빈 문자열 불가, `/` 포함 금지 (또는 wss_mqtt_client.validate_topic 활용)
- 단위 테스트: `test_topics.py`

**의존성**: 없음 (순수 함수)

---

### Step 2: exceptions.py (선택, P1)

**파일**: `SDK/tgu-rpc-sdk/tgu_rpc/exceptions.py` (신규)

**예외 클래스**:
- `RpcTimeoutError`: 타임아웃 시
- `RpcError`: TGU 응답에 `error` 필드가 있을 때 (code, message 래핑)

wss_mqtt_client 예외(`SubscriptionTimeoutError`, `AckError` 등)를 그대로 재사용하거나, TGU 전용으로 래핑.

---

### Step 3: TguRpcClient 초기화

**파일**: `SDK/tgu-rpc-sdk/tgu_rpc/client.py` (신규)

**생성자**:

```python
def __init__(
    self,
    url: str,
    token: Optional[str] = None,
    *,
    vehicle_id: str,
    client_id: Optional[str] = None,
    transport: Union[str, TransportInterface] = "wss-mqtt-api",
    call_timeout: float = 30.0,
    **kwargs,  # WssMqttClientAsync 나머지 인자
) -> None:
```

**처리**:
- `client_id`: None이면 `uuid.uuid4().hex[:16]` 등으로 자동 생성
- `self._wss_client = WssMqttClientAsync(url=url, token=token, transport=transport, **kwargs)`
- `self._vehicle_id`, `self._client_id`, `self._call_timeout` 저장

**컨텍스트 매니저**: `async with TguRpcClient(...)` → 내부 `WssMqttClientAsync` connect/disconnect

---

### Step 4: call(service, payload) 구현

**시그니처**:

```python
async def call(
    self,
    service: str,
    payload: dict[str, Any],
    *,
    timeout: Optional[float] = None,
) -> Any:
```

**payload 규격**: `{"action": str, "params": object?}` (params 생략 시 `{}`)

**흐름**:

1. **검증**: payload에 `action` 필수. `params` 없으면 `{}`로 보정
2. **생성**: `request_id = uuid.uuid4().hex`, `response_topic = build_response_topic(service, vehicle_id, client_id)`
3. **RPC 래퍼 payload**: `{"request_id": request_id, "response_topic": response_topic, "request": payload}`
4. **요청 토픽**: `request_topic = build_request_topic(service, vehicle_id)`
5. **구독 선등록**: `async with self._wss_client.subscribe(response_topic, timeout=timeout or self._call_timeout) as stream`
6. **발행**: `await self._wss_client.publish(request_topic, rpc_payload)`
7. **응답 대기**: `async for event in stream` → 첫 이벤트에서 payload 수신
8. **매칭**: payload에서 `request_id` 일치 확인 (다른 요청 응답일 수 있으므로, request_id 불일치 시 계속 대기 또는 타임아웃)
9. **반환**:
   - `error` 필드 있으면 `RpcError` 발생 (또는 result=None, error 전달)
   - `result` 반환

**주의**:
- 구독은 **발행보다 먼저** 수행 (MQTT RPC 시퀀스)
- `subscribe`의 `timeout`은 `__anext__`에서 첫 메시지 대기 시간
- request_id 매칭: 동일 response_topic에 여러 요청 응답이 순서대로 올 수 있음. 첫 메시지가 현재 request_id와 일치하지 않으면 재대기 필요. 단, client_id별 토픽이라 동시 다중 call 시 같은 response_topic을 쓰므로 **request_id 매칭 필수**.

**동시 call 처리**:
- 한 클라이언트가 `call`을 연속 호출하면, response_topic은 동일. 응답이交错될 수 있음.
- **방법 A**: call 중에는 response_topic을 독점(lock). 한 번에 하나의 call만.
- **방법 B**: 구독을 call마다 수행하되, `async for`로 request_id가 일치할 때까지 소비. 불일치 메시지는 버리거나 내부 큐에 넣어 나중에 매칭.

**권장 (MVP)**: **방법 A** — `asyncio.Lock`으로 call 직렬화. 구현 단순. 추후 방법 B로 확장 가능.

---

### Step 5: call() 세부 시퀀스 (코드 레벨)

```
async def call(self, service, payload, timeout=None):
    timeout = timeout or self._call_timeout
    request_id = uuid.uuid4().hex
    response_topic = build_response_topic(service, self._vehicle_id, self._client_id)
    request_topic = build_request_topic(service, self._vehicle_id)
    rpc_payload = {
        "request_id": request_id,
        "response_topic": response_topic,
        "request": {"action": payload["action"], "params": payload.get("params", {})},
    }

    async with self._call_lock:  # 직렬화
        async with self._wss_client.subscribe(response_topic, timeout=timeout) as stream:
            await self._wss_client.publish(request_topic, rpc_payload)
            async for event in stream:
                data = event.payload
                if not isinstance(data, dict):
                    continue
                if data.get("request_id") != request_id:
                    continue  # 다른 요청의 응답, 다음 메시지 대기 (단, timeout 내)
                if "error" in data and data["error"]:
                    raise RpcError(data["error"])
                return data.get("result")
```

**타임아웃**: `SubscriptionStream`의 `timeout`은 `__anext__`에서 `queue.get()` 대기 시간. 한 번에 한 메시지만 받고 종료하므로, 첫 메시지가 올 때까지 timeout 적용됨. request_id 불일치 시 `async for`가 다음 `__anext__`를 호출하고, 그때 다시 timeout. 즉, **메시지 간 대기마다 timeout**이 적용됨.

**개선**: `SubscriptionStream`은 `async for`로 여러 메시지를 받을 수 있음. request_id 불일치 시 다음 메시지를 기다리되, **전체 call에 대한 총 timeout**이 필요할 수 있음. 예: 30초 내에 응답 없으면 RpcTimeoutError.

구현 옵션:
- `asyncio.wait_for(call_coro(), timeout=timeout)` 로 전체 call을 감싸기
- 또는 SubscriptionStream에 전체 대기 timeout이 있으면 활용

---

### Step 6: raw_client / publish, subscribe 노출 (2.3 전 조기 노출 가능)

**2.3에서 상세**하지만, MVP에서 `TguRpcClient`가 `async with`로 진입 시 `WssMqttClientAsync`가 연결됨. 기본 pub/sub을 쓰려면:
- `client.raw_client` 또는 `client.wss_client` → `WssMqttClientAsync` 반환
- `client.publish(topic, payload)` → `self._wss_client.publish` 위임
- `client.subscribe(topic)` → `self._wss_client.subscribe` 위임

**2.2 범위**: raw_client 노출만 해도 됨. publish/subscribe 위임은 2.3에서.

---

## 3. 파일 구조 (구현 후)

```
tgu-rpc-sdk/
├── tgu_rpc/
│   ├── __init__.py      # TguRpcClient, build_request_topic, build_response_topic
│   ├── client.py        # TguRpcClient
│   ├── topics.py        # 토픽 생성 유틸
│   └── exceptions.py    # RpcError, RpcTimeoutError (선택)
├── pyproject.toml       # wss-mqtt-client 의존
└── tests/
    └── test_topics.py   # topics 단위 테스트
```

---

## 4. 단위 테스트

| 대상 | 케이스 |
|------|--------|
| topics | `build_request_topic("RemoteUDS", "v001")` → `WMT/RemoteUDS/v001/request` |
| topics | `build_response_topic("RemoteUDS", "v001", "client_A")` → `WMO/RemoteUDS/v001/client_A/response` |
| call | Mock WssMqttClientAsync, SUBSCRIPTION 이벤트 가정, result 반환 검증 |
| call | error 필드 시 RpcError 발생 |
| call | 타임아웃 시 RpcTimeoutError (또는 SubscriptionTimeoutError) |

---

## 5. 예제 (2.2 완료 후)

```python
from tgu_rpc import TguRpcClient

async with TguRpcClient(
    url="wss://api.example.com/v1/messaging",
    token="jwt",
    vehicle_id="v001",
    transport="wss-mqtt-api",
) as client:
    result = await client.call("RemoteUDS", {"action": "readDTC", "params": {"source": 1}})
    print(result)
```

---

## 6. 체크리스트 (TODO 2.2)

- [x] `topics.py`: `build_request_topic`, `build_response_topic`
- [x] `exceptions.py`: `RpcError`, `RpcTimeoutError`
- [x] `client.py`: `TguRpcClient` 생성자, `__aenter__`/`__aexit__`
- [x] `client.py`: `call(service, payload)` 구현
- [x] `call` lock 적용 (동시 call 직렬화)
- [x] `__init__.py`: export 정리
- [x] `test_topics.py`: topics 단위 테스트
- [x] `test_client.py`: call mock 테스트
- [x] `test_integration.py`: Mock 서버 통합 테스트
