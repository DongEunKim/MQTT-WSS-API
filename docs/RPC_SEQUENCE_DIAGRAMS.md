# RPC 시퀀스 다이어그램

> 클라이언트 SDK가 사용하는 RPC 패턴별 전체 흐름.  
> 각 다이어그램은 흐름 구조를 간결하게 표현하고, 상세 메시지 사양은 다이어그램 아래에 별도로 기술한다.

---

## 참여자 (Participants)

| 기호 | 역할 |
|------|------|
| **App** | SDK를 호출하는 애플리케이션 코드 |
| **SDK** | `RpcClient` / `RpcClientAsync` (maas-rpc-client-sdk) |
| **GW** | WSS-MQTT API Gateway (WebSocket ↔ MQTT 변환 + ACL) |
| **Broker** | MQTT 브로커 |
| **Edge** | 엣지 서버 — Machine (RPC 서비스 제공) |

---

## 토픽 패턴 요약

```
요청  WMT/{service}/{thing_name}/{oem}/{asset}/request
응답  WMO/{service}/{thing_name}/{oem}/{asset}/{client_id}/response
```

예시 값: `service=RemoteUDS`, `thing_name=device_001`, `oem=acme`, `asset=VIN123`, `client_id=client_A`

---

## 0 — 엣지 서버 사전 구독 (서버 시작 시 1회)

> 엣지 서버가 기동될 때 요청 토픽을 미리 구독해 두어야 클라이언트 요청을 수신할 수 있다.  
> 이 구독은 서버 SDK 시작 시 **1회** 수행하며, 이후 모든 클라이언트 요청에 공유된다.

```mermaid
sequenceDiagram
    autonumber
    participant Edge
    participant Broker

    Note over Edge: 서버 SDK 시작 — Server.run_forever()
    Note over Edge: thing_name = "device_001"

    Edge->>Broker: MQTT SUBSCRIBE WMT/+/device_001/+/+/request
    Note over Broker: oem·asset 은 와일드카드(+) 구독
    Note over Broker: 접근 제어는 GW 가 담당
    Broker-->>Edge: SUBACK

    Note over Edge: 요청 대기 상태
```

**구독 패턴 상세**

```
단일 서비스:  WMT/RemoteUDS/device_001/+/+/request
복수 서비스:  WMT/+/device_001/+/+/request
```

- `oem`, `asset` 을 `+` 와일드카드로 구독 — 접근 제어는 GW 가 담당
- 수신 토픽에서 `oem`, `asset` 값을 파싱하여 `RequestContext` 에 주입

---

## 패턴 1 — `call()` : 단일 요청-응답

### 1-1 정상 흐름

> 전제: **0** 의 엣지 서버 사전 구독이 완료된 상태

```mermaid
sequenceDiagram
    autonumber
    participant App
    participant SDK
    participant GW
    participant Broker
    participant Edge

    Note over Edge,Broker: [전제] Edge 가 WMT/+/device_001/+/+/request 구독 완료
    Note over SDK,GW: [전제] 클라이언트 WebSocket 연결 및 JWT 인증 완료

    App->>SDK: call("RemoteUDS", payload)
    Note over SDK: request_id 생성
    Note over SDK: req_topic = WMT/RemoteUDS/device_001/acme/VIN123/request
    Note over SDK: res_topic = WMO/RemoteUDS/device_001/acme/VIN123/client_A/response

    SDK->>GW: SUBSCRIBE res_topic
    GW->>GW: ACL 검사 (service · oem+asset · client_id)
    GW->>Broker: MQTT SUBSCRIBE
    GW-->>SDK: ACK 200

    SDK->>GW: PUBLISH req_topic [RPC payload]
    GW->>GW: ACL 검사 (service · oem+asset)
    GW->>Broker: MQTT PUBLISH
    GW-->>SDK: ACK 200

    Broker->>Edge: 메시지 전달
    Note over Edge: 토픽에서 oem·asset 파싱
    Note over Edge: action 핸들러 실행

    Edge->>Broker: PUBLISH res_topic [성공 응답]
    Broker->>GW: 메시지 전달
    GW->>SDK: SUBSCRIPTION 이벤트

    Note over SDK: request_id 매칭 → result 반환

    SDK->>GW: UNSUBSCRIBE res_topic
    SDK-->>App: return result
```

**① 요청 Payload** (SDK → GW → Broker → Edge)

```json
{
  "request_id": "a3f9e2b1c4d5...",
  "response_topic": "WMO/RemoteUDS/device_001/acme/VIN123/client_A/response",
  "request": {
    "action": "readDTC",
    "params": { "source": 1 }
  }
}
```

**② 성공 응답 Payload** (Edge → Broker → GW → SDK)

