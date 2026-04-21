# RPC 설계 — MQTT 5.0 네이티브 구현

> MQTT 5.0의 네이티브 기능을 활용하여 Request-Response, Streaming, Exclusive Session RPC 패턴을 구현하는 설계 문서.

---

## 1. 개요

본 시스템의 RPC는 MQTT 5.0 브로커(AWS IoT Core)를 통해 클라이언트와 서비스 간 통신을 구현한다.  
별도의 Envelope 프로토콜 없이 MQTT 5.0의 표준 Properties를 활용하여 요청-응답 상관관계를 처리한다.

### 1.1 기본 원칙

- **Envelope 없음:** MQTT 5.0의 `Response Topic`, `Correlation Data`, `Reason Code`, `User Properties`로 모든 RPC 메타데이터를 처리
- **action 필수:** 페이로드에 `action` 필드를 포함하여 핸들러 라우팅. 클라이언트 SDK가 `call(..., action=...)` 시 자동 삽입
- **서비스 구분:** 토픽의 `{Service}` 세그먼트로 어떤 서비스인지 구분한다. 여러 액션은 동일 `{Service}` 안에서 서로 다른 `action` 값으로 구분한다.
- **페이로드 자유:** `action` 외 필드는 서버-클라이언트 계약으로 자유 정의
- **동기 우선:** SDK 기본 인터페이스는 동기 블로킹. 내부적으로 asyncio 사용

### 1.2 토픽 구조 요약

```
요청:   WMT/{ThingType}/{Service}/{VIN}/{ClientId}/request
응답:   WMO/{ThingType}/{Service}/{VIN}/{ClientId}/response
이벤트: WMO/{ThingType}/{Service}/{VIN}/{ClientId}/event
```

자세한 내용은 [TOPIC_AND_ACL_SPEC.md](TOPIC_AND_ACL_SPEC.md) 참고.

---

## 2. RPC 패턴

### 패턴 A: 상태/정보 조회 (Liveness)

빠른 응답이 필요한 읽기 전용 조회.

| 항목 | 값 |
|------|----|
| QoS | 0 |
| Message Expiry | 3초 권장 |
| 클라이언트 Timeout | 3초 |
| 서비스 응답 | reason_code=0, 즉시 반환 |

```python
result = client.call(
    "CGU", "viss", "get_status", "VIN-001",
    qos=0, timeout=3.0,
)
```

---

### 패턴 B: 신뢰성 제어 (Reliable Control)

하드웨어 제어 등 결과 보장이 필요한 명령.

| 항목 | 값 |
|------|----|
| QoS | 1 |
| 클라이언트 Timeout | 10~15초 |
| 서비스 응답 | reason_code=0 (성공) 또는 0x80/0x83 (실패) |

```python
result = client.call("CGU", "control", "worklight_on", "VIN-001", qos=1, timeout=15.0)
```

---

### 패턴 C: 스트리밍 (Chunked Streaming)

대용량 데이터를 청크로 분할 전송.

**흐름:**
1. 클라이언트 → `WMT/.../request` PUBLISH
2. 서비스 → `WMO/.../event` PUBLISH × N (청크)
3. 서비스 → `WMO/.../response` PUBLISH (완료 신호, `is_EOF=true`)

**Correlation Data**로 청크와 요청을 매핑.

```python
for chunk in client.stream("CGU", "diagnostics", "can_log", "VIN-001"):
    process(chunk.payload)
```

서비스 측:
```python
@server.action("can_log", streaming=True)
def handle_log(ctx: RpcContext):
    for chunk in read_log_chunks():
        yield chunk
```

---

### 패턴 D: 시한성 안전 제어 (Time-bound)

즉시 실행되지 않으면 위험한 명령.  
`Message Expiry Interval`로 브로커 레벨에서 지연 메시지 자동 폐기.

```python
client.call(
    "CGU", "safety", "stop_engine", "VIN-001",
    payload={"force": True},
    qos=1, timeout=5.0,
    expiry=2,  # 2초 후 브로커에서 자동 폐기
)
```

