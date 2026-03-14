# RPC 전송 계층 설계 — VISSv2 참조 및 TGU 관점

> **배경**  
> - MQTT/WSS는 RPC를 구현하기 위한 **중간 전송 계층 래퍼**이다.  
> - TGU 입장에서는 payload만 파싱해 응답 위치를 알 수 있어야 한다.  
> - VISSv3는 이 RPC 설계가 포함하는 **서비스 중 하나**이며, MQTT·WSS로 래핑된다.

---

## 1. 계층 구조

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  서비스 레이어 (예: VISSv3, RemoteUDS, RemoteDashboard)                        │
│  - action, path, filter, data, error 등 서비스별 payload                        │
├─────────────────────────────────────────────────────────────────────────────┤
│  RPC 전송 래퍼 (본 문서 설계 대상)                                              │
│  - request_id, response_topic, request(서비스 payload)                          │
│  - TGU는 이 레이어만 이해하면 응답 위치를 명시적으로 알 수 있음                      │
├─────────────────────────────────────────────────────────────────────────────┤
│  MQTT                                                                        │
│  - publish(topic, payload), subscribe(topic)                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│  WSS (선택)                                                                   │
│  - wss-mqtt-api: MQTT를 WebSocket JSON Envelope으로 래핑                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. VISSv2 MQTT RPC 패턴 (참조: W3C VISSv2 Transport)

VISSv2 Transport 사양의 MQTT 섹션 핵심 내용:

### 2.1 요청 형식

- **요청 토픽**: `VID/Vehicle` (VID = vehicle identity)
- **요청 payload**:

```json
{
  "topic": "aUniqueTopic",
  "request": "<VISSv2Request>"
}
```

- `topic`: 클라이언트가 **미리 구독한** 고유 토픽. 응답 수신용.
- `request`: WebSocket 챕터와 동일한 VISSv2 요청 (action, path, requestId 등)

### 2.2 TGU(vehicle client) 동작

1. `VID/Vehicle` 구독
2. 수신 payload에서 `topic`(응답 토픽), `request`(서비스 요청) 추출
3. vehicle server에 `request` 전달
4. 응답 수신 시 **`topic`에 그대로 발행**
5. **토픽 패턴을 알 필요 없음** — payload에 응답 위치가 명시됨

### 2.3 핵심 원칙

> **응답 위치는 payload의 `topic` 필드로 명시된다.**  
> TGU는 "어디로 보낼지"를 payload에서만 읽어 처리한다.

---

## 3. 본 설계: TGU 관점의 RPC 전송 래퍼

### 3.1 설계 원칙

| 원칙 | 설명 |
|------|------|
| **payload에 응답 토픽 명시** | TGU가 토픽 패턴을 알 필요 없이 `response_topic`만 사용 |
| **서비스 payload 분리** | `request`(또는 `payload`)에 서비스별 내용. VISSv3, RemoteUDS 등 다양한 서비스 수용 |
| **상관관계** | `request_id`로 요청-응답 매칭 (클라이언트 구독 토픽에 여러 응답이 올 수 있음) |

### 3.2 요청 Payload (RPC 전송 래퍼)

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
| request_id | Y | 요청-응답 매칭. 클라이언트 생성 |
| response_topic | Y | **TGU가 응답을 발행할 토픽. 클라이언트가 명시.** |
| request | Y | 서비스별 요청 (action, path, params 등). 서비스 명세 따름 |

### 3.3 TGU 처리 흐름

```
1. WMT/{service}/{vehicle_id}/request 구독 (또는 통합 요청 토픽)
2. payload 수신
3. response_topic ← payload.response_topic   ← 명시적
4. request      ← payload.request
5. 서비스 로직 실행 (action, params 기반)
6. PUBLISH payload.response_topic { request_id, result | error }
```

**TGU는 `response_topic`을 그대로 사용한다. 토픽 규칙(WMO, client_id 등)을 알 필요 없다.**

### 3.4 응답 Payload

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

---

