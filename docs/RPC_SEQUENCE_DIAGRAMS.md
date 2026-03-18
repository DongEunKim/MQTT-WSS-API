# RPC 시퀀스 다이어그램

> 클라이언트 SDK가 사용하는 RPC 패턴별 전체 흐름.  
> 정상 흐름, 예외 상황, 메시지 사양을 포함한다.

---

## 등장 인물 (Participants)

| 기호 | 이름 | 설명 |
|------|------|------|
| **App** | 애플리케이션 | SDK를 사용하는 최종 코드 |
| **SDK** | RpcClient / RpcClientAsync | maas-rpc-client-sdk |
| **GW** | WSS-MQTT API Gateway | WebSocket ↔ MQTT 프로토콜 변환 및 ACL 처리 |
| **Broker** | MQTT Broker | 토픽 기반 발행/구독 브로커 |
| **Edge** | 엣지 서버 (Machine) | 브로커에 연결된 RPC 서비스 제공 서버 |

---

## 메시지 사양 참조

### WSS Envelope (클라이언트 ↔ 게이트웨이)

```json
// 발행 요청 (Client → GW)
{
  "action": "PUBLISH",
  "req_id": "wss-req-001",
  "topic": "WMT/{service}/{thing_name}/{oem}/{asset}/request",
  "payload": { /* RPC 요청 Payload */ }
}

// 구독 요청 (Client → GW)
{
  "action": "SUBSCRIBE",
  "req_id": "wss-req-002",
  "topic": "WMO/{service}/{thing_name}/{oem}/{asset}/{client_id}/response"
}

// ACK (GW → Client)
{
  "event": "ACK",
  "req_id": "wss-req-001",
  "code": 200
}

// 구독 이벤트 전달 (GW → Client)
{
  "event": "SUBSCRIPTION",
  "req_id": "wss-req-002",
  "topic": "WMO/{service}/{thing_name}/{oem}/{asset}/{client_id}/response",
  "payload": { /* RPC 응답 Payload */ }
}
```

### RPC 요청 Payload (클라이언트 → 엣지 서버)

```json
{
  "request_id": "a3f9e2b1c4d5...",
  "response_topic": "WMO/{service}/{thing_name}/{oem}/{asset}/{client_id}/response",
  "request": {
    "action": "readDTC",
    "params": { "source": 1 }
  }
}
```

### RPC 응답 Payload (엣지 서버 → 클라이언트)

```json
// 성공
{ "request_id": "a3f9e2b1...", "result": { "dtcList": [] }, "error": null }

// 실패
{ "request_id": "a3f9e2b1...", "result": null,
  "error": { "code": "DEVICE_BUSY", "message": "처리 불가" } }

// call_stream 청크 (중간)
{ "request_id": "a3f9e2b1...", "result": { "chunk": [...] }, "done": false }

// call_stream 종료 청크
{ "request_id": "a3f9e2b1...", "result": { "chunk": [...] }, "done": true }
```

---

## 패턴 1 — `call()` : 단일 요청-응답 (Request-Response)

### 1.1 정상 흐름