---

### 패턴 E: 독점 세션 (Exclusive Session)

단 하나의 클라이언트만 명령 가능한 세션 Lock 패턴.

**Lock 메커니즘:**
- `acquire_lock=True` 핸들러 호출 시 VIN + ClientId로 Lock 획득
- 다른 ClientId 요청 시 → `reason_code=0x8A (Server Busy)` 반환
- `release_lock=True` 핸들러 호출 시 Lock 해제
- 클라이언트 단절 시 Presence Monitor가 Lock 강제 해제 (데드락 방지)

```python
with client.exclusive_session("CGU", "uds", "VIN-001") as session:
    session.call("ecu_reset", payload={})
```

서비스 측:
```python
@server.action("session_start", acquire_lock=True)
def start_session(ctx: RpcContext):
    return {"session_id": "active"}

@server.action("ecu_reset", exclusive=True)
def reset_ecu(ctx: RpcContext):
    hw.reset()
    return {"ok": True}

@server.action("session_stop", release_lock=True)
def stop_session(ctx: RpcContext):
    return {"session_id": "released"}
```

---

## 3. 내부 구현 메커니즘

### 3.1 요청-응답 상관관계 (Pending Map)

```
1. call() 호출 시 UUID v4 → correlation_id (bytes) 생성
2. pending_map[correlation_id] = asyncio.Future 등록
3. PUBLISH (request_topic, payload, Properties{
       Response-Topic, Correlation-Data=correlation_id
   })
4. 응답 수신 시 Correlation-Data 추출 → pending_map에서 Future 찾아 resolve
5. Timeout 시 Future cancel + pending_map에서 삭제
```

### 3.2 스트리밍 (Stream Map)

```
1. stream() 호출 시 correlation_id 생성
2. stream_map[correlation_id] = asyncio.Queue 등록
3. PUBLISH (request_topic)
4. event 수신 시 → Queue에 StreamEvent put
5. response 수신 (is_EOF=true) 시 → Queue에 EOF sentinel put
6. Iterator가 Queue에서 꺼내 yield
```

### 3.3 동기 Facade

```
MaasClient (동기)
  └── 전용 asyncio 루프를 백그라운드 스레드에서 실행
       call_sync() → run_coroutine_threadsafe(coro) → future.result(timeout)
```

---

## 4. SDK 구성

| 패키지 | 역할 | 주요 클래스 |
|--------|------|-------------|
| `maas-client-sdk` | RPC 호출 + pub/sub | `MaasClient` (동기), `MaasClientAsync` (비동기) |
| `maas-server-sdk` | RPC 핸들러 + pub/sub | `MaasServer`, `RpcContext` |

설치:
```bash
pip install maas-client-sdk
pip install maas-server-sdk
```

---

## 5. 연결 관리

### 5.1 클라이언트 (MQTT 5.0 over WSS)

- 전송: WebSocket (WSS, 포트 443)
- 인증: JWT 토큰을 MQTT username으로 전달 (AWS IoT Custom Authorizer)
- Keep-Alive: 30초 (AWS ALB idle timeout 대응)
- Clean Start: 항상 True (stale 응답 방지)

### 5.2 서비스 (MQTT 5.0 over TLS)

- 전송: TCP + TLS (포트 8883) 또는 WSS
- 인증: X.509 인증서 (Greengrass Component의 경우 Greengrass 관리)
- Keep-Alive: 60초

### 5.3 연결 끊김 처리

클라이언트 연결 끊김 시:
- `pending_map`의 모든 대기 중 Future를 즉시 `ConnectionError`로 reject
- 재연결 후 새로운 RPC 호출로 재시도

서비스의 클라이언트 단절 감지:
- `$aws/events/presence/disconnected/+` 구독
- 단절된 ClientId의 독점 세션 Lock 강제 해제
- 진행 중인 스트리밍 중단