## 4. VISSv3 서비스 통합

VISSv3는 **서비스 레이어**이다. RPC 전송 래퍼의 `request` 안에 VISSv2 스타일 payload가 들어간다.

### 4.1 예: VISSv3 get 요청 (MQTT 래핑)

```json
{
  "request_id": "req-8756",
  "response_topic": "WMO/VISS/v001/client_xyz/response",
  "request": {
    "action": "get",
    "path": "Vehicle.Drivetrain.InternalCombustionEngine.RPM",
    "filter": null
  }
}
```

### 4.2 TGU(VISSv3 서버) 처리

1. `response_topic` 추출 → 응답 발행 위치
2. `request` → VISSv3 Core 로직에 전달
3. VISSv3 응답 형식으로 `result` 생성
4. `PUBLISH response_topic { request_id, data, ts }` (또는 error)

### 4.3 요청 토픽과 서비스 매핑

| 서비스 | 요청 토픽 예 | request 형식 |
|--------|--------------|--------------|
| VISSv3 | `WMT/VISS/{vehicle_id}/request` | VISSv2 Core (action, path, filter 등) |
| RemoteUDS | `WMT/RemoteUDS/{vehicle_id}/request` | action, params |
| RemoteDashboard | `WMT/RemoteDashboard/{vehicle_id}/request` | action, params |

TGU는 **구독한 토픽의 service 세그먼트**로 어떤 서비스 핸들러를 쓸지 결정할 수 있다.  
또는 `request` 내 `action`/서비스 식별자로 라우팅할 수도 있다.

---

## 5. client_id vs response_topic

### 5.1 기존 설계 (client_id 기반)

- 요청: `client_id` 포함
- 응답 토픽: `WMO/{service}/{vehicle_id}/{client_id}/response` — **TGU가 패턴으로 생성**
- TGU는 service, vehicle_id(토픽에서), client_id(payload)를 알아야 함

### 5.2 VISSv2 스타일 (response_topic 명시)

- 요청: `response_topic` 포함
- TGU는 **payload.response_topic에 그대로 발행**
- 토픽 규칙을 TGU가 알 필요 없음. 클라이언트/SDK가 전적으로 결정.

### 5.3 권장: response_topic 명시

| 항목 | 장점 |
|------|------|
| TGU 단순화 | 토픽 패턴 파싱 불필요. payload만 읽으면 됨 |
| VISSv2 정렬 | 표준 사례와 일치 |
| 유연성 | 클라이언트가 응답 토픽을 자유롭게 구성 (ACL 범위 내) |
| 다중 전송 | 이론상 다른 프로토콜로 전환 시에도 response_topic 같은 개념 재사용 가능 |

**client_id**는 `response_topic`을 만들 때 SDK가 사용한다.  
예: `WMO/{service}/{vehicle_id}/{client_id}/response` — SDK가 생성 후 `response_topic`으로 payload에 넣음.

---

## 6. 정리

| 항목 | 내용 |
|------|------|
| **전송 래퍼** | MQTT/WSS payload는 RPC를 위한 중간 계층. 서비스(VISSv3 등)는 `request` 안에 위치 |
| **response_topic** | payload에 명시. TGU가 "어디로 응답할지"를 여기서만 읽음 |
| **request** | 서비스별 payload. VISSv3, RemoteUDS 등 각 서비스 명세 따름 |
| **VISSv3** | 이 RPC 설계가 담는 서비스 중 하나. `request`에 VISSv2 Core 형식 사용 |
| **TGU** | response_topic 추출 → request 처리 → response_topic에 응답 발행. 토픽 규칙 불필요 |

---

## 7. 참조

- [VISSv2 Transport (W3C)](https://w3c.github.io/automotive/spec/VISSv2_Transport.html) — MQTT Application Level Protocol
- `docs/MQTT_RPC_METHODOLOGY.md` — 기존 토픽·상관관계 설계
- `docs/TOPIC_AND_ACL_SPEC.md` — WMT/WMO 토픽 및 ACL
