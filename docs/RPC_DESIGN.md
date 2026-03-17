# RPC 설계 — MQTT 방법론 및 전송 계층

> 클라이언트 ↔ 엣지 서버(Machine) 간 RPC는 **MQTT 패턴**(토픽 분리 + payload 상관관계)으로 구현한다.  
> WSS-MQTT API는 MQTT를 WebSocket Envelope으로 래핑할 뿐, RPC 패턴은 동일하다.

---

## 1. 계층 구조

```
┌─────────────────────────────────────────────────────────────────┐
│  서비스 레이어 (VISSv3, RemoteUDS, RemoteDashboard)              │
│  - action, path, params, result, error 등 서비스별 payload        │
├─────────────────────────────────────────────────────────────────┤
│  RPC 전송 래퍼                                                    │
│  - request_id, response_topic, request(서비스 payload)            │
│  - 엣지 서버는 payload만으로 응답 위치를 명시적으로 알 수 있음      │
├─────────────────────────────────────────────────────────────────┤
│  MQTT — publish(topic, payload), subscribe(topic)                 │
├─────────────────────────────────────────────────────────────────┤
│  WSS (선택) — wss-mqtt-api: MQTT를 WebSocket JSON Envelope 래핑   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. MQTT 비동기 특성

- `publish(topic, payload)` → 즉시 반환. 수신자를 기다리지 않음.
- 응답을 받으려면 **별도 토픽을 구독**하고, 상대가 그 토픽에 발행해야 함.

따라서 RPC는 **요청 토픽 + 응답 토픽 + payload 상관관계(request_id, response_topic)** 로 구현한다.

---

## 3. 토픽 역할

| 구분 | 토픽 | 발행자 | 구독자 |
|------|------|--------|--------|
| **Request** | `WMT/{service}/{thing_name}/{oem}/{asset}/request` | 클라이언트 | 엣지 서버 |
| **Response** | `WMO/{service}/{thing_name}/{oem}/{asset}/{client_id}/response` | 엣지 서버 | 클라이언트 |

- 클라이언트가 **응답 수신 토픽(response_topic)** 을 payload에 명시. 엣지 서버는 그 토픽에 그대로 발행 (VISSv2 MQTT 패턴).
- 엣지 서버는 `thing_name` 기반으로 구독 (`WMT/+/{thing_name}/+/+/request`).
- `oem`+`asset`은 API 게이트웨이 레벨에서 접근 제어에 사용.
- 상세 토픽·ACL: `docs/TOPIC_AND_ACL_SPEC.md`

---

## 4. Payload

### 4.1 요청 (클라이언트 → 엣지 서버)

```json
{
  "request_id": "req-550e8400-e29b",
  "response_topic": "WMO/RemoteUDS/device_001/acme/VIN123/client_A/response",
  "request": {
    "action": "readDTC",
    "params": { "source": 1 }
  }
}
```

| 필드 | 필수 | 설명 |
|------|------|------|
| request_id | Y | 요청-응답 매칭용 |
| response_topic | Y | 엣지 서버가 응답을 발행할 토픽. 클라이언트가 명시 |
| request | Y | 서비스별 요청 (action, params 등) |

### 4.2 응답 (엣지 서버 → 클라이언트)

성공: `{ "request_id": "...", "result": { ... }, "error": null }`  
실패: `{ "request_id": "...", "result": null, "error": { "code": "...", "message": "..." } }`

---

## 5. 시퀀스

1. 클라이언트: 응답 토픽 구독 (`WMO/…/{client_id}/response`)
2. 클라이언트: 요청 토픽에 payload 발행 (`WMT/…/request`)
3. 엣지 서버: 요청 수신 → `response_topic`, `request` 추출 → 처리 → **response_topic**에 응답 발행
4. 클라이언트: 구독 토픽에서 `request_id` 일치 메시지 수신

엣지 서버는 토픽 규칙을 알 필요 없이 **payload.response_topic**만 사용한다.

---

## 6. 참조

- VISSv2 Transport (W3C) — MQTT RPC 패턴 참조
- `docs/TOPIC_AND_ACL_SPEC.md` — WMT/WMO 토픽 및 ACL
- `docs/system_specification_v1.md` — WSS-MQTT API 사양