```json
{
  "request_id": "a3f9e2b1c4d5...",
  "result": { "dtcList": [] },
  "error": null
}
```

---

### 1-2 예외 — 엣지 서버 에러 응답 (RpcError)

> 전제: Edge 가 WMT/+/device_001/+/+/request 구독 완료

```mermaid
sequenceDiagram
    autonumber
    participant App
    participant SDK
    participant GW
    participant Broker
    participant Edge

    Note over Edge,Broker: [전제] Edge 가 WMT/+/device_001/+/+/request 구독 완료

    App->>SDK: call("RemoteUDS", payload)
    SDK->>GW: SUBSCRIBE res_topic
    GW-->>SDK: ACK 200
    SDK->>GW: PUBLISH req_topic [RPC payload]
    GW-->>SDK: ACK 200
    GW->>Broker: MQTT PUBLISH
    Broker->>Edge: 메시지 전달

    Note over Edge: 처리 실패 — 에러 응답 생성

    Edge->>Broker: PUBLISH res_topic [에러 응답]
    Broker->>GW: 메시지 전달
    GW->>SDK: SUBSCRIPTION 이벤트

    Note over SDK: error 필드 존재 → RpcError

    SDK->>GW: UNSUBSCRIBE res_topic
    SDK-->>App: raise RpcError(code, message)
```

**에러 응답 Payload**

```json
{
  "request_id": "a3f9e2b1c4d5...",
  "result": null,
  "error": {
    "code": "DEVICE_BUSY",
    "message": "현재 처리 불가 상태입니다"
  }
}
```

---

### 1-3 예외 — 응답 타임아웃 (RpcTimeoutError)

> 전제: Edge 가 WMT/+/device_001/+/+/request 구독 완료

```mermaid
sequenceDiagram
    autonumber
    participant App
    participant SDK
    participant GW
    participant Broker
    participant Edge

    Note over Edge,Broker: [전제] Edge 가 WMT/+/device_001/+/+/request 구독 완료

    App->>SDK: call("RemoteUDS", payload, timeout=5.0)
    SDK->>GW: SUBSCRIBE res_topic
    GW-->>SDK: ACK 200
    SDK->>GW: PUBLISH req_topic [RPC payload]
    GW-->>SDK: ACK 200
    GW->>Broker: MQTT PUBLISH
    Broker->>Edge: 메시지 전달

    Note over Edge: 응답 없음 (처리 지연 / 네트워크 단절)
    Note over SDK: timeout=5.0 초 경과

    SDK->>GW: UNSUBSCRIBE res_topic
    SDK-->>App: raise RpcTimeoutError(service, request_id, timeout=5.0)
```

---

### 1-4 예외 — 게이트웨이 ACL 거부

```mermaid
sequenceDiagram
    autonumber
    participant App
    participant SDK
    participant GW

    App->>SDK: call("RemoteUDS", payload)
    SDK->>GW: SUBSCRIBE res_topic

    alt oem+asset 권한 없음
        GW-->>SDK: ACK 403 "접근 권한 없음"
        SDK-->>App: raise WssAckError(403)
    else client_id 불일치
        GW-->>SDK: ACK 403 "client_id 불일치"
        SDK-->>App: raise WssAckError(403)
    else service 미허용
        GW-->>SDK: ACK 422 "허용되지 않는 service"
        SDK-->>App: raise WssAckError(422)
    else 토픽 형식 오류
        GW-->>SDK: ACK 422 "Topic format invalid"
        SDK-->>App: raise WssAckError(422)
    end
```

> 발행(PUBLISH) 단계에서도 동일한 ACL 검사가 적용된다.  
> 발행 거부 시 SDK는 응답 토픽 구독을 자동 해제한 후 예외를 전달한다.

---

### 1-5 예외 — payload 검증 오류 (네트워크 미사용)

```mermaid
sequenceDiagram
    autonumber
    participant App
    participant SDK

    App->>SDK: call("RemoteUDS", {"params": {"source": 1}})
    Note over SDK: "action" 필드 없음 — 즉시 거부
    SDK-->>App: raise ValueError("payload에 'action' 필드가 필요합니다")
```

---

## 패턴 2 — `call_stream()` : 단일 요청, 멀티 응답

> 1회 요청 후 서버가 청크를 순차 발행.  
> `done: true` 수신 시 스트림 종료.

### 2-1 정상 흐름

> 전제: **0** 의 엣지 서버 사전 구독이 완료된 상태

