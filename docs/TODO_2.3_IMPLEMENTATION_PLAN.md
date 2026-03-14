# TODO 2.3 구현 계획: 스트리밍 API 및 pub/sub

> **목표**  
> `call_stream` (1요청→멀티응답), `subscribe_stream` (pub/sub 구독), 기본 pub/sub 노출.

---

## 0. 클라이언트 구조 (동기/비동기)

| 클라이언트 | 용도 | 인터페이스 |
|------------|------|------------|
| **TguRpcClient** (동기, 기본) | 기본 사용자 | `call()`, `call_stream(callback=...)`, `subscribe_stream(callback=...)` — 콜백 기반 |
| **TguRpcClientAsync** (비동기, 고급) | 고급 사용자 | `call()`, `call_stream()` → async iterator, `subscribe_stream()` → async iterator |

- **동기식 (기본)**: 콜백 패턴. WssMqttClient의 `subscribe(topic, callback)`와 동일한 사고방식.
- **비동기식 (고급)**: async iterator 패턴. `async for chunk in stream:` 사용.
- `call_stream`, `subscribe_stream`을 **양쪽 클라이언트 모두** 구현. 인터페이스만 다름.

---

## 1. 패턴 구분

| 패턴 | 메서드 | 트리거 | 응답 | 상관관계 |
|------|--------|--------|------|----------|
| **1요청→1응답** | call() | RPC 1회 | 1회 | request_id |
| **1요청→멀티응답** | call_stream() | RPC 1회 | N회 (청크/스트림) | request_id |
| **pub/sub 구독** | subscribe_stream() | 구독 시작 | 주기/이벤트 푸시 | api |

---

## 2. 범위 요약

| 항목 | 설명 | 우선순위 |
|------|------|----------|
| **stop()** | run_forever() 블로킹 해제. WssMqttClient, TguRpcClient | P0 |
| **call_stream(service, payload)** | 1회 요청 → 멀티 응답 (동일 request_id) | P0 |
| **subscribe_stream(service, api)** | pub/sub 구독형 (VISSv3 스타일) | P1 |
| **기본 pub/sub 노출** | publish, subscribe 위임, raw_client | P2 |
| **예제** | call_stream, subscribe_stream | P3 |

---

## 3. 1요청→멀티응답 (call_stream)

### 3.1 용도

- **call()**: 1회 요청 → 1회 응답
- **call_stream()**: 1회 요청 → **여러 청크** 응답 (동일 request_id로 상관관계 유지)

예: readDTC 스트리밍, 대용량 응답 청크 분할.

### 3.2 시퀀스

```
클라이언트                          TGU
    │                               │
    │ 1. SUBSCRIBE response_topic   │
    │ 2. PUBLISH WMT/.../request    │
    │   {request_id, response_topic, request}
    │──────────────────────────────>│
    │                               │
    │ SUBSCRIPTION {request_id, result: chunk1, done: false}
    │<──────────────────────────────│
    │ SUBSCRIPTION {request_id, result: chunk2, done: false}
    │<──────────────────────────────│
    │ SUBSCRIPTION {request_id, result: chunk3, done: true}
    │<──────────────────────────────│
```

- **토픽**: 기존 `WMO/.../response` 재사용
- **payload**: `done: true` 또는 `stream_end: true` 시 스트림 종료

### 3.3 API 스펙

**TguRpcClient (동기, 콜백)**
```python
def call_stream(
    self,
    service: str,
    payload: dict,
    callback: Callable[[Any], None],
    *,
    on_complete: Optional[Callable[[], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
    timeout: Optional[float] = None,
) -> None:
    """1회 요청 → 멀티 응답. 각 청크마다 callback(chunk) 호출. done 시 on_complete. 블로킹."""
```

**TguRpcClientAsync (비동기, iterator)**
```python
async def call_stream(
    self,
    service: str,
    payload: dict,
    *,
    timeout: Optional[float] = None,
):
    """1회 요청 → 멀티 응답. async for chunk in stream: ..."""
    # async generator 또는 async context manager 반환
```

---

## 4. pub/sub 구독형 (subscribe_stream)

