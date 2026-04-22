# 토픽 구조 및 ACL 규격

> MQTT 5.0 기반 MaaS RPC 통신에서 사용되는 토픽 패턴과 접근 제어 규칙을 정의한다.

---

## 1. 토픽 구조

모든 RPC 통신은 아래 구조를 따른다.

```
{WMT|WMO}/{ThingType}/{Service}/{VIN}/{ClientId}/{request|response|event}
```

### 세그먼트 정의

| 세그먼트 | 설명 | 예시 |
|----------|------|------|
| `WMT` | Write Machine To — 클라이언트 → 서비스 방향 | |
| `WMO` | Write Machine Out — 서비스 → 클라이언트 방향 | |
| `{ThingType}` | 사물의 타입 분류. 특정 인스턴스 ID가 아닌 **타입** 식별자 | `CGU`, `SDM` |
| `{Service}` | ThingType 위에서 동작하는 서비스 이름 | `viss`, `diagnostics`, `control` |
| `{VIN}` | 대상 장비 식별자 (Vehicle Identification Number) | `VIN-123456` |
| `{ClientId}` | 응답 라우팅용 클라이언트 식별자. 고유 UUID 권장 | `webapp-uuid-abc` |
| `request` | 요청 메시지 | |
| `response` | 단일 응답 또는 스트림 완료 신호 | |
| `event` | 스트리밍 청크 (패턴 C) | |

> **핵심 원칙:** 클라이언트는 ThingType + Service + VIN만 알면 된다.  
> 서비스가 실행되는 특정 Thing 인스턴스 ID는 노출되지 않는다.

---

## 2. 토픽 패턴별 용도

### 2.1 요청 (WMT)

| 항목 | 형식 |
|------|------|
| 패턴 | `WMT/{ThingType}/{Service}/{VIN}/{ClientId}/request` |
| 발행자 | 클라이언트 |
| 구독자 | 서비스 (ThingType, Service, VIN 고정, ClientId 와일드카드) |
| 예시 | `WMT/CGU/viss/VIN-123456/webapp-abc/request` |

### 2.2 응답 (WMO/response)

| 항목 | 형식 |
|------|------|
| 패턴 | `WMO/{ThingType}/{Service}/{VIN}/{ClientId}/response` |
| 발행자 | 서비스 |
| 구독자 | 클라이언트 (자신의 ClientId 고정) |
| 용도 | 단일 RPC 응답 또는 스트리밍 완료 신호 |

### 2.3 이벤트 (WMO/event)

| 항목 | 형식 |
|------|------|
| 패턴 | `WMO/{ThingType}/{Service}/{VIN}/{ClientId}/event` |
| 발행자 | 서비스 |
| 구독자 | 클라이언트 (자신의 ClientId 고정) |
| 용도 | 스트리밍 청크 (패턴 C). response 수신 전까지 연속 발행 |

---

## 3. 서비스 구독 패턴

서비스는 자신의 ThingType, Service 이름, VIN을 기반으로 구독한다.  
ClientId는 와일드카드(`+`)로 수신하여 모든 클라이언트의 요청을 처리한다.

```
WMT/{ThingType}/{Service}/{VIN}/+/request
```

예시 (CGU의 viss 서비스, VIN-123456 담당):
```
WMT/CGU/viss/VIN-123456/+/request
```

---

## 4. 클라이언트 구독 패턴

클라이언트는 자신의 ClientId를 포함한 응답/이벤트 토픽을 구독한다.  
ThingType, Service, VIN은 와일드카드로 처리하여 모든 서비스로부터의 응답을 수신한다.

```
WMO/+/+/+/{ClientId}/response
WMO/+/+/+/{ClientId}/event
```

> SDK는 연결 시 위 와일드카드 구독을 자동으로 등록하고,  
> `Correlation Data`로 요청-응답을 매핑한다.

---

## 5. 요청 페이로드 (애플리케이션 계약)

JSON 페이로드(권장)에서 다음 필드를 사용한다.

| 필드 | 필수 | 설명 |
|------|------|------|
| `action` | 예 | 실행할 애플리케이션 액션. 서버 SDK의 `@server.action("<이름>")` 과 매칭 |

`action` 외 필드는 서비스별 계약으로 자유롭게 정의한다. 서로 다른 서비스는 토픽의 `{Service}` 로 구분한다.

