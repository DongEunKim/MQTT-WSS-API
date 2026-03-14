# 토픽 패턴·ACL 규격 검토

> WMT/WMO 패턴과 WSS API 서버 동작의 합리성 및 잠재 이슈 검토

---

## 1. 검토 요약

| 항목 | 평가 | 비고 |
|------|------|------|
| 패턴 구조 | ✅ 합리적 | prefix로 요청/응답 구분, vehicle_id ACL 적용 가능 |
| WSS API 동작 | ⚠️ 일부 보완 필요 | 토픽 파싱·검증, 그 외 토픽 정책 등 |
| 확장성 | ✅ 양호 | service 추가 용이 |

---

## 2. 합리적인 점

### 2.1 토픽 구조

- **WMT** (request): 클라이언트 → TGU, ACL 검사 대상
- **WMO** (response): TGU → 클라이언트, `{client_id}` 포함으로 클라이언트 전용 토픽

prefix만으로 PUBLISH/SUBSCRIBE 처리 규칙을 구분할 수 있어 구현이 단순함.

### 2.2 vehicle_id 위치

`WMT/{service}/{vehicle_id}/request`에서 vehicle_id가 세 번째 세그먼트로 고정되어 있어, 파싱이 명확함.

### 2.3 기존 사양과의 정합성

- Envelope, ACK, SUBSCRIPTION, TTL, Subscription Map 등 기존 WSS API 사양과 충돌 없음
- 토픽 문자열만 정의하는 것이므로 payload는 그대로 pass-through

---

## 3. 보완·명확화가 필요한 점

### 3.1 토픽 파싱 규칙

**이슈:** `WMT/RemoteUDS/v001/request`에서 service나 vehicle_id에 `/`가 들어가면 세그먼트 수가 달라져 파싱 오류가 발생함.

**권장:** 사양에 다음을 명시

- `service`, `vehicle_id`는 MQTT 세그먼트 1개로 인식 (추가 `/` 금지)
- `/`, `#`, `+`, NUL 등 특수 문자 금지 (기존 validation과 일치)

### 3.2 토픽 구조 검증

**이슈:** `WMT/a/b/request/extra`처럼 세그먼트가 5개 이상인 경우 처리 기준이 불명확함.

**권장:** 게이트웨이에서 다음 검증

```
WMT: 정확히 4세그먼트 — WMT / {service} / {vehicle_id} / request
WMO: 정확히 5세그먼트 — WMO / {service} / {vehicle_id} / {client_id} / response
```

형식 위반 시 `422` (Unprocessable Entity) 반환.

### 3.3 WMO 구독 ACL

**이슈:** WMO SUBSCRIBE에 대한 vehicle_id ACL이 아직 미정의 상태.

**권장:** WMO 구독에도 WMT와 동일한 vehicle_id ACL 적용

- 이유: client_id로 클라이언트 전용 토픽 분리. 토픽의 client_id가 세션과 불일치 시 거부
- 구독·발행 모두 `vehicle_id` 접근 권한 검사

### 3.4 그 외 토픽 정책

**이슈:** `WMT`, `WMO`가 아닌 토픽(예: `test/command`, `custom/topic`)에 대한 정책이 정의되지 않음.

**권장:** 정책을 명시적으로 선택

| 옵션 | 설명 |
|------|------|
| **A. 화이트리스트** | WMT, WMO만 허용, 그 외는 422 |
| **B. 허용 목록 추가** | 테스트용 `test/*` 등 별도 패턴 정의 |
| **C. 블랙리스트** | WMT/WMO만 ACL 적용, 나머지는 제한적 허용 |

Mock 서버·테스트에서 `test/command`, `test/response`를 사용 중이므로, 개발/테스트 환경용 패턴을 별도로 정의하는 것이 좋음.

### 3.5 service / api 세분화

**이슈:** 기존 TGU 계획은 `{service}/{api}` 형태였으나, 현재 패턴에는 `api` 레벨이 없음.

**현재:** `WMT/{service}/{vehicle_id}/request` — service만 존재

**선택지:**

1. **현행 유지:** service가 RemoteUDS 등 상위 개념, api는 payload로 구분
2. **api 추가:** `WMT/{service}/{api}/{vehicle_id}/request` — 토픽으로 api까지 구분

RPC 호출 시 api별 라우팅이 필요하면 2번이 유리하고, 단순 요청/응답이면 1번으로도 충분함.

### 3.6 Stateless와 세션 vehicle_id

**이슈:** 사양에는 "상태 비저장"이 있으나, ACL을 위해 세션별 vehicle_id 목록을 유지해야 함.

**해석:** Subscription Map, TTL 타이머처럼 **라우팅·인가용 상태**는 사양 상 허용 범위로 보는 것이 자연스러움.  
"비즈니스 데이터를 보관하지 않는다"는 의미로 이해하면 충돌 없음.

---

## 4. system_specification 예시 업데이트

현재 JSON 예시가 구 패턴(`tgu/vehicle_001/...`)을 사용 중:

```json
"topic": "tgu/vehicle_001/RemoteUDS/readDTC/request"
```

새 패턴으로 통일하는 것이 좋음:

```json
"topic": "WMT/RemoteUDS/v001/request"
"topic": "WMO/RemoteUDS/v001/client_A/response"
```

---

## 5. Mock 서버 TGU 시뮬레이션

현재 Mock 서버는 `"/command" in topic`일 때 `/response`로 변환:

```python
if self._simulate_tgu and "/command" in topic:
    response_topic = topic.replace("/command", "/response")
```

WMT/WMO 패턴 적용 시에는 예를 들어 다음과 같이 변경 필요:

```python
if self._simulate_tgu and topic.startswith("WMT/") and topic.endswith("/request"):
    # WMT → WMO, payload에서 client_id 추출하여 토픽 생성
    # response_topic = f"WMO/{service}/{vehicle_id}/{client_id}/response"
```

---

## 6. 권장 조치 요약

| # | 조치 | 상태 |
|---|------|------|
| 1 | TOPIC_AND_ACL_SPEC에 토픽 파싱·검증 규칙 명시 (세그먼트 수, 문자 제한) | ✅ 제안 반영 (섹션 6) |
| 2 | WMO SUBSCRIBE에 vehicle_id ACL 적용 명시 | ✅ 완료 |
| 3 | "그 외 토픽" 정책 선택 (화이트리스트 vs 허용 목록) | 현행 유지 |
| 4 | system_specification JSON 예시를 WMT/WMO로 수정 | ✅ 완료 |
| 5 | service / api 세분화 여부 결정 | 현행 유지 |
| 6 | Mock 서버 TGU 시뮬레이션을 WMT/WMO 기반으로 변경 | 현행 유지 |
