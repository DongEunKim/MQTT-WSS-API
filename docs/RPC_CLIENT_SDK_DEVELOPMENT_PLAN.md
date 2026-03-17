# RPC Client SDK 개발 계획서

> **문서 목적**  
> RPC Client SDK의 아키텍처·설계 원칙을 정리한다.  
> **진행 상황·할 일**은 루트 [TODO.md](../TODO.md) 참고.

---


## 1. 프로젝트 개요

### 1.1. 배경

- 백엔드 서비스는 MQTT 브로커에 연결되어 클라이언트와 RPC를 수행한다.
- 클라이언트는 **wss-mqtt-api** 또는 **MQTT over WSS** 중 선택하여 연결할 수 있다.
- VISSv3의 MQTT 전송 프로토콜 사례와 유사한 구조를 갖는다.
- 현재 클라이언트는 토픽 경로, 구독/발행 순서 등을 직접 처리해야 하며 개발 부담이 크다.

### 1.2. 목표

- **서비스·API 명세만 알면 RPC를 쉽게 구현할 수 있는 SDK** 제공
- 기존 `wss-mqtt-client`를 재활용·포함한 **통합 SDK** 구성
- 기본 pub/sub 기능도 클라이언트가 계속 사용할 수 있도록 유지
- 표준화된 토픽 패턴과 페이로드 스키마를 적용
- **연결 방식 선택**: wss-mqtt-api 또는 MQTT over WSS를 옵션으로 지정하여 선택 가능, 인터페이스는 동일

### 1.3. 적용 대상

| 구분 | 내용 |
|------|------|
| **후보 서비스** | Remote UDS, Remote Dashboard |
| **API 패턴** | Request & Response RPC, VISSv3 스타일 구독(주기/이벤트 발행) |
| **클라이언트 환경** | Python (우선), 추후 다른 언어 확장 고려 |

---

## 2. 아키텍처

### 2.1. 설계 원칙: Transport는 wss_mqtt_client에 집중

**transport 선택과 구현은 wss_mqtt_client에서 담당**한다. RPC Client SDK는 transport를 직접 구현하지 않고, 사용자 선택을 wss_mqtt_client에 전달한다.

| 원칙 | 설명 |
|------|------|
| **구조적 일관성** | transport 로직이 한 곳(wss_mqtt_client)에 집중. RPC Client SDK는 RPC·토픽 패턴에만 집중. |
| **통합 혜택** | RPC와 기본 pub/sub 모두 wss_mqtt_client를 사용하므로 transport 선택이 동일하게 적용됨. |
| **재사용성** | 특정 서버(TGU 등) 없이 pub/sub만 쓰는 경우에도 wss_mqtt_client로 transport 선택 가능. |
| **의존성 단순화** | RPC Client SDK는 wss-mqtt-client만 의존. paho-mqtt는 wss_mqtt_client 내부에 한정. |

### 2.2. 연결 방식 옵션 (wss_mqtt_client 수준)

wss_mqtt_client의 `WssMqttClient`(동기) 또는 `WssMqttClientAsync`(비동기) 초기화 시 `transport` 옵션으로 선택한다.

| transport | 설명 | 인증 | 사용 라이브러리 |
|-----------|------|------|-----------------|
| `wss-mqtt-api` | wss-mqtt-api 게이트웨이 경유 | JWT (WebSocket handshake) | websockets (기존) |
| `mqtt` | 네이티브 MQTT (URL로 TCP/WebSocket 선택) | JWT (username 등) | paho-mqtt |

- **MQTT 직접 연결 시**: VISS와 동일하게 JWT를 사용하여 TGU 접근 제어 수행.
- **MQTT 클라이언트**: paho-mqtt 사용.

### 2.3. 레이어 구조

```
┌─────────────────────────────────────────────────────────────────┐
│  RPC Client SDK (maas-rpc-client-sdk)                                    │
│  - call(service, payload)             : RPC 호출                   │
│  - subscribe_stream(service, api)     : 구독형 API                 │
│  - publish / subscribe                : wss_mqtt_client 위임       │
│  - transport 옵션을 wss_mqtt_client에 전달                          │
├─────────────────────────────────────────────────────────────────┤
│  wss_mqtt_client (wss-mqtt-client 패키지)                          │
│  - WssMqttClient(기본), WssMqttClientAsync(url, token, transport=...) │
│  - transport="wss-mqtt-api" | "mqtt"  →  내부 Transport 구현 선택   │
│  - publish(topic, payload), subscribe(topic)  →  통일 인터페이스    │
├──────────────────────┬──────────────────────────────────────────┤
│ WssMqttApiTransport  │  MqttOverWssTransport                     │
│ (websockets + JSON)  │  (paho-mqtt)                              │
└──────────────────────┴──────────────────────────────────────────┘
         │                            │
         ▼                            ▼
   wss-mqtt-api              MQTT Broker (WSS)
         │                            │
         └────────────┬───────────────┘
                      ▼
               MQTT Broker ←→ TGU
```