```mermaid
sequenceDiagram
    autonumber
    participant App
    participant SDK
    participant GW as WSS-MQTT GW
    participant Broker as MQTT Broker
    participant Edge as 엣지 서버

    Note over SDK,GW: 전제: WebSocket 연결 및 JWT 인증 완료

    App->>SDK: client.call("RemoteUDS",<br/>{"action":"readDTC","params":{"source":1}})

    Note over SDK: ① request_id 생성<br/>request_id = uuid4().hex<br/>② 토픽 생성<br/>req_topic = WMT/RemoteUDS/device_001/acme/VIN123/request<br/>res_topic = WMO/RemoteUDS/device_001/acme/VIN123/client_A/response

    SDK->>GW: SUBSCRIBE {<br/>  "action":"SUBSCRIBE",<br/>  "req_id":"wss-sub-001",<br/>  "topic":"WMO/RemoteUDS/device_001/acme/VIN123/client_A/response"<br/>}

    GW->>GW: ACL 검사<br/>① service "RemoteUDS" 허용 목록 확인 ✓<br/>② oem="acme" + asset="VIN123" 접근 허가 확인 ✓<br/>③ 토픽의 client_id == 세션 client_id 확인 ✓
    GW->>Broker: MQTT SUBSCRIBE<br/>"WMO/RemoteUDS/device_001/acme/VIN123/client_A/response"
    GW-->>SDK: ACK { "event":"ACK", "req_id":"wss-sub-001", "code":200 }

    Note over SDK: Subscription Map 등록 완료.<br/>이제 PUBLISH 요청 발송.

    SDK->>GW: PUBLISH {<br/>  "action":"PUBLISH",<br/>  "req_id":"wss-pub-001",<br/>  "topic":"WMT/RemoteUDS/device_001/acme/VIN123/request",<br/>  "payload":{<br/>    "request_id":"a3f9e2b1",<br/>    "response_topic":"WMO/.../client_A/response",<br/>    "request":{"action":"readDTC","params":{"source":1}}<br/>  }<br/>}

    GW->>GW: ACL 검사<br/>① service 허용 확인 ✓<br/>② oem+asset 접근 허가 확인 ✓
    GW->>Broker: MQTT PUBLISH<br/>topic: WMT/RemoteUDS/device_001/acme/VIN123/request
    GW-->>SDK: ACK { "event":"ACK", "req_id":"wss-pub-001", "code":200 }

    Broker->>Edge: 메시지 전달<br/>(구독 패턴 WMT/+/device_001/+/+/request 에 매칭)

    Note over Edge: payload 파싱<br/>request_id, response_topic 추출<br/>action="readDTC" 핸들러 실행

    Edge->>Broker: MQTT PUBLISH<br/>topic: WMO/RemoteUDS/device_001/acme/VIN123/client_A/response<br/>payload: {<br/>  "request_id":"a3f9e2b1",<br/>  "result":{"dtcList":[]},<br/>  "error":null<br/>}

    Broker->>GW: 구독 메시지 도착
    GW->>SDK: SUBSCRIPTION {<br/>  "event":"SUBSCRIPTION",<br/>  "req_id":"wss-sub-001",<br/>  "topic":"WMO/.../client_A/response",<br/>  "payload":{"request_id":"a3f9e2b1","result":{"dtcList":[]},"error":null}<br/>}

    Note over SDK: request_id 일치 확인 ✓<br/>error 필드 없음 ✓<br/>구독 해제 + result 반환

    SDK->>GW: UNSUBSCRIBE "WMO/.../client_A/response"
    SDK-->>App: return {"dtcList": []}
```

---

### 1.2 예외 — 엣지 서버가 에러 응답 (RpcError)

```mermaid
sequenceDiagram
    autonumber
    participant App
    participant SDK
    participant GW as WSS-MQTT GW
    participant Broker as MQTT Broker
    participant Edge as 엣지 서버

    App->>SDK: client.call("RemoteUDS",<br/>{"action":"readDTC","params":{"source":99}})

    SDK->>GW: SUBSCRIBE (응답 토픽)
    GW-->>SDK: ACK 200
    SDK->>GW: PUBLISH (요청 토픽, request_id="b5c3d2e1")
    GW-->>SDK: ACK 200
    GW->>Broker: MQTT PUBLISH
    Broker->>Edge: 메시지 전달

    Note over Edge: source=99 존재하지 않음<br/>→ 에러 응답 생성

    Edge->>Broker: MQTT PUBLISH (response_topic)<br/>payload: {<br/>  "request_id":"b5c3d2e1",<br/>  "result": null,<br/>  "error": {<br/>    "code": "INVALID_SOURCE",<br/>    "message": "source 99는 지원하지 않습니다"<br/>  }<br/>}

    Broker->>GW: 구독 메시지 도착
    GW->>SDK: SUBSCRIPTION (응답 payload 전달)

    Note over SDK: request_id 일치 ✓<br/>error 필드 존재 → RpcError 발생

    SDK->>GW: UNSUBSCRIBE (응답 토픽)
    SDK-->>App: raise RpcError(<br/>  code="INVALID_SOURCE",<br/>  message="source 99는 지원하지 않습니다"<br/>)
```