> **서버 SDK (`maas-server-sdk`) 라우팅:** 규격상 권장 필드명은 `action` 이다. 구현에서는 `MaasServer(..., route_key="action")`(기본값)으로 페이로드에서 라우팅에 쓸 **JSON 키**를 바꿀 수 있다(예: `method`, `op`). `route_key=None` 이면 `@server.action` 은 사용하지 않고 `@server.default` 하나만 등록하며, 이때는 라우팅용 필드를 페이로드에서 제거하지 않고 본문 전체를 핸들러에 넘긴다. 자세한 설명은 [SDK 설계요구사양서](SDK%20설계요구사양서.md) Part 1, `SDK/server/python/maas-server-sdk/README.md` 참고.

---

## 6. MQTT 5.0 Properties 사용 규약

RPC 통신에서 MQTT 5.0 Properties를 다음과 같이 활용한다.

| Property | 사용 위치 | 용도 |
|----------|-----------|------|
| `Response Topic` | 요청 PUBLISH | 서비스가 응답할 WMO 토픽. SDK가 자동 삽입 |
| `Correlation Data` | 요청/응답 PUBLISH | 요청-응답 매핑용 UUID bytes. SDK가 자동 처리 |
| `Message Expiry Interval` | 요청 PUBLISH | 패턴 D(시한성 명령)에서 브로커 레벨 메시지 만료 |
| `User Property: reason_code` | 응답 PUBLISH | 처리 결과 코드 (0=성공, 0x80 이상=오류) |
| `User Property: error_detail` | 응답 PUBLISH | 오류 상세 메시지 (오류 시만 포함) |
| `User Property: is_EOF` | 응답 PUBLISH | `"true"` — 스트리밍 완료 신호 |

### 6.1 요청 JSON 예시

```json
{
  "action": "get",
  "path": "Vehicle.Speed"
}
```

### 6.2 응답 페이로드

응답 페이로드 구조는 서비스가 자유롭게 정의한다.  
성공/실패 여부는 페이로드가 아닌 `User Property: reason_code`로 판단한다.

---

## 7. Reason Code 표준

서비스는 응답 시 User Property `reason_code`로 결과를 반환한다.

| 코드 | 의미 |
|------|------|
| `0` (0x00) | 성공 |
| `128` (0x80) | 알 수 없는 서버/하드웨어 오류 |
| `131` (0x83) | 비즈니스 로직 오류 (장비가 현재 수행 불가) |
| `135` (0x87) | 권한 없음 |
| `138` (0x8A) | 독점 세션 점유 중 (Server Busy) |
| `144` (0x90) | 지원하지 않는 action |
| `153` (0x99) | 페이로드 형식 오류 |

---

## 8. ACL 규칙

### 8.1 클라이언트 발행 (WMT)

- 클라이언트는 자신의 ClientId가 포함된 WMT 토픽에만 발행 가능
- VIN 접근 권한은 인증 토큰(JWT) 기반으로 브로커/인가 서비스에서 검증

### 8.2 클라이언트 구독 (WMO)

- 클라이언트는 자신의 ClientId가 포함된 WMO 토픽만 구독 가능
- 타 클라이언트의 응답 토픽 구독 차단

### 8.3 서비스 구독 (WMT)

- 서비스는 자신의 ThingType + Service + VIN 범위의 WMT 토픽만 구독 가능

---

## 9. 토픽 흐름 예시

```
[Client: webapp-abc]
PUBLISH  WMT/CGU/viss/VIN-123456/webapp-abc/request
  payload: {"action": "get", "path": "Vehicle.Speed"}
  MQTT5:   Response-Topic = WMO/CGU/viss/VIN-123456/webapp-abc/response
           Correlation-Data = <UUID-1>

[CGU viss Service, VIN-123456]
구독 중:  WMT/CGU/viss/VIN-123456/+/request
  → 수신 → action="get" → 핸들러 호출
PUBLISH  WMO/CGU/viss/VIN-123456/webapp-abc/response
  payload: {"value": 120.5}
  MQTT5:   Correlation-Data = <UUID-1>
           User-Property: reason_code=0

[Client: webapp-abc]
  → Correlation-Data 매핑 → Future resolved
  → result.payload = {"value": 120.5}
```