### 2.4. 패키지 구조

**wss-mqtt-client (확장)**

```
wss-mqtt-client/
├── wss_mqtt_client/
│   ├── __init__.py
│   ├── client.py              # WssMqttClient (transport 파라미터 추가)
│   ├── transport/
│   │   ├── __init__.py
│   │   ├── base.py            # TransportInterface (Protocol)
│   │   ├── wss_mqtt_api.py    # 기존 WebSocket + JSON Envelope
│   │   └── mqtt.py            # paho-mqtt, MQTT over WSS
│   ├── protocol.py, models.py, exceptions.py, constants.py  # 기존 유지
│   └── ...
├── pyproject.toml             # dependencies: websockets, paho-mqtt
└── ...
```

**maas-rpc-client-sdk (RPC Client SDK)**

```
maas-rpc-client-sdk/
├── maas_rpc_client/
│   ├── __init__.py
│   ├── client.py              # RpcClient (동기, WssMqttClient 패턴)
│   ├── client_async.py        # RpcClientAsync (비동기, 스트리밍 등)
│   ├── topics.py              # 토픽 패턴 생성 유틸
│   └── exceptions.py          # RPC 예외
├── pyproject.toml             # dependencies: wss-mqtt-client (단일 의존성)
├── README.md
└── examples/
    ├── rpc_call_wss_api.py
    ├── rpc_call_mqtt.py
    └── subscribe_stream.py
```

### 2.5. 초기화 흐름

```python
# RpcClient
client = RpcClient(
    url="wss://...",  # 또는 host/port (transport에 따라 해석)
    token="jwt",
    thing_name="device_001",
    oem="acme",
    asset="VIN123",
    transport="mqtt",  # wss_mqtt_client에 그대로 전달
)

# 내부: WssMqttClient(url=..., token=..., transport="mqtt") 생성
# RPC (call, call_stream), 기본 pub/sub (publish, subscribe) 모두 동일 WssMqttClient 사용
```

### 2.6. 기본 pub/sub 유지

- `RpcClient`가 내부 `WssMqttClient`를 노출 (예: `client.raw_client` 또는 `client.wss_client`)
- `publish`, `subscribe`는 `WssMqttClient`에 위임
- transport 선택은 `WssMqttClient` 생성 시 한 번만 지정, RPC와 pub/sub 모두 동일 transport 사용

### 2.7. MQTT RPC 방법론 (참조: `docs/RPC_DESIGN.md`)

**전송 계층 래퍼 관점**: MQTT/WSS payload는 RPC를 위한 중간 전송 계층이다. 엣지 서버는 payload에서 **응답 위치(response_topic)**를 명시적으로 읽어 처리한다. VISSv2 MQTT 패턴을 따른다.

| 항목 | 내용 |
|------|------|
| **토픽 분리** | Request: `WMT/{service}/{thing_name}/{oem}/{asset}/request` / Response: 클라이언트가 `response_topic`으로 명시 |
| **상관관계** | payload의 `request_id`로 요청-응답 매칭 |
| **클라이언트** | ① 응답 토픽 구독 ② 요청 발행 (response_topic 포함) ③ request_id 일치하는 응답 대기 ④ 타임아웃 처리 |
| **엣지 서버** | ① `WMT/+/{thing_name}/+/+/request` 구독 ② payload에서 response_topic, request 추출 ③ response_topic에 응답 발행 |

**요청 Payload (RPC 전송 래퍼)**

| 필드 | 필수 | 설명 |
|------|------|------|
| request_id | Y | 요청당 고유 ID. 응답 매칭용 |
| response_topic | Y | TGU가 응답을 발행할 토픽. 클라이언트(SDK)가 명시 |
| request | Y | 서비스별 요청 `{ action, params }`. VISSv3, RemoteUDS 등 |

**응답 Payload**

| 필드 | 필수 | 설명 |
|------|------|------|
| request_id | Y | 요청의 request_id와 동일. 매칭용 |
| result | N | 성공 시 결과 |
| error | N | 실패 시 에러 정보 `{ "code": "...", "message": "..." }` |

