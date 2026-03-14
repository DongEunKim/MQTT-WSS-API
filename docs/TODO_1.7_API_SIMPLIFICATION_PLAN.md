# TODO 1.7 API 사용성 단순화 계획

> **상태**: 완료  
> **목표**: async/await 중첩을 줄이고, sync·콜백 친화적 API로 사용성을 개선  
> **배경**: `async with` + `async with` + `async for` 조합이 복잡해 보임

---

## 1. 범위 및 이관

### 1.1 1.7 범위 (wss_mqtt_client)

- **WssMqttClient** (기본): sync 래퍼 (connect/disconnect/publish)
- **콜백 기반 subscribe** + **run_forever()**: paho-mqtt 스타일 listen-only
- **예제·문서 단순화**: quick start sync 예제

### 1.2 이관 (TGU RPC SDK, 2.2)

- **call() RPC**: 발행 → 응답 1건 수신 한 줄 API
- **receive_one()**: 구독 후 1건 블로킹 수신

RPC 패턴(요청-응답 매핑, 토픽 규칙)은 애플리케이션 계층 관심사이므로 TGU RPC SDK에서 구현한다.

---

## 2. 현황과 문제

### 2.1 현재 사용 패턴

```python
async def main():
    async with WssMqttClientAsync(url=URL) as client:
        async with client.subscribe(TOPIC) as stream:
            async for event in stream:
                print(event.payload)
                break
asyncio.run(main())
```

- context manager 2단 중첩
- `asyncio.run(main())` 필요
- async를 모르는 사용자에게 진입 장벽

### 2.2 목표 사용 패턴 (1.7 범위)

- async 문법 최소화
- paho-mqtt처럼 직관적인 sync/콜백 스타일
- 복사-붙여넣기로 바로 동작하는 최소 예제

---

## 3. 작업 항목

| # | 항목 | 우선순위 | 설명 |
|---|------|----------|------|
| 1 | WssMqttClient (기본) | 높음 | sync 래퍼 클래스 (asyncio.run 내부 활용) |
| 2 | 콜백 기반 subscribe | 높음 | `subscribe(topic, callback=fn)` + `run_forever()` |
| 3 | 예제·문서 단순화 | 중간 | quick start sync 예제 업데이트 |

---

## 4. 상세 API 설계

### 4.1 WssMqttClient (기본, 동기)

sync 래퍼. 내부에서 WssMqttClientAsync + asyncio.run 사용.

```python
client = WssMqttClient(url=URL)
client.connect()
client.publish("topic", {"x": 1})
# ... 사용 ...
client.disconnect()
```

또는 context manager:

```python
with WssMqttClient(url=URL) as client:
    client.publish("topic", {"x": 1})
```

### 4.2 콜백 기반 subscribe (paho-mqtt 스타일)

listen-only 용도. 구독 후 수신 메시지를 콜백으로 처리.

```python
def on_message(event):
    print(event.payload)

client = WssMqttClient(url=URL)
client.connect()
client.subscribe("topic", callback=on_message)
client.run_forever()  # 블로킹
```

- `async for` 제거
- paho-mqtt 사용자에게 익숙한 패턴

**구현**
- `subscribe(topic, callback=Callable[[SubscriptionEvent], None])`
- `run_forever()` 또는 `run(timeout=초)`: 내부 이벤트 루프 블로킹

---

## 5. 기존 async API 유지

- `WssMqttClientAsync` (고급): 비동기 API 유지
- 고급 사용자, 스트리밍, 다중 구독 등은 `WssMqttClientAsync` 사용
- `WssMqttClient` (기본)는 단순 사용 사례 전용 (발행, listen-only 구독)

---

## 6. 예제 변경 (before/after)

### 6.1 구독 예제 (listen-only)

**Before (async)**

```python
async def main():
    async with WssMqttClientAsync(url=URL) as client:
        async with client.subscribe(TOPIC, timeout=None) as stream:
            async for event in stream:
                print(event.payload)
asyncio.run(main())
```

**After (sync, 콜백, 기본)**

```python
def on_message(event):
    print(event.payload)

with WssMqttClient(url=URL) as client:
    client.subscribe(TOPIC, callback=on_message)
    client.run_forever()
```

### 6.2 발행 예제

**After (sync, 기본)**

```python
with WssMqttClient(url=URL) as client:
    client.publish("topic/command", {"action": "ping"})
```

---

## 7. 구현 순서

| 순서 | 항목 | 이유 |
|------|------|------|
| 1 | WssMqttClient (connect/disconnect/publish) | 기반 클래스 |
| 2 | subscribe(callback) + run_forever() | listen-only 구독 패턴 |
| 3 | 예제·문서 업데이트 | 사용자 노출 |

---

## 8. 파일

| 파일 | 내용 |
|------|------|
| `client_sync.py` | WssMqttClient 클래스 (동기 래퍼) |
| `__init__.py` | WssMqttClient(기본), WssMqttClientAsync 노출 |
| `examples/subscriber.py` | 기본 동기 구독 예제 |
| `examples/publisher.py` | 기본 동기 발행 예제 |
| `examples/subscriber_async.py` | 고급 비동기 구독 예제 |
| `examples/publisher_async.py` | 고급 비동기 발행 예제 |

---

## 9. RPC 패턴 (TGU RPC SDK 2.2)

RPC 한 줄 호출(`call()`) 및 `receive_one()`은 TGU RPC SDK에서 구현한다.

- 토픽 패턴: `tgu/{vehicle_id}/{service}/request`, `.../response` 등
- TguRpcClient.call(): 발행 → 응답 1건 수신
- 상세: `TODO.md` 2.2 RPC MVP

---

## 10. 완료 사항 (구현 기록)

- **client_sync.py**: WssMqttClient — 백그라운드 스레드 + 이벤트 루프
- **connect/disconnect/publish**: 블로킹, `_run_coro`로 async 호출
- **subscribe(topic, callback)**: connect 전/후 호출 가능, drain task로 콜백 호출
- **run_forever() / run(timeout)**: 블로킹 대기
- **예제**: subscriber.py, publisher.py (기본), subscriber_async.py, publisher_async.py (고급)
- **테스트**: test_client_sync.py (11개) — publish, subscribe, 콜백 예외, 다중 구독 등
