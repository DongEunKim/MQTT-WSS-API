# MQTT 기반 RPC 방법론

> WSS는 중계(wrapper)일 뿐이며, **클라이언트 ↔ TGU 간 RPC는 MQTT 패턴**으로 구현된다.  
> 본 문서는 MQTT만으로 RPC를 구현하는 방법론을 정리한다.
>
> **TGU 관점**: MQTT payload는 RPC를 위한 **전송 계층 래퍼**이며, TGU는 payload에서 응답 위치를 명시적으로 읽어 처리한다. 상세 설계는 `docs/RPC_TRANSPORT_LAYER_DESIGN.md` 참조.

---

## 1. MQTT의 비동기 특성

MQTT는 **발행/구독** 기반이다. 발행 시점에 수신자를 기다리지 않는다.

- `publish(topic, payload)` → 즉시 반환
- 응답을 받으려면 **별도 토픽을 구독**하고, 상대방이 그 토픽에 발행해야 함

따라서 RPC(request → wait → response)는 **토픽 2개 + payload 상관관계**로 구현한다.

---

## 2. 토픽 역할 분리

| 구분 | 토픽 | 발행자 | 구독자 | 용도 |
|------|------|--------|--------|------|
| **Request** | `WMT/{service}/{vehicle_id}/request` | 클라이언트 | TGU | RPC 요청 |
| **Response** | `WMO/{service}/{vehicle_id}/{client_id}/response` | TGU | 클라이언트 | RPC 응답 |

- **요청·응답 토픽 분리**: 요청과 응답이 서로 다른 토픽으로 오간다.
- **response_topic**: 클라이언트가 응답 수신 토픽을 payload에 명시. TGU는 그 토픽에 그대로 발행한다 (VISSv2 MQTT 패턴).

---

## 3. Payload 상관관계 (Correlation)

동일 응답 토픽에 여러 요청의 응답이 올 수 있으므로, **어떤 요청에 대한 응답인지** 구분해야 한다.

### 3.1 요청 Payload (VISSv2 스타일 — response_topic 명시)

> TGU는 payload에서 **응답할 토픽을 명시적으로** 읽는다. 토픽 패턴을 알 필요 없다.

```json
{
  "request_id": "req-550e8400-e29b",
  "response_topic": "WMO/RemoteUDS/v001/client_A/response",
  "request": {
    "action": "readDTC",
    "params": { "source": 1 }
  }
}
```

| 필드 | 필수 | 설명 |
|------|------|------|
| request_id | Y | 요청당 고유 ID. 응답 매칭용 |
| response_topic | Y | **TGU가 응답을 발행할 토픽. 클라이언트가 명시.** |
| request | Y | 서비스별 요청 (action, path, params 등). 서비스 명세 따름 |

- **response_topic**: SDK가 `WMO/{service}/{vehicle_id}/{client_id}/response` 형식으로 생성 후 payload에 포함
- **request**: 서비스(VISSv3, RemoteUDS 등)별 payload. RPC 전송 래퍼는 이 내용을 그대로 전달

### 3.2 응답 Payload

```json
{
  "request_id": "req-550e8400-e29b",
  "result": { "dtcList": [...] },
  "error": null
}
```

또는 에러 시:

```json
{
  "request_id": "req-550e8400-e29b",
  "result": null,
  "error": { "code": "TIMEOUT", "message": "..." }
}
```

| 필드 | 필수 | 설명 |
|------|------|------|
| request_id | Y | 요청의 request_id와 동일. 매칭용 |
| result | N | 성공 시 결과 |
| error | N | 실패 시 에러 정보 |

---

## 4. RPC 시퀀스 (MQTT 레벨)

```
클라이언트                              MQTT 브로커                              TGU
    │                                        │                                    │
    │ 1. SUBSCRIBE WMO/.../client_A/response │                                    │
    │───────────────────────────────────────>│                                    │
    │                                        │ 2. SUBSCRIBE WMT/.../request       │
    │                                        │<───────────────────────────────────│
    │                                        │                                    │
    │ 3. PUBLISH WMT/.../request             │                                    │
    │    {request_id, response_topic, request}  │                               │
    │───────────────────────────────────────>│───────────────────────────────────>│
    │                                        │                                    │
    │                                        │          4. 처리 후 PUBLISH         │
    │                                        │             WMO/.../client_A/response
    │                                        │             {request_id, result}             │
    │                                        │<───────────────────────────────────│
    │ 5. 수신 (구독 토픽)                      │                                    │
    │<───────────────────────────────────────│                                    │
    │    {request_id, result}                  │                                    │
```

### 4.1 클라이언트 흐름

1. **구독 선등록**: 응답 토픽 `WMO/{service}/{vehicle_id}/{client_id}/response` 구독
2. **요청 발행**: `WMT/{service}/{vehicle_id}/request`에 payload 발행
3. **응답 대기**: 구독 토픽에서 `request_id`가 일치하는 메시지 수신
4. **타임아웃**: 일정 시간 내 수신 없으면 에러 처리

### 4.2 TGU 흐름

1. **요청 구독**: 처리 대상 `WMT/.../request` 토픽 구독
2. **요청 수신**: payload에서 `response_topic`, `request_id`, `request` 추출
3. **처리**: `request`(action, params 등)에 따라 서비스 로직 실행
4. **응답 발행**: **`payload.response_topic`**에 `{request_id, result/error}` 발행

---

## 5. WSS 래퍼의 역할

WSS-MQTT API 게이트웨이는 **MQTT를 직접 쓰지 않는 클라이언트**를 위해:

- WebSocket으로 JSON Envelope 수신
- `action: "PUBLISH"` → MQTT Publish
- `action: "SUBSCRIBE"` → MQTT Subscribe
- MQTT에서 수신한 메시지 → `SUBSCRIPTION` 이벤트로 WebSocket 전달

**RPC 패턴은 그대로 유지**된다. 토픽 구조와 payload 상관관계는 동일하다.

---

## 6. VISSv2 MQTT 패턴 참조

VISSv2 Transport 사양의 MQTT 섹션은 `{"topic": "응답토픽", "request": "서비스요청"}` 형식을 사용한다.  
본 설계의 `response_topic` + `request` 구조는 이를 따르며, TGU가 payload만으로 응답 위치를 명시적으로 알 수 있게 한다.

상세: `docs/RPC_TRANSPORT_LAYER_DESIGN.md`

---

## 7. MQTT 5.0 Request/Response (참고)

MQTT 5.0에는 `Response Topic`, `Correlation Data` 프로퍼티가 있어, 표준 RPC 패턴을 지원한다.  
다만 MQTT 3.1.1 호환·브로커 제약을 고려하면, **토픽 + payload 기반 상관관계**가 더 범용적이다.

---

## 8. 정리

| 항목 | 내용 |
|------|------|
| **토픽 분리** | Request 토픽(WMT) / Response 토픽(WMO, client_id 포함) |
| **상관관계** | payload의 `request_id`로 요청-응답 매칭 |
| **클라이언트** | ① 응답 토픽 구독 ② 요청 발행 (response_topic 포함) ③ request_id 일치하는 응답 대기 |
| **TGU** | ① 요청 토픽 구독 ② payload.response_topic, request 추출 ③ response_topic에 응답 발행 |
| **WSS** | MQTT를 WebSocket Envelope으로 감싸는 전송 계층 |
