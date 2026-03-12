# TGU RPC SDK 개발 계획서

> **문서 목적**  
> TGU(Telematics Gateway Unit)의 서비스/API 명세만으로 RPC를 쉽게 구현할 수 있는 통합 SDK를 개발하기 위한 계획을 정리한다.  
> 기존 `wss-mqtt-client` SDK를 포함·재활용하며, 표준화된 토픽·페이로드 패턴을 제공한다.

---

## 1. 프로젝트 개요

### 1.1. 배경

- TGU는 MQTT 브로커에 연결되어 클라이언트와 RPC를 수행한다.
- 클라이언트는 MQTT over WSS가 아닌 **wss-mqtt-api**를 통해 연결한다.
- VISSv3의 MQTT 전송 프로토콜 사례와 유사한 구조를 갖는다.
- 현재 클라이언트는 토픽 경로, 구독/발행 순서 등을 직접 처리해야 하며 개발 부담이 크다.

### 1.2. 목표

- **서비스·API 명세만 알면 RPC를 쉽게 구현할 수 있는 SDK** 제공
- 기존 `wss-mqtt-client`를 재활용·포함한 **통합 SDK** 구성
- 기본 pub/sub 기능도 클라이언트가 계속 사용할 수 있도록 유지
- 표준화된 토픽 패턴과 페이로드 스키마를 적용

### 1.3. 적용 대상

| 구분 | 내용 |
|------|------|
| **후보 서비스** | Remote UDS, Remote Dashboard |
| **API 패턴** | Request & Response RPC, VISSv3 스타일 구독(주기/이벤트 발행) |
| **클라이언트 환경** | Python (우선), 추후 다른 언어 확장 고려 |

---

## 2. 아키텍처

### 2.1. 레이어 구조

```
┌─────────────────────────────────────────────────────────────────┐
│  TGU RPC SDK (tgu-rpc-sdk)                                       │
│  - call(service, api, payload)        : RPC 호출                   │
│  - subscribe_stream(service, api)     : 구독형 API                 │
│  - publish / subscribe (기본 pub/sub 노출)                         │
├─────────────────────────────────────────────────────────────────┤
│  wss-mqtt-client (의존성, 재사용)                                   │
│  - WssMqttClient: publish, subscribe, transport                   │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
   wss-mqtt-api (게이트웨이)
         │
         ▼
   MQTT Broker ←→ TGU
```

### 2.2. 패키지 구조 (예시)

```
tgu-rpc-sdk/
├── tgu_rpc/
│   ├── __init__.py
│   ├── client.py          # TguRpcClient (WssMqttClient 래핑)
│   ├── spec.py            # 서비스/API → 토픽/스키마 매핑
│   ├── topics.py          # 토픽 패턴 생성 유틸
│   └── exceptions.py      # TGU 전용 예외 (선택)
├── pyproject.toml         # dependencies: wss-mqtt-client
├── README.md
└── examples/
    ├── rpc_call.py
    └── subscribe_stream.py
```

### 2.3. 기본 pub/sub 유지

- `TguRpcClient`가 내부 `WssMqttClient` 참조를 노출 (예: `raw_client`)
- 또는 `publish`, `subscribe` 메서드를 그대로 위임
- 필요 시 토픽 필터 정책에 따라 정형화된 토픽만 허용하도록 선택 가능

---

## 3. 개발 범위

### 3.1. 포함 범위

| 항목 | 설명 |
|------|------|
| TguRpcClient 클래스 | URL, token, vehicle_id(또는 식별자) 초기화 |
| call(service, api, payload) | Request & Response RPC, 내부에서 토픽 생성·구독·발행·응답 수신 |
| subscribe_stream(service, api) | VISSv3 스타일 구독, 장기 스트림 반환 |
| 기본 pub/sub 노출 | publish, subscribe 메서드 또는 raw_client 참조 |
| 서비스/API 명세 기반 토픽 생성 | 표준 토픽 패턴 적용 |
| 타임아웃·에러 처리 | wss-mqtt-client 예외 활용 및 필요 시 래핑 |

### 3.2. 제외 범위 (본 단계)

| 항목 | 비고 |
|------|------|
| 페이로드 스키마 검증 | 선택 사항, 추후 확장 |
| 다국어 지원 | 문서·주석 한글 우선 |
| Python 외 언어 SDK | 별도 프로젝트로 검토 |

---

## 4. 개발 단계

### Phase 1: 토픽·명세 정의 (사전 작업)

- [ ] 토픽 패턴 규칙 확정 (예: `tgu/{vehicle_id}/{service}/{api}/request`, `.../response`, `.../data`)
- [ ] Remote UDS, Remote Dashboard의 API 목록 및 각 API의 request/response 페이로드 스키마 확정
- [ ] wss-mqtt-api에서의 Request 토픽 필터(ACL) 규칙 확정

### Phase 2: SDK 골격 및 기본 RPC