```mermaid
sequenceDiagram
    autonumber
    participant App
    participant SDK
    participant GW
    participant Broker
    participant Edge

    Note over Edge,Broker: [전제] Edge 가 WMT/+/device_001/+/+/request 구독 완료
    Note over SDK,GW: [전제] 클라이언트 WebSocket 연결 및 JWT 인증 완료

    App->>SDK: call_stream("RemoteDashboard", payload)
    Note over SDK: request_id, req_topic, res_topic 생성

    SDK->>GW: SUBSCRIBE res_topic
    GW-->>SDK: ACK 200
    SDK->>GW: PUBLISH req_topic [RPC payload]
    GW-->>SDK: ACK 200
    GW->>Broker: MQTT PUBLISH
    Broker->>Edge: 메시지 전달

    loop 청크 전송 (done=false)
        Edge->>Broker: PUBLISH res_topic [청크 N, done=false]
        Broker->>GW: 메시지 전달
        GW->>SDK: SUBSCRIPTION 이벤트
        Note over SDK: request_id 매칭 → yield
        SDK-->>App: yield chunk_N
    end

    Edge->>Broker: PUBLISH res_topic [마지막 청크, done=true]
    Broker->>GW: 메시지 전달
    GW->>SDK: SUBSCRIPTION 이벤트
    Note over SDK: done=true → 마지막 yield 후 루프 종료
    SDK-->>App: yield chunk_last
    SDK->>GW: UNSUBSCRIBE res_topic
```

**중간 청크 Payload**

```json
{
  "request_id": "c7d8e9f0...",
  "result": { "chunk": [1, 2], "seq": 1 },
  "done": false
}
```

**마지막 청크 Payload**

```json
{
  "request_id": "c7d8e9f0...",
  "result": { "chunk": [10, 11], "seq": 5 },
  "done": true
}
```

---

### 2-2 예외 — 스트림 중 에러 응답

> 전제: Edge 가 WMT/+/device_001/+/+/request 구독 완료

```mermaid
sequenceDiagram
    autonumber
    participant App
    participant SDK
    participant GW
    participant Broker
    participant Edge

    Note over Edge,Broker: [전제] Edge 가 WMT/+/device_001/+/+/request 구독 완료

    App->>SDK: call_stream("RemoteDashboard", payload)
    SDK->>GW: SUBSCRIBE res_topic
    GW-->>SDK: ACK 200
    SDK->>GW: PUBLISH req_topic [RPC payload]
    GW-->>SDK: ACK 200
    GW->>Broker: MQTT PUBLISH
    Broker->>Edge: 메시지 전달

    Edge->>Broker: PUBLISH res_topic [청크 1, done=false]
    Broker->>GW: 메시지 전달
    GW->>SDK: SUBSCRIPTION 이벤트
    SDK-->>App: yield chunk_1

    Note over Edge: 처리 중 오류 발생

    Edge->>Broker: PUBLISH res_topic [에러 응답]
    Broker->>GW: 메시지 전달
    GW->>SDK: SUBSCRIPTION 이벤트
    Note over SDK: error 필드 존재 → 스트림 즉시 중단

    SDK->>GW: UNSUBSCRIBE res_topic
    SDK-->>App: raise RpcError(code="SENSOR_DISCONNECTED", ...)
```

---

### 2-3 예외 — 첫 청크 수신 타임아웃

> 전제: Edge 가 WMT/+/device_001/+/+/request 구독 완료

```mermaid
sequenceDiagram
    autonumber
    participant App
    participant SDK
    participant GW
    participant Broker
    participant Edge

    Note over Edge,Broker: [전제] Edge 가 WMT/+/device_001/+/+/request 구독 완료

    App->>SDK: call_stream("RemoteDashboard", payload, timeout=10.0)
    SDK->>GW: SUBSCRIBE res_topic
    GW-->>SDK: ACK 200
    SDK->>GW: PUBLISH req_topic [RPC payload]
    GW-->>SDK: ACK 200
    GW->>Broker: MQTT PUBLISH
    Broker->>Edge: 메시지 전달

    Note over Edge: 응답 없음

    Note over SDK: timeout=10.0 초 경과

    SDK->>GW: UNSUBSCRIBE res_topic
    SDK-->>App: raise RpcTimeoutError(service, request_id, timeout=10.0)
```

---

## 패턴 3 — 연결 수립 및 종료

### 3-1 WebSocket 연결 + JWT 인증

```mermaid
sequenceDiagram
    autonumber
    participant App
    participant SDK
    participant GW

    App->>SDK: RpcClient(url, token, thing_name, oem, asset, client_id)
    App->>SDK: connect()

    SDK->>GW: WebSocket Upgrade (Authorization: Bearer JWT)

    GW->>GW: JWT 서명·만료 검증
    GW->>GW: client_id·oem+asset 목록 추출
    GW->>GW: 세션 초기화

    alt 인증 성공
        GW-->>SDK: 101 Switching Protocols
        SDK-->>App: connect() 완료
    else JWT 만료 / 서명 오류
        GW-->>SDK: 401 Unauthorized
        SDK-->>App: raise WssConnectionError(401)
    else 서버 오류
        GW-->>SDK: 503 Service Unavailable
        SDK-->>App: raise WssConnectionError(503)
    end
```