### 4.1 용도

- 구독 시작 → TGU가 주기/이벤트 기준으로 **여러 번** 데이터 발행 (Push 스트림)
- request_id 상관 없음. api 기준 토픽 구독.

예: 차속, RPM, 온도 등 실시간 시그널.

### 4.2 토픽 패턴 (제안)

`WMO/.../response`는 RPC 응답용. 스트림은 별도 패턴 사용.

| 구분 | 패턴 | 설명 |
|------|------|------|
| **스트림 수신 토픽** | `WMO/{service}/{vehicle_id}/{client_id}/stream/{api}` | 클라이언트 구독, TGU 발행 |
| **스트림 활성화 요청** | `WMT/{service}/{vehicle_id}/request` | `action: "subscribe"`, `api` 지정 |

즉, **RPC 요청으로 스트림을 활성화**하고, **별도 토픽**으로 이벤트를 수신한다.

### 4.3 시퀀스

```
클라이언트                              TGU
    │                                    │
    │ 1. SUBSCRIBE WMO/.../stream/{api}  │
    │────────────────────────────────────>
    │                                    │
    │ 2. PUBLISH WMT/.../request         │
    │    {action:"subscribe", api:"vehicleSpeed"}
    │───────────────────────────────────>│
    │                                    │ 3. 스트림 시작
    │ 4. SUBSCRIPTION (이벤트 1)         │
    │<───────────────────────────────────│
    │ 5. SUBSCRIPTION (이벤트 2)         │
    │<───────────────────────────────────│
    │ ...                                │
```

- **옵션 A (제안)**: subscribe_stream 진입 시 ① 구독 선등록 ② RPC로 `action: "subscribe"` 발행
- **옵션 B**: 토픽만 구독. TGU가 구독자 존재 시 자동 발행 (브로커 기반, TGU 규격 의존)

**권장**: 옵션 A. TGU가 “누가 스트림을 원하는지” 명시적으로 알 수 있음.

### 4.4 요청 payload (스트림 활성화)

```json
{
  "request_id": "uuid",
  "response_topic": "WMO/RemoteDashboard/v001/client_A/response",
  "request": {
    "action": "subscribe",
    "api": "vehicleSpeed",
    "params": { "interval_ms": 100 }
  }
}
```

- **action**: `"subscribe"` (구독 시작)
- **api**: 스트림 식별자 (예: `vehicleSpeed`, `rpm`, `dtc`)
- **params**: 선택 (주기, 필터 등)

### 4.5 응답 payload (스트림 활성화 ACK)

```json
{
  "request_id": "uuid",
  "result": { "status": "subscribed", "stream_topic": "WMO/.../stream/vehicleSpeed" },
  "error": null
}
```

스트림 이벤트는 `stream_topic` (또는 약속된 `WMO/.../stream/{api}`)로 발행.

### 4.6 스트림 이벤트 payload

서비스별 상이. 예:

```json
{
  "ts": 1699900000000,
  "value": 85.5,
  "unit": "km/h"
}
```

### 4.7 subscribe_stream API 스펙

**TguRpcClient (동기, 콜백)**
```python
def subscribe_stream(
    self,
    service: str,
    api: str,
    callback: Callable[[SubscriptionEvent], None],
    *,
    params: Optional[dict[str, Any]] = None,
    queue_maxsize: Optional[int] = None,
) -> None:
    """
    구독형 스트림. connect() 전/후 호출. run_forever()로 수신.
    WssMqttClient.subscribe(topic, callback)와 동일 패턴.

    Usage:
        client.subscribe_stream("RemoteDashboard", "vehicleSpeed", callback=lambda e: print(e))
        client.run_forever()
    """
```

**TguRpcClientAsync (비동기, iterator)**
```python
async def subscribe_stream(
    self,
    service: str,
    api: str,
    *,
    params: Optional[dict[str, Any]] = None,
    timeout: Optional[float] = None,
    queue_maxsize: Optional[int] = None,
) -> "SubscriptionStreamContext":
    """
    구독형 스트림. async for event in stream: ...

    Usage:
        async with client.subscribe_stream("RemoteDashboard", "vehicleSpeed") as stream:
            async for event in stream:
                print(event.payload)
    """
```

