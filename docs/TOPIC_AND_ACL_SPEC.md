# 토픽 패턴 및 ACL 규격

> WSS-MQTT API에서 클라이언트가 `action: "PUBLISH"`로 전송할 때, **토픽 prefix**로 요청 유형을 구분하고 필터 규칙을 적용한다.

---

## 1. 배경

클라이언트가 TGU에 요청을 보내는 경우나 일반 메시지를 발행하는 경우 모두 `action: "PUBLISH"`로 동작한다.  
토픽 경로를 파싱하여 **어떤 필터를 적용할지** 구분한다.

---

## 2. 토픽 패턴 및 세그먼트 의미

### 2.1 발행 요청 (WMT)

| 항목 | 형식 | 설명 |
|------|------|------|
| **토픽 패턴** | `WMT/{service}/{vehicle_id}/request` | 클라이언트 → TGU 요청 |
| **service** | TGU가 제공하는 서비스. API는 **조건부 허용** (사전 약속) |
| **vehicle_id** | 클라이언트가 접근이 허용된 대상 ID. 권한 없으면 발행 요청 거부 |

### 2.2 구독 요청 (WMO)

| 항목 | 형식 | 설명 |
|------|------|------|
| **토픽 패턴** | `WMO/{service}/{vehicle_id}/{client_id}/response` | TGU → 클라이언트 응답 수신 |
| **service** | TGU가 제공하는 서비스. API는 **조건부 허용** (사전 약속) |
| **vehicle_id** | 클라이언트가 접근이 허용된 대상 ID. 권한 없으면 구독 요청 거부 |
| **client_id** | 클라이언트가 설정. 다른 클라이언트가 구독하지 못하도록 분리. API는 **로깅에 사용** |

### 2.3 client_id 및 response_topic 전달

- **WMT 요청:** TGU가 응답할 WMO 토픽을 알 수 있도록 **payload에 `response_topic` 포함** (VISSv2 스타일).  
  예: `{"response_topic": "WMO/RemoteUDS/v001/client_A/response", "request": {...}}`  
  - `response_topic` = `WMO/{service}/{vehicle_id}/{client_id}/response` 형식. 상세: `docs/RPC_TRANSPORT_LAYER_DESIGN.md`
- **WMO 구독:** 클라이언트는 `WMO/{service}/{vehicle_id}/{자기_client_id}/response` 토픽으로 구독

### 2.4 예시

```
WMT/RemoteUDS/v001/request              → 클라이언트 A → TGU (payload: {"response_topic":"WMO/.../client_A/response", "request":{...}})
WMO/RemoteUDS/v001/client_A/response    → TGU → 클라이언트 A (client_A 전용 응답)
WMO/RemoteUDS/v001/client_B/response    → TGU → 클라이언트 B (client_B 전용 응답)
```

---

## 3. 필터(ACL) 규칙

### 3.1 service 조건부 허용

- **적용:** WMT 발행, WMO 구독 모두
- **규칙:** `service`는 사전 약속에 따른 **허용 목록**으로 검사 가능. 미허용 service 시 `422` 반환

### 3.2 WMT 토픽 (발행)

- **대상:** `topic`이 `WMT/`로 시작하는 PUBLISH 요청
- **규칙:** WSS로 연결된 클라이언트가 대상 `vehicle_id`에 대한 **접근 허가**가 없으면 발행 거부
- **거부 시:** ACK `403` (Forbidden) 또는 `422` (허용되지 않는 토픽/service)

### 3.3 WMO 토픽 (구독)

- **대상:** `topic`이 `WMO/`로 시작하는 SUBSCRIBE 요청
- **규칙:** ① vehicle_id 접근 허가 ② 토픽의 `client_id`가 해당 세션과 일치 (다른 클라이언트 구독 차단)
- **거부 시:** ACK `403` 또는 `422`

### 3.4 그 외 토픽

- WMT, WMO가 아닌 토픽에 대한 정책은 별도 사양에 따른다.
- 옵션: (A) WMT/WMO만 허용(화이트리스트), (B) 테스트용 패턴 추가, (C) 제한적 허용
- 상세 검토: [TOPIC_ACL_REVIEW.md](TOPIC_ACL_REVIEW.md)

---

## 4. 게이트웨이 처리 흐름

### 4.1 PUBLISH

```
PUBLISH 수신 (topic이 WMT/ 로 시작)
    │
    ├─ service 허용? (사전 약속) → No → ACK 422
    ├─ vehicle_id 접근 허가? → No → ACK 403
    └─ Yes → MQTT 발행
```

### 4.2 SUBSCRIBE (WMO)

```
SUBSCRIBE 수신 (topic이 WMO/ 로 시작)
    │
    ├─ service 허용? (사전 약속) → No → ACK 422
    ├─ vehicle_id 접근 허가? → No → ACK 403
    ├─ topic의 client_id == 세션 client_id? → No → ACK 403
    └─ Yes → Subscription Map 등록
```

---

## 5. JWT·세션과 매핑

- 연결 시 JWT에서 **client_id** (또는 `sub` 등) 및 **접근 가능 vehicle_id 목록** 추출
- API 게이트웨이 메모리(또는 인가 서비스)에 세션별 (client_id, vehicle_id 집합) 유지
- **service 허용 목록:** 사전 약속에 따른 허용 service 집합 (조건부 검사)
- **WMT 발행 시:** service 검사 → vehicle_id 접근 허가 검사
- **WMO 구독 시:** service 검사 → vehicle_id 허가 → client_id 일치 검사. client_id는 **로깅에 활용**

---

## 6. 토픽 파싱·검증 규칙 (게이트웨이 구현 가이드)

### 6.1 세그먼트 구조 검증

| 패턴 | 세그먼트 수 | 형식 | vehicle_id | client_id |
|------|-------------|------|------------|-----------|
| WMT | 4 | `WMT / {service} / {vehicle_id} / request` | index 2 | - |
| WMO | 5 | `WMO / {service} / {vehicle_id} / {client_id} / response` | index 2 | index 3 |

**검증 순서:** 1) prefix 확인 → 2) `/` 기준 split → 3) 세그먼트 수 확인 (WMT=4, WMO=5) → 4) 마지막 세그먼트가 `request` 또는 `response` 확인

**위반 시:** ACK `422` (Unprocessable Entity), payload 예: `{"message": "Topic format invalid for WMT/WMO"}`

### 6.2 문자 제한

| 항목 | 제한 |
|------|------|
| `service`, `vehicle_id`, `client_id` | 단일 MQTT 세그먼트. `/` 포함 금지 |
| 전체 토픽 | `+`, `#`, `\x00`(NUL) 사용 불가 |
| 빈 세그먼트 | 빈 service/vehicle_id/client_id → 422 |

### 6.3 검증 실패 시 코드

| 사유 | ACK code |
|------|----------|
| 세그먼트 수 불일치, 마지막 세그먼트 오류 | 422 |
| service 미허용 (조건부 허용 정책) | 422 |
| vehicle_id ACL 미통과 | 403 |
| WMO 구독 시 client_id 불일치 | 403 |
