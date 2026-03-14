# TODO 1.2 안정성 개선 상세 계획

> **상태**: ✅ 구현 완료  
> **목표**: wss_mqtt_client의 안정성·견고성 향상 (바이너리 수신, disconnect 처리, 연결 끊김 대응, 로깅)

---

## 1. 작업 항목 개요

| # | 항목 | 우선순위 | 의존성 |
|---|------|----------|--------|
| 1 | 바이너리 수신 처리 | 높음 | msgpack (선택적) |
| 2 | disconnect 시 UNSUBSCRIBE 전송 | 중간 | 없음 |
| 3 | 연결 끊김 시 구독 스트림 처리 | 높음 | 없음 |
| 4 | 알 수 없는 req_id SUBSCRIPTION 로깅 | 낮음 | 없음 |
| 5 | 연결 끊김 감지 정책 | 중간 | 없음 |

---

## 2. 상세 작업 계획

### 2.1 바이너리 수신 처리 (MessagePack 파싱)

**현재 상태**
- `protocol.py`의 `decode_message()`: `bytes` 수신 시 `json.loads(raw.decode("utf-8"))`만 사용
- 서버가 MessagePack(바이너리)으로 보내면 JSON 파싱 실패 → ValueError → 메시지 폐기

**사양 (5.1)**
- 서버: 페이로드가 바이너리이면 전체 Envelope을 MessagePack으로 직렬화하여 바이너리 WebSocket 프레임으로 전송

**구현 방안**

```
수신 raw 타입 분기:
  - str → json.loads() (기존)
  - bytes → 1) msgpack.unpackb() 시도
            2) 실패 시 json.loads(raw.decode("utf-8")) (fallback)
```

**파일**
- `protocol.py`: `decode_message()` 수정

**의존성**
- `msgpack` 패키지: `pyproject.toml`에 optional dependency로 추가 (`msgpack` 없으면 bytes를 JSON으로만 시도)

**코드 스케치**
```python
def decode_message(raw: Union[str, bytes]) -> Union[AckEvent, SubscriptionEvent]:
    if isinstance(raw, str):
        data = json.loads(raw)
    else:
        try:
            import msgpack
            data = msgpack.unpackb(raw, raw=False)  # raw=False → str keys
        except ImportError:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            data = json.loads(raw.decode("utf-8"))  # fallback
    # ... 기존 data 처리 로직
```

---

### 2.2 disconnect 시 UNSUBSCRIBE 전송

**현재 상태**
- `disconnect()`: `_topic_to_req_ids`를 clear만 함. UNSUBSCRIBE 미전송.
- 서버에는 orphan 구독이 남을 수 있음 (실제 게이트웨이는 WebSocket close 시 정리하는 경우 많음)

**목표**
- disconnect 전에 활성 구독에 대해 UNSUBSCRIBE 전송 옵션 제공

**구현 방안**

- `disconnect(unsubscribe_first: bool = False)` 파라미터 추가
- `unsubscribe_first=True`일 때:
  1. `_topic_to_req_ids`에 있는 각 topic에 대해 UNSUBSCRIBE 전송
  2. `_send_and_wait_ack()` 사용 시 ACK 타임아웃 가능 → 비동기 발송만 하거나, 짧은 타임아웃 적용
  3. 전송 실패해도 disconnect는 진행 (best effort)

**고려사항**
- 이미 `_closed` 상태이거나 transport 비연결 시 UNSUBSCRIBE 불가 → 조건 체크

**파일**
- `client.py`: `disconnect()` 시그니처 및 로직

---

### 2.3 연결 끊김 시 구독 스트림 처리

**현재 상태**
- `receive_loop`가 `ConnectionClosed`로 종료되면 그냥 끝남
- 구독 스트림의 `queue.get()`은 계속 대기 (timeout=None이면 영원히)
- 사용자 입장: 연결이 끊겼는데 아무 반응 없음

**목표**
- 연결 끊김 시 `async for event in stream` 대기 중인 모든 구독 스트림에 즉시 예외 전달

**구현 방안**

1. **연결 끊김 감지**: `receive_loop` 종료 시점 파악
   - transport에 `on_connection_lost` 콜백 추가 (선택)
   - 또는: `receive_loop`가 정상 종료/예외 종료 시 client에 알림

2. **클라이언트 측 처리**
   - `receive_task`가 완료되면 (cancel 아닌 ConnectionClosed) `_on_connection_lost()` 호출
   - `_on_connection_lost()`: 모든 `_subscription_handlers`의 queue에 sentinel 투입

3. **Sentinel 설계**
   - `ConnectionClosedSentinel` 또는 `SubscriptionEvent` 서브클래스로 `event="__CONNECTION_CLOSED__"` 같은 표식
   - 또는: `SubscriptionEvent`에 `ConnectionClosedError`를 payload로 넣는 방식은 비권장
   - **권장**: 새 예외 `ConnectionClosedError(WssConnectionError)` 정의, queue에 넣을 수 없으므로 → **별도 `_connection_closed` asyncio.Event** + queue에 `None` 또는 특수 객체 put
   - `SubscriptionStream.__anext__`에서 해당 객체 수신 시 `WssConnectionError` raise