---

### 3-2 연결 종료

```mermaid
sequenceDiagram
    autonumber
    participant App
    participant SDK
    participant GW
    participant Broker

    App->>SDK: disconnect() 또는 with 블록 종료

    Note over SDK: 진행 중인 call_stream 태스크 모두 취소

    SDK->>GW: WebSocket Close
    GW->>Broker: MQTT UNSUBSCRIBE (세션 내 전체 구독 해제)
    GW->>GW: Subscription Map 정리
    GW-->>SDK: Close ACK
    SDK-->>App: disconnect() 완료
```

---

## 패턴 4 — 복수 클라이언트 동시 접근

> 동일 엣지 서버에 A, B 두 클라이언트가 동시에 요청.  
> `client_id` 가 다르면 응답 토픽이 완전히 격리된다.

> 전제: Edge 가 WMT/+/device_001/+/+/request 구독 완료

```mermaid
sequenceDiagram
    autonumber
    participant A as 클라이언트 A
    participant B as 클라이언트 B
    participant GW
    participant Broker
    participant Edge

    Note over Edge,Broker: [전제] Edge 가 WMT/+/device_001/+/+/request 구독 완료
    Note over A: client_id = client_A
    Note over B: client_id = client_B

    par 동시 구독
        A->>GW: SUBSCRIBE WMO/.../client_A/response
        B->>GW: SUBSCRIBE WMO/.../client_B/response
    end
    GW->>Broker: SUBSCRIBE (client_A 토픽)
    GW->>Broker: SUBSCRIBE (client_B 토픽)
    GW-->>A: ACK 200
    GW-->>B: ACK 200

    par 동시 발행
        A->>GW: PUBLISH WMT/.../request [req-AAA]
        B->>GW: PUBLISH WMT/.../request [req-BBB]
    end
    GW->>Broker: PUBLISH [req-AAA]
    GW->>Broker: PUBLISH [req-BBB]
    Broker->>Edge: req-AAA 전달
    Broker->>Edge: req-BBB 전달

    Note over Edge: 두 요청 독립 처리

    Edge->>Broker: PUBLISH .../client_A/response [req-AAA 결과]
    Edge->>Broker: PUBLISH .../client_B/response [req-BBB 결과]

    Broker->>GW: client_A 응답
    Broker->>GW: client_B 응답
    GW->>A: SUBSCRIPTION [req-AAA]
    GW->>B: SUBSCRIPTION [req-BBB]

    Note over A: 자신의 응답만 수신
    Note over B: 자신의 응답만 수신
    Note over GW: 타 클라이언트 토픽 구독 시도 시 ACK 403 거부
```

---

## 예외 코드 요약

| 발생 위치 | 예외 타입 | 원인 |
|-----------|-----------|------|
| SDK 내부 | `ValueError` | payload에 `action` 필드 없음 |
| GW ACK | `WssAckError(403)` | oem+asset 접근 권한 없음 |
| GW ACK | `WssAckError(403)` | WMO 구독 시 client_id 불일치 |
| GW ACK | `WssAckError(422)` | service 미허용 또는 토픽 형식 오류 |
| Edge 응답 | `RpcError` | 서버가 `error` 필드로 응답 |
| 타임아웃 | `RpcTimeoutError` | 응답 미수신, timeout 경과 |
| 연결 | `WssConnectionError` | WebSocket 연결 실패 또는 JWT 인증 오류 |

---

## 메시지 Envelope 규격 (WSS ↔ GW)

```json
// 발행 요청 (Client → GW)
{ "action": "PUBLISH", "req_id": "wss-pub-001",
  "topic": "WMT/…/request", "payload": { /* RPC 요청 */ } }

// 구독 요청 (Client → GW)
{ "action": "SUBSCRIBE", "req_id": "wss-sub-001",
  "topic": "WMO/…/response" }

// ACK (GW → Client)
{ "event": "ACK", "req_id": "wss-sub-001", "code": 200 }

// 구독 이벤트 전달 (GW → Client)
{ "event": "SUBSCRIPTION", "req_id": "wss-sub-001",
  "topic": "WMO/…/response", "payload": { /* RPC 응답 */ } }
```

---

## 참조

- [`TOPIC_AND_ACL_SPEC.md`](TOPIC_AND_ACL_SPEC.md) — WMT/WMO 토픽 패턴 및 ACL 규격
- [`RPC_DESIGN.md`](RPC_DESIGN.md) — RPC 방법론 및 전송 계층 설계
- [`system_specification_v1.md`](system_specification_v1.md) — WSS-MQTT API 전체 사양