**VISSv3 통합**: VISSv3는 이 RPC 설계가 포함하는 서비스 중 하나. `request`에 VISSv2 Core 형식(action, path, filter 등)을 사용한다.

---

## 3. 개발 범위

### 3.1. wss_mqtt_client 확장 (wss-mqtt-client 패키지)

| 항목 | 설명 |
|------|------|
| TransportInterface | publish, subscribe 추상 인터페이스 (Protocol) |
| WssMqttApiTransport | 기존 Transport 로직 분리, wss-mqtt-api 프로토콜 |
| MqttOverWssTransport | paho-mqtt 기반, MQTT over WSS, JWT 인증 (VISS 방식) |
| WssMqttClient 수정 | `transport` 파라미터 추가, 선택된 Transport 인스턴스 사용 |
| 통일 인터페이스 | publish(topic, payload), subscribe(topic) — 두 transport에서 동일 시그니처 |

### 3.2. RPC Client SDK (maas-rpc-client-sdk 패키지)

| 항목 | 설명 |
|------|------|
| RpcClient 클래스 | url, token, thing_name, oem, asset, transport 옵션 — wss_mqtt_client에 전달 |
| call(service, payload) | Request & Response RPC. payload 규격 `{action, params}`. request_id·response_topic 생성, WMT 발행, response_topic 구독 후 request_id 매칭·응답 수신 |
| call_stream(service, payload) | 1회 요청 → 멀티 응답 스트림. done/stream_end 수신 시 종료 |
| 기본 pub/sub | publish, subscribe를 WssMqttClient에 위임, raw_client 노출 |
| 토픽 패턴 | topics.py로 표준 토픽 패턴 적용 |
| 타임아웃·에러 처리 | wss_mqtt_client 예외 활용 및 필요 시 래핑 |

### 3.2. 제외 범위 (본 단계)

| 항목 | 비고 |
|------|------|
| 페이로드 스키마 검증 | 선택 사항, 추후 확장 |
| 다국어 지원 | 문서·주석 한글 우선 |
| Python 외 언어 SDK | 별도 프로젝트로 검토 |

---

## 4. 개발 단계

### Phase 1: 토픽 패턴 정의 (사전 작업) ✅

> 상세: `docs/TOPIC_AND_ACL_SPEC.md`, `docs/RPC_DESIGN.md`
- [x] 토픽 패턴 확정:
  - 요청: `WMT/{service}/{thing_name}/{oem}/{asset}/request`
  - 응답: `WMO/{service}/{thing_name}/{oem}/{asset}/{client_id}/response`
- [x] Payload 상관관계: request_id, response_topic, request 등 (RPC 방법론 문서 참조)
- [x] wss-mqtt-api ACL: WMT 발행 시 oem+asset 접근 허가 검사, 미허가 시 거부
- [x] 엣지 서버 구독 패턴: `WMT/+/{thing_name}/+/+/request`

※ 서비스/API 상세 명세(페이로드 스키마)는 SDK 구현에 불필요. TGU 서버 및 클라이언트 애플리케이션 개발 시 별도 확정.

### Phase 2: wss_mqtt_client — Transport 추상화 및 wss-mqtt-api 분리 ✅

- [x] TransportInterface (Protocol) 정의
- [x] 기존 Transport 로직을 WssMqttApiTransport로 분리
- [x] WssMqttClient에 `transport` 파라미터 추가, `transport="wss-mqtt-api"` 시 WssMqttApiTransport 사용
- [x] 기존 동작 호환성 유지 (transport 미지정 시 wss-mqtt-api 기본)

### Phase 3: RPC Client SDK — 골격 및 RPC (MVP 우선)

- [x] 프로젝트 셋업 (SDK/client/python/maas-rpc-client-sdk, pyproject.toml, maas_rpc_client 패키지, wss-mqtt-client 의존)
- [x] 토픽 생성 유틸 (`topics.py`)
- [x] RpcClient 구현 — WssMqttClient 생성 시 transport 전달
- [x] `call()` 메서드 구현

### Phase 4: wss_mqtt_client — MQTT over WSS 지원

- [ ] paho-mqtt 의존성 추가
- [ ] MqttOverWssTransport 구현 (MQTT over WSS, JWT 인증 VISS 방식)
- [x] `transport="mqtt"` 옵션 지원, WssMqttClient에서 선택
- [ ] publish/subscribe 인터페이스 통일 (두 transport에서 동일 시그니처)

