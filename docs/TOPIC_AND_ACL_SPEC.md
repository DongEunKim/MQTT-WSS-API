# 토픽 패턴 및 ACL 규격

> WSS-MQTT API에서 클라이언트가 `action: "PUBLISH"`로 전송할 때, **토픽 prefix**로 요청 유형을 구분하고 필터 규칙을 적용한다.

---

## 1. 배경

클라이언트가 엣지 서버(Machine)에 요청을 보내는 경우나 일반 메시지를 발행하는 경우 모두 `action: "PUBLISH"`로 동작한다.  
토픽 경로를 파싱하여 **어떤 필터를 적용할지** 구분한다.

---

## 2. 세그먼트 정의

| 세그먼트 | 설명 |
|----------|------|
| **service** | 엣지 서버가 제공하는 서비스 식별자 (예: RemoteUDS, VISS) |
| **thing_name** | 엣지 서버의 IoT Thing 이름. 브로커 레벨 라우팅 키 |
| **oem** | 엣지 서버의 소속 조직/제조사. 접근 제어에 사용 |
| **asset** | 장비 식별자 (VIN, 시리얼 번호 등). 접근 제어에 사용 |
| **client_id** | 서비스 요청자 ID. 응답 토픽 격리에 사용 |

> API 서버는 **oem + asset 조합**으로 클라이언트의 접근 권한을 통제한다.

---

## 3. 토픽 패턴

### 3.1 요청 토픽 (WMT — Write/Machine/Topic)

| 항목 | 형식 |
|------|------|
| **토픽 패턴** | `WMT/{service}/{thing_name}/{oem}/{asset}/request` |
| **발행자** | 클라이언트 |
| **구독자** | 엣지 서버 |

### 3.2 응답 토픽 (WMO — Write/Machine/Output)

| 항목 | 형식 |
|------|------|
| **토픽 패턴** | `WMO/{service}/{thing_name}/{oem}/{asset}/{client_id}/response` |
| **발행자** | 엣지 서버 |
| **구독자** | 클라이언트 |

### 3.3 client_id 및 response_topic 전달

- **WMT 요청:** 엣지 서버가 응답할 WMO 토픽을 알 수 있도록 **payload에 `response_topic` 포함** (VISSv2 스타일).  
  예: `{"response_topic": "WMO/RemoteUDS/device_001/acme/VIN123/client_A/response", "request": {...}}`  
- **WMO 구독:** 클라이언트는 `WMO/{service}/{thing_name}/{oem}/{asset}/{자기_client_id}/response` 토픽으로 구독

### 3.4 예시

```
WMT/RemoteUDS/device_001/acme/VIN123/request
    → 클라이언트 A → 엣지 서버
    → payload: {"response_topic": "WMO/RemoteUDS/device_001/acme/VIN123/client_A/response", "request":{...}}

WMO/RemoteUDS/device_001/acme/VIN123/client_A/response
    → 엣지 서버 → 클라이언트 A (client_A 전용 응답)

WMO/RemoteUDS/device_001/acme/VIN123/client_B/response
    → 엣지 서버 → 클라이언트 B (client_B 전용 응답)
```

---

## 4. 엣지 서버 구독 패턴

엣지 서버는 자신의 `thing_name`을 기준으로 WMT 토픽을 구독한다.  
`oem`과 `asset`은 접근 제어 계층(API 서버/게이트웨이)이 처리하므로, 엣지 서버는 와일드카드로 수신한다.

```
WMT/{service}/{thing_name}/+/+/request
```

예: `thing_name = device_001`, 서비스 = RemoteUDS

```
WMT/RemoteUDS/device_001/+/+/request
```

복수 서비스를 처리하는 경우:

```
WMT/+/{thing_name}/+/+/request
```

> **설계 근거:** `thing_name`이 브로커 레벨의 라우팅 키 역할을 한다. 엣지 서버는 자신의 Thing 이름으로 구독하며, `oem`+`asset` 검증은 API 서버/게이트웨이가 담당한다.

---

## 5. 필터(ACL) 규칙

### 5.1 service 조건부 허용