### 4.8 구현 단계

1. **topics.py 확장**
   - `build_stream_topic(service, vehicle_id, client_id, api)` 추가
   - `WMO/{service}/{vehicle_id}/{client_id}/stream/{api}`

2. **TguRpcClient.subscribe_stream(callback)** (동기)
   - 스트림 토픽 구독 (내부 WssMqttClient.subscribe 패턴)
   - RPC 발행: `{ action: "subscribe", api, params }` (선택)
   - 콜백으로 이벤트 전달. `run_forever()` 필요.

3. **TguRpcClientAsync.subscribe_stream()** (비동기)
   - raw_client.subscribe 스트림 토픽
   - RPC 발행: `{ action: "subscribe", api, params }`
   - `SubscriptionStream` (async context manager) 반환

4. **스트림 종료**
   - 동기: disconnect() 또는 프로세스 종료
   - 비동기: context exit 시 `action: "unsubscribe"` RPC 발행 (선택), 구독 해제

---

## 5. 기본 pub/sub 노출

### 5.1 현황

- `raw_client`: connect() 후 WssMqttClientAsync 반환
- 기본 pub/sub: 동기/비동기 각각 위임 메서드 추가

### 5.2 추가할 위임 메서드

**TguRpcClient (동기)** — WssMqttClient와 동일 패턴. `stop()`은 WssMqttClient(wss-mqtt-client)에 선행 구현 필요.
```python
def publish(self, topic: str, payload: Any) -> None:
    """토픽에 메시지 발행 (블로킹)."""
def subscribe(self, topic: str, callback: Callable, queue_maxsize: Optional[int] = None) -> None:
    """토픽 구독. connect() 전/후 호출. run_forever()로 수신."""
def run_forever(self, timeout: Optional[float] = None) -> None:
    """수신 루프 (블로킹). subscribe_stream, subscribe 사용 시 필요. stop()으로 종료 가능."""
def stop(self) -> None:
    """run_forever() 블로킹 해제. 다른 스레드/시그널 핸들러에서 호출."""
```

**TguRpcClientAsync (비동기)**
```python
async def publish(self, topic: str, payload: Any) -> None:
    """토픽에 메시지 발행. raw_client.publish 위임."""
def subscribe(self, topic: str, *, timeout, queue_maxsize) -> SubscriptionStream:
    """토픽 구독. raw_client.subscribe 위임."""
async def unsubscribe(self, topic: str) -> None:
    """토픽 구독 해제."""
```

- RPC와 동일한 transport 사용
- `raw_client` 직접 사용과 동일하지만, 각 클라이언트 단일 진입점 제공

### 5.3 raw_client 유지

- 고급 사용: `client.raw_client`로 `subscribe_many`, `publish_many` 등 직접 사용

---

## 6. 예제

### 6.1 동기식 (기본 사용자) — 콜백

```python
# call_stream
with TguRpcClient(...) as client:
    client.call_stream(
        "RemoteUDS",
        {"action": "readDTCStream", "params": {}},
        callback=lambda chunk: print("chunk:", chunk),
        on_complete=lambda: print("완료"),
    )

# subscribe_stream
client = TguRpcClient(...)
client.connect()
client.subscribe_stream("RemoteDashboard", "vehicleSpeed", callback=lambda e: print(e.payload))
client.run_forever()  # stop() 또는 Ctrl+C로 종료
```

### 6.2 비동기식 (고급 사용자) — async iterator

```python
# call_stream
async with TguRpcClientAsync(...) as client:
    async for chunk in client.call_stream("RemoteUDS", {"action": "readDTCStream", ...}):
        print(chunk)

# subscribe_stream
async with TguRpcClientAsync(...) as client:
    async with client.subscribe_stream("RemoteDashboard", "vehicleSpeed") as stream:
        async for event in stream:
            print(event.payload)
```

### 6.3 산출물 및 참고