---

### 1.3 예외 — 타임아웃 (RpcTimeoutError)

```mermaid
sequenceDiagram
    autonumber
    participant App
    participant SDK
    participant GW as WSS-MQTT GW
    participant Broker as MQTT Broker
    participant Edge as 엣지 서버

    App->>SDK: client.call("RemoteUDS",<br/>{"action":"readDTC"},<br/>timeout=5.0)

    SDK->>GW: SUBSCRIBE (응답 토픽)
    GW-->>SDK: ACK 200
    SDK->>GW: PUBLISH (요청 토픽)
    GW-->>SDK: ACK 200
    GW->>Broker: MQTT PUBLISH
    Broker->>Edge: 메시지 전달

    Note over Edge: 처리 지연 또는 응답 없음<br/>(네트워크 단절, 과부하 등)

    Note over SDK: ⏱ timeout=5.0초 경과<br/>SubscriptionTimeoutError 발생

    SDK->>GW: UNSUBSCRIBE (응답 토픽, 자동 정리)
    SDK-->>App: raise RpcTimeoutError(<br/>  service="RemoteUDS",<br/>  request_id="...",<br/>  timeout=5.0<br/>)
```

---

### 1.4 예외 — 게이트웨이 ACL 거부 (구독 단계)

```mermaid
sequenceDiagram
    autonumber
    participant App
    participant SDK
    participant GW as WSS-MQTT GW

    App->>SDK: client.call("RemoteUDS", {"action":"readDTC"})

    Note over SDK: 토픽 생성<br/>res_topic = WMO/RemoteUDS/device_001/acme/VIN123/client_A/response

    SDK->>GW: SUBSCRIBE {<br/>  "action":"SUBSCRIBE",<br/>  "req_id":"wss-sub-001",<br/>  "topic":"WMO/RemoteUDS/device_001/acme/VIN123/client_A/response"<br/>}

    alt oem+asset 권한 없음
        GW-->>SDK: ACK {<br/>  "event":"ACK",<br/>  "req_id":"wss-sub-001",<br/>  "code": 403,<br/>  "message": "접근 권한 없음: acme/VIN123"<br/>}
        SDK-->>App: raise WssAckError(code=403, ...)
    else client_id 불일치
        GW-->>SDK: ACK {<br/>  "event":"ACK",<br/>  "req_id":"wss-sub-001",<br/>  "code": 403,<br/>  "message": "client_id 불일치"<br/>}
        SDK-->>App: raise WssAckError(code=403, ...)
    else service 미허용
        GW-->>SDK: ACK {<br/>  "event":"ACK",<br/>  "req_id":"wss-sub-001",<br/>  "code": 422,<br/>  "message": "허용되지 않는 service: RemoteUDS"<br/>}
        SDK-->>App: raise WssAckError(code=422, ...)
    end
```

---

### 1.5 예외 — 게이트웨이 ACL 거부 (발행 단계)

```mermaid
sequenceDiagram
    autonumber
    participant App
    participant SDK
    participant GW as WSS-MQTT GW

    App->>SDK: client.call("RemoteUDS", {"action":"readDTC"})

    SDK->>GW: SUBSCRIBE (응답 토픽)
    GW-->>SDK: ACK 200 ✓

    SDK->>GW: PUBLISH {<br/>  "action":"PUBLISH",<br/>  "req_id":"wss-pub-001",<br/>  "topic":"WMT/RemoteUDS/device_001/acme/VIN123/request",<br/>  "payload": {...}<br/>}

    alt oem+asset 권한 없음
        GW-->>SDK: ACK {<br/>  "event":"ACK",<br/>  "req_id":"wss-pub-001",<br/>  "code": 403,<br/>  "message": "발행 권한 없음: acme/VIN123"<br/>}
        SDK->>GW: UNSUBSCRIBE (응답 토픽 자동 정리)
        SDK-->>App: raise WssAckError(code=403, ...)
    else 토픽 형식 오류
        GW-->>SDK: ACK { "code": 422, "message": "Topic format invalid for WMT" }
        SDK->>GW: UNSUBSCRIBE (응답 토픽 자동 정리)
        SDK-->>App: raise WssAckError(code=422, ...)
    end
```