4. **실제 구현**
   - queue에 넣을 수 있는 sentinel: `SubscriptionEvent`가 아닌 `object()` 같은 고유 객체
   - `__anext__`에서 `if event is CONNECTION_CLOSED_SENTINEL: raise WssConnectionError("연결이 끊어졌습니다")`

5. **receive_loop 종료 알림**
   - `WssMqttApiTransport.receive_loop`가 `ConnectionClosed`로 끝날 때, callback만으로는 한계
   - **방안 A**: transport에 `set_on_connection_lost(callback)` 추가. receive_loop의 except 블록에서 호출
   - **방안 B**: client가 `receive_task`에 `add_done_callback` 등으로 완료 감지. 단, task는 cancel로 끝날 수도 있어 구분 필요.
   - **방안 C**: client의 receive_loop를 wrapper로 감싸서, 내부에서 receive_loop 호출 후 정상 종료가 아니면 `_on_connection_lost` 호출

**권장**: TransportInterface에 `on_connection_lost: Optional[Callable[[], None]]` 추가. WssMqttApiTransport.receive_loop의 `except ConnectionClosed`에서 호출. Client는 `set_receive_callback`과 함께 `set_on_connection_lost`로 등록.

**파일**
- `transport/base.py`: TransportInterface에 `set_on_connection_lost` (선택) 또는 기존 `set_receive_callback` 확장
- `transport/wss_mqtt_api.py`: `receive_loop`에서 ConnectionClosed 시 콜백 호출
- `client.py`: `_on_connection_lost` 구현, sentinel put, `connect()` 시 콜백 등록
- `client.py` SubscriptionStream `__anext__`: sentinel 검사
- `constants.py` 또는 `client.py`: `CONNECTION_CLOSED_SENTINEL` 정의

---

### 2.4 알 수 없는 req_id SUBSCRIPTION 로깅

**현재 상태**
- `_on_message`에서 `queue = _subscription_handlers.get(msg.req_id)`가 None이면 아무 처리 없이 메시지 폐기

**구현**
```python
queue = self._subscription_handlers.get(msg.req_id)
if queue:
    try:
        queue.put_nowait(msg)
    except queue.Full:
        ...
else:
    self._log.warning(
        "미등록 req_id의 SUBSCRIPTION 수신, 폐기: req_id=%s topic=%s",
        msg.req_id, msg.topic,
    )
```

**파일**
- `client.py`: `_on_message` 수정

---

### 2.5 연결 끊김 감지 정책

**현재 상태**
- `websockets.connect(ping_interval=30, ping_timeout=10)` 고정

**목표**
- Ping/Pong 파라미터 설정 가능
- 불안정 연결 조기 탐지 (선택)

**구현**
- `WssMqttApiTransport.__init__`에 `ping_interval`, `ping_timeout` 파라미터 추가 (기본값 유지)
- docstring에 연결 유지 정책 설명
- (선택) 연속 ping 실패 횟수 로깅

**파일**
- `transport/wss_mqtt_api.py`

---

## 3. 작업 순서 제안

| 순서 | 항목 | 이유 |
|------|------|------|
| 1 | 2.4 알 수 없는 req_id 로깅 | 단순, 즉시 적용 |
| 2 | 2.5 연결 끊김 감지 정책 | 단순, Transport 수정만 |
| 3 | 2.1 바이너리 수신 처리 | msgpack 의존성 추가, 프로토콜 계층 |
| 4 | 2.3 연결 끊김 시 구독 스트림 처리 | TransportInterface 확장, 복잡도 높음 |
| 5 | 2.2 disconnect 시 UNSUBSCRIBE | 상대적으로 독립적 |

---

## 4. 검증 포인트

| 항목 | 검증 방법 |
|------|-----------|
| 바이너리 수신 | Mock 서버에서 MessagePack SUBSCRIPTION 전송 테스트 |
| disconnect UNSUBSCRIBE | disconnect 전후 Mock 서버 구독 상태 확인 |
| 연결 끊김 스트림 | 연결 강제 종료 후 `async for`가 WssConnectionError로 종료되는지 확인 |
| 알 수 없는 req_id | 미등록 req_id SUBSCRIPTION 주입 시 경고 로그 확인 |
| ping 파라미터 | ping_interval/timeout 변경 시 동작 확인 |

---

## 5. 의존성

| 패키지 | 용도 | 필요성 |
|--------|------|--------|
| msgpack | MessagePack 디코딩 | 바이너리 수신 시 필요. optional로 두고, 없으면 JSON fallback만 |

---

## 6. 구현 완료 요약

| # | 항목 | 구현 |
|---|------|------|
| 1 | 바이너리 수신 | protocol._decode_data() - bytes → msgpack 우선, fallback JSON |
| 2 | disconnect UNSUBSCRIBE | disconnect(unsubscribe_first=False) 파라미터 |
| 3 | 연결 끊김 스트림 | set_on_connection_lost, CONNECTION_CLOSED_SENTINEL, __anext__에서 WssConnectionError |
| 4 | 알 수 없는 req_id | _on_message에서 _log.warning() |
| 5 | ping 파라미터 | ping_interval, ping_timeout (WssMqttApiTransport, WssMqttClient) |