- `SDK/tgu-rpc-sdk/examples/call_stream_example.py` — 동기 + 비동기 예제
- `SDK/tgu-rpc-sdk/examples/subscribe_stream_example.py` — 동기 + 비동기 예제
- `rpc_call_mqtt.py` 이미 존재. README/실행 순서만 정리.

- Mock 서버/TGU가 `subscribe` + `stream/{api}` 토픽 발행을 지원해야 동작
- 최소 구현: `subscribe_stream` = 스트림 토픽만 구독 (RPC 생략)

---

## 7. TGU/Mock 지원 사항

**call_stream**: response_topic에 `done: true` 또는 `stream_end: true` 포함된 메시지로 스트림 종료 신호.

**subscribe_stream**: TGU(또는 Mock)가 다음을 지원해야 함.

| 항목 | 설명 |
|------|------|
| **action: "subscribe"** | `api` 수신 시 해당 스트림 시작 |
| **스트림 토픽 발행** | `WMO/.../stream/{api}`에 주기/이벤트 발행 |
| **action: "unsubscribe"** | (선택) 스트림 중지 |

초기에는 **토픽 구독만** 구현하고, RPC(`subscribe`/`unsubscribe`)는 TGU 규격 확정 후 연동하는 방식도 가능.

---

## 8. 작업 순서

| 단계 | 작업 | 산출물 |
|------|------|--------|
| 0 | **stop()** — WssMqttClient, TguRpcClient에 추가. run_forever() 블로킹 해제용 | `client_sync.py`, `client.py` |
| 1 | topics.py에 `build_stream_topic` 추가 | `topics.py` |
| 2a | **TguRpcClient** (동기): `call_stream(callback)`, `subscribe_stream(callback)`, `publish`, `subscribe`, `run_forever`, `stop` | `client.py` |
| 2b | **TguRpcClientAsync** (비동기): `call_stream()` iterator, `subscribe_stream()` iterator, `publish`, `subscribe`, `unsubscribe` | `client_async.py` |
| 3 | call_stream 구현 — 동기(콜백 블로킹), 비동기(async for) | `client.py`, `client_async.py` |
| 4 | subscribe_stream 구현 — 동기(콜백+run_forever), 비동기(async with stream) | `client.py`, `client_async.py` |
| 5 | subscribe_stream RPC 연동 (action: subscribe/unsubscribe) | 양쪽 |
| 6 | 예제, Mock/TGU 시뮬레이션 | `examples/` |

---

## 9. 의존성 및 리스크

| 항목 | 내용 |
|------|------|
| **토픽 패턴** | `stream/{api}` 패턴은 제안. TGU 규격과 맞출 필요 있음 |
| **TGU 구현 상태** | subscribe_stream 완전 지원 시 TGU 측 구현 필요 |
| **하위 호환** | `raw_client` 기존 사용처에 영향 없음 |
| **동기/비동기 이중 구현** | 동기(콜백)는 WssMqttClient.subscribe 패턴 재사용. 비동기는 async iterator. |

---

## 10. 향후 작업 (TODO 2.3 완료 후)

### Heartbeat (종단 간·서비스별)

- **목적**: subscribe_stream 등 장기 구독 시, TGU가 클라이언트 끊김을 감지하여 불필요한 발행 중단
- **설계**: 스트림 수준 양방향 heartbeat (토픽, 주기, 타임아웃)
- **진행 시점**: TODO 2.3 완료 후

---

## 11. 참조

- `docs/TGU_RPC_SDK_DEVELOPMENT_PLAN.md` — Phase 5, 5.3 구독형 API
- `docs/TOPIC_AND_ACL_SPEC.md` — WMT/WMO 토픽 규격
- `docs/MQTT_RPC_METHODOLOGY.md` — RPC 패턴
- `SDK/tgu-rpc-sdk/tgu_rpc/client.py` — TguRpcClient (동기)
- `SDK/tgu-rpc-sdk/tgu_rpc/client_async.py` — TguRpcClientAsync (비동기, TODO 2.3 대상)
- `SDK/tgu-rpc-sdk/tgu_rpc/topics.py` — 토픽 유틸
- `TODO.md` — 2.4 Heartbeat (TODO 2.3 완료 후)