---

### 1.6 예외 — payload 검증 오류 (SDK 내부)

```mermaid
sequenceDiagram
    autonumber
    participant App
    participant SDK

    App->>SDK: client.call("RemoteUDS",<br/>{"params": {"source": 1}})
    Note over SDK: payload에 "action" 필드 없음<br/>→ 네트워크 왕복 없이 즉시 거부
    SDK-->>App: raise ValueError("payload에 'action' 필드가 필요합니다")
```

---

## 패턴 2 — `call_stream()` : 단일 요청, 멀티 응답

> 1회 요청 후 서버가 여러 청크를 순차 발행. `done: true` 또는 `stream_end: true` 수신 시 종료.  
> 동일 응답 토픽을 사용하며, 각 청크는 `request_id`로 매칭된다.

### 2.1 정상 흐름

```mermaid
sequenceDiagram
    autonumber
    participant App
    participant SDK
    participant GW as WSS-MQTT GW
    participant Broker as MQTT Broker
    participant Edge as 엣지 서버

    App->>SDK: async for chunk in<br/>client.call_stream("RemoteDashboard",<br/>{"action":"getLiveData"})

    Note over SDK: request_id = uuid4().hex<br/>res_topic = WMO/RemoteDashboard/device_001/acme/VIN123/client_A/response<br/>req_topic = WMT/RemoteDashboard/device_001/acme/VIN123/request

    SDK->>GW: SUBSCRIBE (응답 토픽)
    GW->>GW: ACL 검사 ✓
    GW->>Broker: MQTT SUBSCRIBE
    GW-->>SDK: ACK 200

    SDK->>GW: PUBLISH {<br/>  "topic": "WMT/RemoteDashboard/device_001/acme/VIN123/request",<br/>  "payload": {<br/>    "request_id": "c7d8e9f0",<br/>    "response_topic": "WMO/.../client_A/response",<br/>    "request": {"action":"getLiveData","params":{}}<br/>  }<br/>}
    GW-->>SDK: ACK 200
    GW->>Broker: MQTT PUBLISH
    Broker->>Edge: 메시지 전달

    Note over Edge: 스트리밍 데이터 준비

    loop 청크 N (done=false)
        Edge->>Broker: PUBLISH response_topic<br/>{<br/>  "request_id":"c7d8e9f0",<br/>  "result":{"chunk":[...], "seq":N},<br/>  "done": false<br/>}
        Broker->>GW: 메시지 도착
        GW->>SDK: SUBSCRIPTION (payload 전달)
        Note over SDK: request_id 일치 ✓<br/>done=false → yield result
        SDK-->>App: yield {"chunk":[...], "seq":N}
    end

    Edge->>Broker: PUBLISH response_topic (마지막 청크)<br/>{<br/>  "request_id":"c7d8e9f0",<br/>  "result":{"chunk":[...], "seq":N+1},<br/>  "done": true<br/>}
    Broker->>GW: 메시지 도착
    GW->>SDK: SUBSCRIPTION (마지막 payload)
    Note over SDK: done=true → 마지막 result yield 후 루프 종료

    SDK-->>App: yield {"chunk":[...], "seq":N+1}
    Note over SDK: 스트림 종료.<br/>UNSUBSCRIBE 자동 처리.
    SDK->>GW: UNSUBSCRIBE (응답 토픽)
```

---

### 2.2 예외 — 스트림 중 에러 응답