### Phase 5: RPC Client SDK — 구독형 API 및 기본 pub/sub

- [ ] `subscribe_stream()` 메서드 구현
- [ ] 기본 pub/sub 노출 (publish, subscribe 위임, raw_client 또는 wss_client 노출)
- [ ] 예제 코드 작성 (rpc_call_wss_api, rpc_call_mqtt, subscribe_stream)

### Phase 6: 문서화 및 테스트

- [x] wss-mqtt-client, maas-rpc-client-sdk 각 README 및 사용법
- [ ] 단위 테스트 (mock 기반)
- [ ] 통합 테스트 (실 서버 연동 시 선택)

---

## 5. 사용 시나리오 (목표 UX)

인터페이스는 transport 옵션과 관계없이 동일하다.

**기본**: RpcClient (동기). **고급**: RpcClientAsync (비동기, 스트리밍 등).

### 5.1. RPC 호출 (wss-mqtt-api) — 기본 (동기)

```python
from maas_rpc_client import RpcClient

with RpcClient(
    url="wss://api.example.com/v1/messaging",
    token="jwt",
    thing_name="device_001",
    oem="acme",
    asset="VIN123",
    transport="wss-mqtt-api",  # 기본값, wss_mqtt_client에 전달
) as client:
    result = client.call("RemoteUDS", {"action": "readDTC", "params": {"source": 0x01}})
```

### 5.2. RPC 호출 (MQTT over WSS, JWT 인증) — 기본 (동기)

```python
# transport="mqtt" → wss_mqtt_client가 paho로 MQTT 연결 (URL에 따라 TCP/WSS)
with RpcClient(
    url="wss://mqtt.example.com:443/mqtt",
    token="jwt",  # VISS 방식 JWT
    thing_name="device_001",
    oem="acme",
    asset="VIN123",
    transport="mqtt",
) as client:
    result = client.call("RemoteUDS", {"action": "readDTC", "params": {"source": 0x01}})
```

### 5.3. 1회 요청 → 멀티 응답 (call_stream) — RpcClientAsync

```python
from maas_rpc_client import RpcClientAsync

async with RpcClientAsync(
    url="wss://api.example.com/v1/messaging",
    token="jwt",
    thing_name="device_001",
    oem="acme",
    asset="VIN123",
) as client:
    async for chunk in client.call_stream(
        "RemoteDashboard", {"action": "getLiveData"}
    ):
        print(chunk)
```

### 5.4. 기본 pub/sub (동일 transport 사용) — RpcClientAsync

```python
# RPC와 동일한 transport. wss_mqtt_client의 publish/subscribe 위임
async with RpcClientAsync(...) as client:
    await client.publish("custom/topic", payload)
    async with client.subscribe("custom/response") as s:
        async for event in s:
            ...
```

### 5.5. wss_mqtt_client 직접 사용 (pub/sub 전용)

```python
# 특정 RPC 서비스 없이 pub/sub만 필요할 때도 transport 선택 가능
from wss_mqtt_client import WssMqttClientAsync

async with WssMqttClientAsync(
    url="wss://...",
    token="jwt",
    transport="mqtt",
) as client:
    await client.publish("topic", payload)
    async with client.subscribe("topic/response") as stream:
        async for event in stream:
            ...
```

---

## 6. 의존성 및 제약

### 6.1. 의존성

**maas-rpc-client-sdk**

| 패키지 | 용도 |
|--------|------|
| wss-mqtt-client | 유일 직접 의존성. transport 로직 모두 포함 |

**wss-mqtt-client**

| 패키지 | 용도 |
|--------|------|
| websockets | wss-mqtt-api transport |
| paho-mqtt | MQTT over WSS transport |
| Python 3.8+ | - |

- MQTT transport: paho-mqtt + asyncio 래핑 (loop_start 등) 활용

### 6.2. 인증

| transport | 인증 방식 |
|-----------|-----------|
| wss-mqtt-api | JWT (WebSocket handshake, Authorization 헤더 또는 쿼리 파라미터) |
| mqtt | JWT (username/password 또는 확장 메커니즘) |

### 6.3. 참조 문서

- `docs/system_specification_v1.md` — wss-mqtt-api 사양
- `docs/RPC_DESIGN.md` — RPC 방법론 및 전송 계층 설계
- `docs/TOPIC_AND_ACL_SPEC.md` — 토픽 패턴 및 ACL 규격
- `docs/wss-mqtt-message-schema.json` — 메시지 Envelope 스키마