- **적용:** WMT 발행, WMO 구독 모두
- **규칙:** `service`는 사전 약속에 따른 **허용 목록**으로 검사. 미허용 service 시 `422` 반환

### 5.2 WMT 토픽 (발행)

- **대상:** `topic`이 `WMT/`로 시작하는 PUBLISH 요청
- **규칙:** 클라이언트 세션의 `oem`+`asset` 접근 허가가 없으면 발행 거부
- **거부 시:** ACK `403` (Forbidden) 또는 `422` (허용되지 않는 토픽/service)

### 5.3 WMO 토픽 (구독)

- **대상:** `topic`이 `WMO/`로 시작하는 SUBSCRIBE 요청
- **규칙:** ① `oem`+`asset` 접근 허가 ② 토픽의 `client_id`가 해당 세션과 일치 (타 클라이언트 구독 차단)
- **거부 시:** ACK `403` 또는 `422`

### 5.4 그 외 토픽

- WMT, WMO가 아닌 토픽에 대한 정책은 별도 사양에 따른다.
- 옵션: (A) WMT/WMO만 허용(화이트리스트), (B) 테스트용 패턴 추가, (C) 제한적 허용
- 상세 검토: [TOPIC_ACL_REVIEW.md](TOPIC_ACL_REVIEW.md)

---

## 6. 게이트웨이 처리 흐름

### 6.1 PUBLISH

```
PUBLISH 수신 (topic이 WMT/ 로 시작)
    │
    ├─ service 허용? (사전 약속) → No → ACK 422
    ├─ oem+asset 접근 허가? → No → ACK 403
    └─ Yes → MQTT 발행
```

### 6.2 SUBSCRIBE (WMO)

```
SUBSCRIBE 수신 (topic이 WMO/ 로 시작)
    │
    ├─ service 허용? (사전 약속) → No → ACK 422
    ├─ oem+asset 접근 허가? → No → ACK 403
    ├─ topic의 client_id == 세션 client_id? → No → ACK 403
    └─ Yes → Subscription Map 등록
```

---

## 7. JWT·세션과 매핑

- 연결 시 JWT에서 **client_id** (또는 `sub` 등) 및 **접근 가능 oem+asset 목록** 추출
- API 게이트웨이 메모리(또는 인가 서비스)에 세션별 (client_id, {oem+asset} 집합) 유지
- **service 허용 목록:** 사전 약속에 따른 허용 service 집합 (조건부 검사)
- **WMT 발행 시:** service 검사 → oem+asset 접근 허가 검사
- **WMO 구독 시:** service 검사 → oem+asset 허가 → client_id 일치 검사

---

## 8. 토픽 파싱·검증 규칙 (게이트웨이 구현 가이드)

### 8.1 세그먼트 구조 검증

| 패턴 | 세그먼트 수 | 형식 |
|------|-------------|------|
| WMT | 6 | `WMT / {service} / {thing_name} / {oem} / {asset} / request` |
| WMO | 7 | `WMO / {service} / {thing_name} / {oem} / {asset} / {client_id} / response` |

**검증 순서:** 1) prefix 확인 → 2) `/` 기준 split → 3) 세그먼트 수 확인 (WMT=6, WMO=7) → 4) 마지막 세그먼트가 `request` 또는 `response` 확인

**위반 시:** ACK `422`, payload 예: `{"message": "Topic format invalid for WMT/WMO"}`

### 8.2 문자 제한

| 항목 | 제한 |
|------|------|
| `service`, `thing_name`, `oem`, `asset`, `client_id` | 단일 MQTT 세그먼트. `/` 포함 금지 |
| 전체 토픽 | `+`, `#`, `\x00`(NUL) 사용 불가 |
| 빈 세그먼트 | 빈 값 → 422 |

### 8.3 검증 실패 시 코드

| 사유 | ACK code |
|------|----------|
| 세그먼트 수 불일치, 마지막 세그먼트 오류 | 422 |
| service 미허용 (조건부 허용 정책) | 422 |
| oem+asset ACL 미통과 | 403 |
| WMO 구독 시 client_id 불일치 | 403 |