```mermaid
sequenceDiagram
    autonumber
    participant App
    participant SDK
    participant GW as WSS-MQTT GW
    participant Broker as MQTT Broker
    participant Edge as 엣지 서버

    App->>SDK: async for chunk in client.call_stream(...)

    SDK->>GW: SUBSCRIBE ✓
    SDK->>GW: PUBLISH ✓
    Broker->>Edge: 메시지 전달

    Edge->>Broker: PUBLISH response_topic (청크 1)<br/>{"request_id":"...","result":{...},"done":false}
    Broker->>GW: 도착
    GW->>SDK: SUBSCRIPTION
    SDK-->>App: yield result (청크 1)

    Note over Edge: 처리 중 오류 발생 (예: 센서 연결 끊김)

    Edge->>Broker: PUBLISH response_topic (에러 청크)<br/>{<br/>  "request_id":"c7d8e9f0",<br/>  "result": null,<br/>  "error": {<br/>    "code": "SENSOR_DISCONNECTED",<br/>    "message": "센서 연결이 끊어졌습니다"<br/>  }<br/>}
    Broker->>GW: 도착
    GW->>SDK: SUBSCRIPTION

    Note over SDK: error 필드 존재 → RpcError 발생<br/>스트림 즉시 중단

    SDK->>GW: UNSUBSCRIBE (자동 정리)
    SDK-->>App: raise RpcError(<br/>  code="SENSOR_DISCONNECTED",<br/>  message="센서 연결이 끊어졌습니다"<br/>)
```

---

### 2.3 예외 — 첫 청크 수신 타임아웃

```mermaid
sequenceDiagram
    autonumber
    participant App
    participant SDK
    participant GW as WSS-MQTT GW
    participant Edge as 엣지 서버

    App->>SDK: async for chunk in<br/>client.call_stream(..., timeout=10.0)

    SDK->>GW: SUBSCRIBE ✓ (timeout=10.0 설정)
    SDK->>GW: PUBLISH ✓

    Note over Edge: 응답 없음 또는 지연

    Note over SDK: ⏱ timeout=10.0초 경과<br/>구독 스트림에서 SubscriptionTimeoutError

    SDK->>GW: UNSUBSCRIBE (자동 정리)
    SDK-->>App: raise RpcTimeoutError(<br/>  service="RemoteDashboard",<br/>  request_id="...",<br/>  timeout=10.0<br/>)
```

---

## 패턴 3 — 연결 수립 및 인증

> 모든 RPC 패턴의 전제 조건.

### 3.1 WebSocket 연결 + JWT 인증

```mermaid
sequenceDiagram
    autonumber
    participant App
    participant SDK
    participant GW as WSS-MQTT GW

    App->>SDK: RpcClient(<br/>  url="wss://api.example.com/v1/messaging",<br/>  token="eyJhbGci...",<br/>  thing_name="device_001",<br/>  oem="acme",<br/>  asset="VIN123",<br/>  client_id="client_A"  ← None이면 uuid 자동 생성<br/>)
    App->>SDK: client.connect()

    SDK->>GW: WebSocket Upgrade 요청<br/>GET /v1/messaging HTTP/1.1<br/>Upgrade: websocket<br/>Authorization: Bearer eyJhbGci...

    GW->>GW: JWT 검증<br/>① 서명 유효성 확인<br/>② 만료(exp) 확인<br/>③ 클레임에서 client_id 및<br/>   허가된 oem+asset 목록 추출<br/>④ 세션 생성 (Subscription Map 초기화)

    alt JWT 유효
        GW-->>SDK: 101 Switching Protocols<br/>(WebSocket 연결 수립)
        SDK-->>App: connect() 완료
    else JWT 만료 / 서명 오류
        GW-->>SDK: 401 Unauthorized<br/>WebSocket 연결 거부
        SDK-->>App: raise WssConnectionError("인증 실패: 401")
    else 서버 오류
        GW-->>SDK: 503 Service Unavailable
        SDK-->>App: raise WssConnectionError("연결 실패: 503")
    end
```

---

### 3.2 연결 종료

```mermaid
sequenceDiagram
    autonumber
    participant App
    participant SDK
    participant GW as WSS-MQTT GW
    participant Broker as MQTT Broker

    App->>SDK: client.disconnect()<br/>(또는 with 블록 종료)

    Note over SDK: 진행 중인 call_stream 태스크 취소

    SDK->>GW: WebSocket Close Frame
    GW->>Broker: MQTT UNSUBSCRIBE (세션 내 모든 구독 해제)
    GW->>GW: Subscription Map 정리<br/>세션 제거
    GW-->>SDK: WebSocket Close Ack
    SDK-->>App: disconnect() 완료
```