---

## 7. 리스크 및 대응

| 리스크 | 대응 |
|--------|------|
| 토픽 패턴 미확정 | Phase 1을 우선 진행하고, 확정 후 SDK 반영 |
| wss-mqtt-api ACL 미정의 | 토픽 패턴을 유연하게 설계하여 ACL 추가 시 매핑만 수정 |
| paho-mqtt 비동기 통합 | paho-mqtt는 기본 동기 API. asyncio 루프에서 실행하거나 `loop_start` 활용 |

---

## 8. 추가로 제공이 필요한 정보 (SDK 구현용)

SDK 구현을 위해 필요한 정보. **서비스·API 상세 명세(페이로드 스키마)는 SDK에 불필요**하며, TGU 서버 및 클라이언트 애플리케이션 개발 시 별도 확정한다.

### 8.1. 토픽 패턴 (필수)

| 항목 | 설명 | 예시 |
|------|------|------|
| **요청 토픽 패턴** | 클라이언트가 PUBLISH하는 토픽 형식 | `WMT/{service}/{thing_name}/{oem}/{asset}/request` |
| **응답 토픽 패턴** | RPC 응답 수신용 SUBSCRIBE 토픽 (client_id별 분리) | `WMO/{service}/{thing_name}/{oem}/{asset}/{client_id}/response` |
| **엣지 서버 구독 패턴** | 엣지 서버가 요청 수신을 위해 구독하는 패턴 | `WMT/+/{thing_name}/+/+/request` |

### 8.1.1. RPC Payload 스키마 (필수)

> 상세: `docs/RPC_DESIGN.md`

**요청 Payload (RPC 전송 래퍼)**  
`request_id`, `response_topic`, `request` 필수. `request` = `{ action, params }` (서비스별).

**응답 Payload**  
`request_id` 필수. 성공 시 `result`, 실패 시 `error` (`code`, `message`).

### 8.2. wss-mqtt-api 토픽 필터 규칙 (권장, wss-mqtt-api 사용 시)

| 항목 | 설명 |
|------|------|
| 허용 Request 토픽 패턴 | 클라이언트가 PUBLISH할 수 있는 토픽 패턴 (정규식 또는 와일드카드) |
| 허용 SUBSCRIBE 토픽 패턴 | 구독 허용 토픽 패턴 |
| JWT 클레임과 토픽의 매핑 | oem+asset 등이 JWT에서 추출되는 경우, 토픽 내 식별자와의 매핑 규칙 |

### 8.3. MQTT JWT 인증 (transport="mqtt" 사용 시)

| 항목 | 설명 |
|------|------|
| JWT 전달 방식 | username/password, CONNECT 확장 프로퍼티 등 VISS 사례 기준 |
| 엣지 서버 접근 제어 | JWT 클레임 기반 oem+asset 권한 검증 방식 |

### 8.4. 기타 (선택)

| 항목 | 설명 |
|------|------|
| 기본 타임아웃 | RPC call 기본 타임아웃 (현재 사양서 30초) |
| thing_name / oem / asset 획득 방식 | SDK 초기화 시 사용자 입력 vs JWT 클레임 등 |

---

## 9. 문서 이력

| 버전 | 일자 | 작성 | 변경 내용 |
|------|------|------|-----------|
| 0.1 | 2025-03-13 | - | 초안 작성 |
| 0.2 | 2025-03-13 | - | Transport 옵션(wss-mqtt-api/mqtt) 추가, paho-mqtt·JWT(VISS) 반영, 서비스/API 명세는 SDK 외부로 분리 |
| 0.3 | 2025-03-13 | - | Transport를 wss_mqtt_client에 집중, RPC Client SDK는 transport 전달만. 구조적 일관성 반영 |
| 0.4 | 2025-03-13 | - | Phase 3·4 순서 변경: RPC MVP 우선 (2→3→4→5), MQTT 지원은 Phase 4로 |
| 0.5 | 2025-03-13 | - | Phase 2 완료 반영: Transport 추상화, WssMqttApiTransport 분리 |
| 0.6 | 2025-03-13 | - | MQTT RPC 방법론 반영: 2.7절 추가, Payload 스키마(8.1.1), 참조 문서 보강 |
| 0.7 | 2025-03-13 | - | VISSv2 MQTT 패턴 반영: response_topic 명시, request 중첩, RPC_DESIGN 통합. call(service, payload) |