- [ ] 프로젝트 셋업 (pyproject.toml, tgu_rpc 패키지)
- [ ] `wss-mqtt-client` 의존성 추가 및 임포트 검증
- [ ] 토픽 생성 유틸 구현 (`topics.py`)
- [ ] 서비스/API 명세 매핑 모듈 (`spec.py`)
- [ ] `TguRpcClient` 클래스 구현, `call()` 메서드

### Phase 3: 구독형 API 및 기본 pub/sub

- [ ] `subscribe_stream()` 메서드 구현
- [ ] 기본 pub/sub 메서드 노출 (publish, subscribe 또는 raw_client)
- [ ] 예제 코드 작성 (rpc_call, subscribe_stream)

### Phase 4: 문서화 및 테스트

- [ ] README, 사용법, API 레퍼런스
- [ ] 단위 테스트 (mock 기반)
- [ ] 통합 테스트 (실 서버 연동 시 선택)

---

## 5. 사용 시나리오 (목표 UX)

### 5.1. RPC 호출

```python
from tgu_rpc import TguRpcClient

async with TguRpcClient(
    url="wss://api.example.com/v1/messaging",
    token="jwt",
    vehicle_id="vehicle_001",
) as client:
    result = await client.call("RemoteUDS", "readDTC", {"source": 0x01})
```

### 5.2. 구독형 API (VISSv3 스타일)

```python
async with client.subscribe_stream("RemoteDashboard", "vehicleSpeed") as stream:
    async for event in stream:
        print(event.payload)
```

### 5.3. 기본 pub/sub

```python
# raw_client를 통한 저수준 제어
await client.raw_client.publish("custom/topic", payload)
async with client.raw_client.subscribe("custom/response") as s:
    async for event in s:
        ...
```

---

## 6. 의존성 및 제약

### 6.1. 의존성

- Python 3.8+
- wss-mqtt-client (기존 SDK)
- websockets (wss-mqtt-client 전이 의존성)

### 6.2. 참조 문서

- `docs/system_specification_v1.md` — wss-mqtt-api 사양
- `docs/wss-mqtt-message-schema.json` — 메시지 Envelope 스키마

---

## 7. 리스크 및 대응

| 리스크 | 대응 |
|--------|------|
| 토픽 패턴·명세 미확정 | Phase 1을 우선 진행하고, 확정 후 SDK 반영 |
| wss-mqtt-api ACL 미정의 | 토픽 패턴을 유연하게 설계하여 ACL 추가 시 매핑만 수정 |
| 서비스/API 추가 시 스키마 변경 | spec.py를 확장 가능하게 설계, 파일 또는 코드 기반 명세 |

---

## 8. 추가로 제공이 필요한 정보

개발을 진행하기 위해 아래 정보가 필요합니다.

### 8.1. 토픽 패턴 (필수)

| 항목 | 설명 | 예시 |
|------|------|------|
| **요청 토픽 패턴** | 클라이언트가 PUBLISH하는 토픽 형식 | `tgu/{vehicle_id}/{service}/{api}/request` |
| **응답 토픽 패턴** | RPC 응답 수신용 SUBSCRIBE 토픽 | `tgu/{vehicle_id}/{service}/{api}/response` |
| **구독형 데이터 토픽** | VISSv3 스타일 이벤트/주기 발행 토픽 | `tgu/{vehicle_id}/{service}/{api}/data` |
| **vehicle_id 대체** | 차량 식별자 외 다른 식별자 사용 여부 (예: device_id, session_id) | - |

### 8.2. 서비스·API 명세 (필수)

| 서비스 | API 목록 | 각 API의 Request/Response 스키마 |
|--------|----------|----------------------------------|
| **Remote UDS** | readDTC, clearDTC, ... (전체 목록) | 필드 정의, 타입, 필수/선택 여부 |
| **Remote Dashboard** | vehicleSpeed, engineRPM, ... (전체 목록) | 동일 |

- RPC용 API와 구독용 API를 구분한 목록
- 각 API별 타임아웃 권장값 (있는 경우)

### 8.3. wss-mqtt-api 토픽 필터 규칙 (권장)

| 항목 | 설명 |
|------|------|
| 허용 Request 토픽 패턴 | 클라이언트가 PUBLISH할 수 있는 토픽 패턴 (정규식 또는 와일드카드) |
| 허용 SUBSCRIBE 토픽 패턴 | 구독 허용 토픽 패턴 |
| JWT 클레임과 토픽의 매핑 | vehicle_id 등이 JWT에서 추출되는 경우, 토픽 내 식별자와의 매핑 규칙 |

### 8.4. 기타 (선택)

| 항목 | 설명 |
|------|------|
| 기본 타임아웃 | RPC call 기본 타임아웃 (현재 사양서 30초) |
| vehicle_id 획득 방식 | SDK 초기화 시 사용자 입력 vs JWT 클레임 등 |
| VISSv3 명세 참조 | 참조할 VISSv3 문서 또는 스키마 URL |

---

## 9. 문서 이력

| 버전 | 일자 | 작성 | 변경 내용 |
|------|------|------|-----------|
| 0.1 | 2025-03-13 | - | 초안 작성 |