---

## 패턴 4 — 복수 클라이언트 동시 접근

> 동일 엣지 서버에 여러 클라이언트가 동시에 RPC 요청하는 경우.  
> 각 클라이언트는 고유한 `client_id`로 응답 토픽이 격리된다.

```mermaid
sequenceDiagram
    autonumber
    participant AppA as 클라이언트 A
    participant AppB as 클라이언트 B
    participant GW as WSS-MQTT GW
    participant Broker as MQTT Broker
    participant Edge as 엣지 서버

    Note over AppA,AppB: 두 클라이언트 모두 연결 완료<br/>client_A: client_id="client_A"<br/>client_B: client_id="client_B"

    par 동시 요청
        AppA->>GW: SUBSCRIBE<br/>WMO/RemoteUDS/device_001/acme/VIN123/client_A/response
        AppB->>GW: SUBSCRIBE<br/>WMO/RemoteUDS/device_001/acme/VIN123/client_B/response
    end

    GW->>Broker: SUBSCRIBE (client_A 응답 토픽)
    GW->>Broker: SUBSCRIBE (client_B 응답 토픽)

    par 동시 발행
        AppA->>GW: PUBLISH WMT/.../request<br/>payload.request_id="req-AAA"<br/>payload.response_topic=".../client_A/response"
        AppB->>GW: PUBLISH WMT/.../request<br/>payload.request_id="req-BBB"<br/>payload.response_topic=".../client_B/response"
    end

    GW->>Broker: MQTT PUBLISH (req-AAA)
    GW->>Broker: MQTT PUBLISH (req-BBB)
    Broker->>Edge: req-AAA 도착
    Broker->>Edge: req-BBB 도착

    Note over Edge: 독립적으로 각 요청 처리

    Edge->>Broker: PUBLISH ".../client_A/response"<br/>{"request_id":"req-AAA","result":{...}}
    Edge->>Broker: PUBLISH ".../client_B/response"<br/>{"request_id":"req-BBB","result":{...}}

    Broker->>GW: client_A 응답 도착
    Broker->>GW: client_B 응답 도착

    GW->>AppA: SUBSCRIPTION (req-AAA 결과)
    GW->>AppB: SUBSCRIPTION (req-BBB 결과)

    Note over AppA,AppB: 각 클라이언트가 자신의 결과만 수신.<br/>client_B가 client_A 응답 토픽 구독 시도 시<br/>게이트웨이가 403으로 거부.
```

---

## 전체 예외 코드 요약

| 발생 위치 | 예외 / 코드 | 원인 | SDK 동작 |
|-----------|-------------|------|----------|
| SDK (내부) | `ValueError` | payload에 `action` 필드 없음 | 즉시 raise, 네트워크 요청 없음 |
| GW → SDK | `WssAckError(403)` | oem+asset 접근 권한 없음 | raise, 구독 자동 정리 |
| GW → SDK | `WssAckError(403)` | WMO 구독 시 client_id 불일치 | raise |
| GW → SDK | `WssAckError(422)` | service 미허용 | raise |
| GW → SDK | `WssAckError(422)` | 토픽 형식 오류 (세그먼트 수 불일치) | raise |
| Edge → SDK | `RpcError` | 서버가 `error` 필드로 응답 | raise, 구독 자동 정리 |
| SDK (타임아웃) | `RpcTimeoutError` | 응답 미수신, timeout 경과 | raise, 구독 자동 정리 |
| Transport | `WssConnectionError` | WebSocket 연결 실패, JWT 인증 오류 | raise |

---

## 참조

- `docs/TOPIC_AND_ACL_SPEC.md` — WMT/WMO 토픽 패턴 및 ACL 규격
- `docs/RPC_DESIGN.md` — RPC 방법론 및 전송 계층 설계
- `docs/system_specification_v1.md` — WSS-MQTT API 사양 (Envelope, ACK, SUBSCRIPTION 등)
- `SDK/client/python/maas-rpc-client-sdk/maas_rpc_client/client_async.py` — SDK 구현체
