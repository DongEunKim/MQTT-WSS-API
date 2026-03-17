# 진행 예정 작업 (TODO)

> 프로젝트 루트 기준. 우선순위는 상황에 따라 조정.  
> **계층 순서**: wss_mqtt_client(기반) → RPC Client SDK → RPC Server SDK  
> 상세 계획: `docs/RPC_CLIENT_SDK_DEVELOPMENT_PLAN.md`, `docs/RPC_SERVER_SDK_DEVELOPMENT_PLAN.md`

---

## 1. wss_mqtt_client 개선 (기반 계층, 선행)

> RPC SDK는 wss_mqtt_client 위에 구축되므로, 기반 계층을 먼저 안정화한다.

### 1.1 Transport 추상화 ✅
> 상세 계획: `docs/TODO_1.1_TRANSPORT_ABSTRACTION_PLAN.md`
- [x] TransportInterface (Protocol) 정의 — `transport/base.py`
- [x] 기존 Transport 로직을 WssMqttApiTransport로 분리 — `transport/wss_mqtt_api.py`
- [x] WssMqttClient에 `transport` 파라미터 추가
- [x] `transport="wss-mqtt-api"` 시 WssMqttApiTransport 사용 (기본값, 기존 동작 호환)

### 1.2 안정성 ✅
> 상세 계획: `docs/TODO_1.2_STABILITY_PLAN.md`
- [x] **바이너리 수신 처리**: MessagePack 파싱 (msgpack optional, fallback JSON)
- [x] **disconnect 시 UNSUBSCRIBE 전송**: disconnect(unsubscribe_first=True) 옵션
- [x] **연결 끊김 시 구독 스트림 처리**: on_connection_lost, sentinel, WssConnectionError
- [x] **알 수 없는 req_id SUBSCRIPTION 로깅**: 경고 로그
- [x] **연결 끊김 감지 정책**: ping_interval, ping_timeout 파라미터

### 1.3 기능 확장
> 상세 계획: `docs/TODO_1.3_FEATURE_EXPANSION_PLAN.md`
- [x] **MQTT Transport**: paho-mqtt, `transport="mqtt"`, URL scheme으로 TCP/WebSocket 선택
- [x] publish/subscribe 인터페이스 통일 (두 transport 동일 시그니처)
- [x] **MessagePack 발송**: payload가 `bytes`이면 MessagePack 직렬화 (수신은 1.2 완료)
- [x] **재연결 정책**: 연결 끊김 시 exponential backoff 자동 재연결
- [x] **재연결 시 구독 복구**: auto_resubscribe로 재연결 후 구독 자동 복구
- [ ] **동기(Sync) 래퍼**: 1.7 API 단순화로 이관

### 1.4 프로토콜·파싱 ✅
> 상세 계획: `docs/TODO_1.4_PROTOCOL_PARSING_PLAN.md`
- [x] **알 수 없는 event 타입 처리**: unknown event 수신 시 상세 로깅 (event, req_id, raw_preview)
- [x] **req_id 누락 메시지 처리**: 파싱 실패 시 상세 에러 로깅 (keys, event)
- [x] **직렬화 파싱 실패**: JSON/MessagePack 디코딩 실패 시 raw_preview 포함 로깅

### 1.5·1.6 입력 검증 및 유틸리티 ✅
> 상세 계획: `docs/TODO_1.5_1.6_INPUT_AND_UTILITY_PLAN.md`
- [x] **1.5 토픽 형식 검증**: 빈 문자열, 길이 제한, 와일드카드(+, #) 및 NUL 금지
- [x] **1.6 배치 publish/subscribe**: `publish_many()`, `subscribe_many()` 헬퍼
- [x] **1.6 unsubscribe idempotent**: docstring 명시
- [x] **1.6 구독 미소비 가이드**: SubscriptionStream docstring 보강
- [x] **1.6 구조화 로깅**: README에 structlog 연동 안내

### 1.7 API 사용성 단순화 ✅
> 상세 계획: `docs/TODO_1.7_API_SIMPLIFICATION_PLAN.md`
> call(), receive_one()은 TGU RPC SDK(2.2)로 이관.
- [x] **WssMqttClient** (기본, 동기): sync 래퍼 (connect/disconnect/publish)
- [x] **WssMqttClientAsync** (고급, 비동기): async API
- [x] **콜백 기반 subscribe**: `subscribe(topic, callback=fn)` + `run_forever()`
- [x] **예제·문서 단순화**: publisher, subscriber (기본), *_async (고급)

---

## 2. TGU RPC SDK 개발 (상위 계층)

> wss_mqtt_client가 준비된 후 진행.  
> 상세: `docs/RPC_CLIENT_SDK_DEVELOPMENT_PLAN.md` (RPC Client SDK), `docs/RPC_DESIGN.md`

### 2.1 사전 작업: 토픽·Payload 패턴 ✅
> 상세: `docs/TOPIC_AND_ACL_SPEC.md`, `docs/RPC_DESIGN.md`
- [x] 토픽 패턴: `WMT/{service}/{vehicle_id}/request`, `WMO/{service}/{vehicle_id}/{client_id}/response`
- [x] RPC Payload: `request_id`, `response_topic`, `request` (VISSv2 스타일)
- [x] WMT 발행 시 vehicle_id ACL 필터

### 2.2 RPC MVP ✅
> 상세: `docs/TODO_2.2_RPC_MVP_IMPLEMENTATION_PLAN.md`
- [x] maas-rpc-client-sdk 프로젝트 셋업 (SDK/client/python/maas-rpc-client-sdk, wss-mqtt-client 의존)
- [x] 토픽 생성 유틸 (`topics.py`): `build_request_topic`, `build_response_topic`
- [x] RpcClient 구현: WssMqttClient 래핑, transport 전달, client_id 자동 생성
- [x] `call(service, payload)` 구현
  - payload 규격: `{ "action": str, "params": object? }`
  - request_id, response_topic 생성 → WMT 발행 → response_topic 구독 → request_id 매칭 → 응답 반환
  - asyncio.Lock으로 동시 call 직렬화, 타임아웃 처리

### 2.3 스트리밍 API 및 pub/sub
> 상세 계획: `docs/TODO_2.3_IMPLEMENTATION_PLAN.md`  
> 패턴 구분: **call_stream** (1요청→멀티응답) vs **subscribe_stream** (pub/sub 구독)

- [x] **stop()**: `run_forever()` 블로킹 해제 — WssMqttClient, RpcClient
- [x] **call_stream**: 1회 요청 → 멀티 응답 (동기 콜백, 비동기 iterator)
- [x] **subscribe_stream**: pub/sub 구독형 (동기 callback+run_forever, 비동기 async with stream)
- [x] **build_stream_topic**, topics 확장
- [x] 예제: call_stream_example.py, subscribe_stream_example.py (동기+비동기)
- [x] 기본 pub/sub 노출 — 동기/비동기 각각 publish, subscribe 위임

### 2.4 Heartbeat (TODO 2.3 완료 후)
> 종단 간·서비스별 heartbeat. subscribe_stream 등 장기 구독 시 엣지 디바이스가 클라이언트 끊김 감지.

- [ ] 스트림 수준 양방향 heartbeat 설계 (토픽, 주기, 타임아웃)
- [ ] TGU/클라이언트 구현 — TODO 2.3 완료 후 진행

### 2.5 문서화 및 테스트
- [x] maas-rpc-client-sdk README 및 사용법
- [x] 단위 테스트 (mock 기반, call 시나리오)
- [x] 통합 테스트: RPC 패턴 (Mock 서버 WMT/WMO 시뮬레이션 포함)
- [ ] ACK 에러(403, 422), 타임아웃 시나리오 (추가)

---

## 3. RPC Server SDK 개발

> RPC Client SDK(`maas-rpc-client-sdk`)의 RPC 호출에 대응하는 **서버 측 서비스를 쉽게 구현**하기 위한 SDK.  
> 상세 아키텍처: `docs/RPC_SERVER_SDK_DEVELOPMENT_PLAN.md`

### 3.1 프로젝트 셋업
> **SDK 디렉토리 구조** (client/server × 언어 분리)
>
> ```
> SDK/
> ├── client/                          ← Machine 서비스를 호출하는 쪽
> │   ├── python/
> │   │   ├── wss-mqtt-client/         # 전송 인프라 (클라이언트 전용)
> │   │   └── maas-rpc-client-sdk/     # RPC 클라이언트
> │   ├── csharp/                      # 추후
> │   └── java/                        # 추후
> └── server/                          ← Machine 위에서 서비스를 노출하는 쪽
>     └── python/                      # 우선 Python만
>         └── maas-rpc-server-sdk/
>             ├── maas_rpc_server/
>             │   ├── __init__.py
>             │   ├── config.py        # 브로커/토픽/인증/transport 설정
>             │   ├── server.py        # Server 런타임, 엔트리포인트
>             │   ├── runtime.py       # 디스패처, 요청/응답 파이프라인
>             │   ├── decorators.py    # @rpc_service, @rpc_action
>             │   ├── models.py        # Request/Response, RequestContext
>             │   ├── exceptions.py    # 서버 SDK 예외
>             │   ├── utils.py         # request_id 생성 등 공용 유틸
>             │   └── transport/
>             │       ├── __init__.py
>             │       ├── base.py      # TransportInterface (추상)
>             │       ├── mqtt.py      # 순수 MQTT (paho-mqtt)
>             │       └── aws_iot.py   # AWS IoT Core (옵션)
>             ├── tests/
>             ├── examples/
>             ├── pyproject.toml
>             └── README.md
> ```

- [x] `SDK/client/python/`으로 기존 패키지 이동
  - `SDK/wss-mqtt-client/` → `SDK/client/python/wss-mqtt-client/`
  - `SDK/maas-rpc-client-sdk/` → `SDK/client/python/maas-rpc-client-sdk/`
- [ ] `SDK/server/python/maas-rpc-server-sdk/` 디렉토리 및 `pyproject.toml` 생성
  - 의존성: `paho-mqtt` (기본), `awsiotsdk` (옵션)
- [ ] `maas_rpc_server` 패키지 골격 생성
  - `__init__.py`, `config.py`, `server.py`, `runtime.py`, `decorators.py`, `models.py`, `exceptions.py`, `utils.py`
  - `transport/` 서브패키지: `__init__.py`, `base.py`, `mqtt.py`, `aws_iot.py`

### 3.2 설정 관리 (`config.py`)
> `ServerConfig`: 모든 설정을 담는 단일 객체. 전송 방식·인증·토픽 설정 포함.

- [ ] `ServerConfig` 데이터 클래스 설계
  - `transport_type`: `"mqtt"` | `"aws_iot"`
  - MQTT 공통: `mqtt_host`, `mqtt_port`, `use_tls`, `client_id`, `keepalive`
  - AWS IoT 전용: `aws_iot_endpoint`, `aws_iot_client_id`, `aws_iot_cert_path`, `aws_iot_private_key_path`, `aws_iot_ca_cert_path`
  - 서비스 공통: `vehicle_id_source`, `qos` (기본 1), `reconnect_backoff_*`
- [ ] `ServerConfig.from_ini(path: str)` 구현
  - 섹션: `[server]`, `[mqtt]`, `[aws_iot]`
  - 미입력 항목은 기본값 적용
- [ ] `ServerConfig.from_env(prefix: str = "SERVER_")` 구현
  - 예: `SERVER_TRANSPORT_TYPE`, `SERVER_MQTT_HOST` 등
- [ ] `ServerConfig.from_ini_and_env(path)` 구현 (INI 로드 후 환경변수로 오버라이드)

### 3.3 Transport 추상화 (`transport/base.py`)
> 상위 레이어에서 전송 방식(MQTT / AWS IoT)이 은닉되도록 하는 공통 인터페이스.

- [ ] `TransportInterface` (Protocol / ABC) 정의
  - `async connect()`, `async disconnect()`
  - `async publish(topic: str, payload: bytes | str, qos: int)`
  - `async subscribe(topic: str, callback: Callable, qos: int)`
  - `async unsubscribe(topic: str)`
  - `on_connect`, `on_disconnect` 콜백 훅

### 3.4 기본 MQTT Transport (`transport/mqtt.py`)
> paho-mqtt 기반. 순수 MQTT 브로커 직접 연결. 모바일/불안정 환경을 고려한 재연결 정책 포함.

- [ ] `MqttTransport(TransportInterface)` 구현
  - `ServerConfig` 의 MQTT 필드를 읽어 paho-mqtt 클라이언트 초기화
  - TLS 설정 지원 (`use_tls`, 인증서 경로 등)
  - JWT 인증 (MQTT username/password 방식)
- [ ] QoS 1 기본, keepalive, 재연결 정책 구현
  - exponential backoff 재연결 (`reconnect_backoff_min`, `reconnect_backoff_max`)
  - 재연결 시 구독 자동 복구 (auto-resubscribe)
- [ ] asyncio 루프 통합 (`loop_start` / callback → asyncio.Queue 브릿지)

### 3.5 AWS IoT Transport (`transport/aws_iot.py`)
> AWS IoT Device SDK(v2) 기반. `mqtt_connection_builder` 로 연결 생성. AWS 자격증명/환경변수 사전 설정 전제.

- [ ] `AwsIotTransport(TransportInterface)` 구현
  - `mqtt_connection_builder.mtls_from_path(...)` 로 `mqtt.Connection` 생성
  - `ServerConfig` 의 `aws_iot_*` 필드 또는 AWS 기본 환경설정(AWS_PROFILE 등) 사용
  - `connection.connect()`, `connection.publish()`, `connection.subscribe()` 래핑
- [ ] `TransportInterface` 를 완전히 구현하여 `runtime.py` 에서 MQTT와 동일하게 교체 가능하도록 설계
- [ ] `ServerConfig.transport_type == "aws_iot"` 시 자동 선택

### 3.6 데이터 모델 (`models.py`)
> RPC 전송 래퍼 스키마(`RPC_DESIGN.md`)와 서버 내부 컨텍스트 모델 정의.

- [ ] `RpcRequestEnvelope` (dataclass)
  - `request_id: str`, `response_topic: str`, `request: dict`
- [ ] `RpcResponseEnvelope` (dataclass)
  - `request_id: str`, `result: Any | None`, `error: dict | None`
- [ ] `RequestContext` (dataclass)
  - `service: str`, `action: str`, `params: dict | None`
  - `vehicle_id: str`, `client_id: str`
  - `request_id: str`, `response_topic: str`
  - `received_at: float` (timestamp), `raw_payload: bytes`

### 3.7 예외 타입 (`exceptions.py`)
> 서버 핸들러에서 발생시키면 SDK가 표준 에러 응답으로 자동 변환.

- [ ] `RpcServerError(code, message)` — 서버 내부 오류 (500)
- [ ] `RpcBadRequestError(message)` — 요청 형식 오류 (400)
- [ ] `RpcUnauthorizedError(message)` — 인증/인가 실패 (401/403)
- [ ] `RpcActionNotFoundError(service, action)` — 액션 없음 (404)
- [ ] `RpcConcurrencyLimitError(message)` — 동시 세션 초과 (`CONCURRENCY_LIMIT_EXCEEDED`)
- [ ] 예외 → `{ "code": "...", "message": "..." }` 자동 변환 매핑 테이블

### 3.8 런타임/디스패처 (`runtime.py`)
> 수신된 MQTT 메시지를 파싱하여 핸들러로 라우팅하고, 응답을 발행하는 SDK 핵심 루프.

- [ ] **요청 수신 루프** 구현
  - Transport 콜백 → asyncio.Queue → 코루틴 처리
  - 동시 요청을 비동기로 병렬 처리 (`asyncio.create_task`)
- [ ] **Envelope 파싱/검증**
  - JSON / MessagePack 역직렬화
  - `request_id`, `response_topic`, `request` 필수 필드 검사
  - 파싱 실패 시 상세 로깅 후 무시 (클라이언트에 에러 응답 불가 케이스)
- [ ] **`RequestContext` 생성**
  - 토픽에서 `service`, `vehicle_id` 추출
  - Envelope에서 `client_id`(response_topic 파싱), `action`, `params` 추출
- [ ] **디스패치 테이블 관리**
  - `(service, action)` → 핸들러 코루틴 매핑
  - `@rpc_service`, `@rpc_action` 데코레이터가 등록한 메타데이터 기반으로 테이블 구성
  - 존재하지 않는 service/action → `RpcActionNotFoundError` 응답
- [ ] **응답 Envelope 직렬화 및 발행**
  - 핸들러 반환값 → `RpcResponseEnvelope(result=...)` 구성
  - 예외 → `RpcResponseEnvelope(error={"code": ..., "message": ...})` 변환
  - `transport.publish(response_topic, payload)` 호출
- [ ] **request_id 캐시 훅** (중복 요청 방지)
  - 최근 N개 `request_id` 인메모리 캐시 (TTL 기반)
  - 이미 처리된 요청이면 동일 응답 재전송 또는 무시 (서비스 선택)

### 3.9 데코레이터 (`decorators.py`)
> 서비스/액션 핸들러 등록 API. 서비스 개발자가 직접 사용하는 공개 인터페이스.

- [ ] `@rpc_service(name: str, max_concurrent_clients: int = 0)` 구현
  - 클래스에 적용 시 서비스 등록 메타데이터 부여
  - `max_concurrent_clients > 0` 이면 런타임이 동시 클라이언트 수 추적
- [ ] `@rpc_action(name: str, sync: bool = False)` 구현
  - 메서드를 디스패치 테이블에 등록
  - `sync=True` 이면 스레드풀(`asyncio.to_thread`)로 자동 래핑
- [ ] 글로벌 레지스트리 구조 설계 (`_SERVICE_REGISTRY`)
  - `Server` 초기화 시 레지스트리에서 디스패치 테이블 구성

### 3.10 서버 엔트리포인트 (`server.py`)
> 서비스 개발자가 직접 사용하는 메인 클래스. 내부는 비동기 코어, 외부에는 동기/비동기 양쪽 인터페이스 제공.

- [ ] `ServerAsync` (비동기 코어) 구현
  - `async start()`, `async stop()`, `async run_forever()`
  - Transport 선택·초기화, 서비스 등록, 런타임 루프 시작
  - 서비스별 요청 토픽 구독: `WMT/{service}/{vehicle_id}/request`
    - 와일드카드(`WMT/+/+/request`) 또는 서비스별 구독 전략 선택
- [ ] `Server` (동기 래퍼) 구현
  - 내부 `ServerAsync` + 백그라운드 스레드 이벤트 루프 패턴 (Client SDK와 동일)
  - `start()`, `stop()`, `run_forever()` — 블로킹 API
  - `Server.from_ini(path)`, `Server.from_env()` 팩토리 메서드
- [ ] graceful shutdown 처리
  - `stop()` 시 진행 중인 핸들러 완료 대기, Transport 연결 종료

### 3.11 단위 테스트
> Mock Transport를 사용하여 네트워크 없이 검증.

- [ ] `TransportInterface` Mock 구현 (`tests/mock_transport.py`)
- [ ] `runtime.py` 파싱/디스패치/응답 발행 단위 테스트
  - 정상 요청 → 핸들러 호출 → 응답 발행 검증
  - Envelope 파싱 실패 시 로깅·무시 검증
  - 존재하지 않는 action → `RpcActionNotFoundError` 응답 검증
  - 핸들러 예외 → 표준 에러 응답 변환 검증
- [ ] `request_id` 캐시 중복 처리 단위 테스트
- [ ] `ServerConfig.from_ini()`, `from_env()` 단위 테스트

### 3.12 통합 테스트
> 실제 MQTT 브로커(또는 Mock)와 RPC Client SDK를 함께 사용하는 종단 간 테스트.

- [ ] Mock MQTT 브로커 또는 인메모리 브릿지 기반 통합 테스트 환경 구성
- [ ] **RPC call 종단 간 테스트**
  - `RpcClient.call("RemoteUDS", {...})` → Server SDK 핸들러 → 응답 반환 검증
- [ ] **에러 시나리오 테스트**
  - 존재하지 않는 action 요청 → `RpcActionNotFoundError` 응답
  - 핸들러 내부 예외 → `RpcServerError` 응답
  - 타임아웃 (핸들러 지연) 시나리오
- [ ] **재연결 시나리오 테스트**
  - 브로커 연결 끊김 → 재연결 후 구독 복구 검증
- [ ] **request_id 중복 처리 테스트**
  - 동일 `request_id` 재전송 → 캐시 히트, 동일 응답 재발행 검증

### 3.13 예제 및 문서화
> 서비스 개발자를 위한 빠른 시작 가이드와 참조 예제.

- [ ] `examples/remote_uds_server.py` — MQTT transport, call 처리 예제
- [ ] `examples/remote_uds_server_aws.py` — AWS IoT transport 예제
- [ ] `examples/remote_dashboard_server.py` — subscribe_stream 서버 측 대응 예제 (pub/sub 발행)
- [ ] `README.md` 작성 (설치, 설정, 서비스 구현 방법, 예제)
- [ ] 서비스 개발 가이드 (`docs/RPC_SERVER_SDK_DEVELOPMENT_PLAN.md` 7장 기반)
  - 단일 클라이언트 전용 서비스 구현 패턴 (RemoteDMS 예시 코드 포함)
  - Idempotent 핸들러 구현 가이드

---

## 4. 문서·배포

- [ ] **API 문서화**: docstring 보완, Sphinx/Read the Docs 검토
- [ ] **PyPI 배포**: `wss-mqtt-client` 패키지 공개 (버전 0.2.0 등)

---

## 5. 인프라

- [ ] **WSS-MQTT API 게이트웨이 구현**: 현재는 Mock 서버만 존재. 실제 게이트웨이 서버 개발

---

## 참고 (완료된 항목)

- [x] SDK 기반 구현 (publish, subscribe, unsubscribe)
- [x] Mock 서버 및 통합 테스트
- [x] **동일 토픽 중복 구독 개선**: 토픽별 참조 카운트, 마지막 스트림 종료 시에만 UNSUBSCRIBE 전송
- [x] **구독 큐 무한 증가 방지**: maxsize 기본값 10000, 초과 시 메시지 폐기 및 경고 로그
- [x] **Transport 추상화**: TransportInterface, WssMqttApiTransport, transport 파라미터
- [x] **안정성 개선**: MessagePack 수신, disconnect UNSUBSCRIBE, 연결 끊김 sentinel, 로깅, ping 파라미터
- [x] **MQTT Transport**: transport="mqtt", URL scheme으로 TCP/WebSocket 선택 (순수 MQTT + MQTT over WSS)
- [x] **MessagePack 발송**: payload bytes 시 MessagePack 직렬화
- [x] **재연결 정책**: auto_reconnect, exponential backoff, auto_resubscribe
- [x] **프로토콜·파싱 개선**: unknown event, req_id 누락, 직렬화 실패 시 상세 로깅 (raw_preview 등)
- [x] **입력 검증·유틸리티**: 토픽 검증, publish_many, subscribe_many, docstring 보강, structlog 안내
- [x] **API 사용성 단순화**: WssMqttClient(기본), WssMqttClientAsync(고급), 콜백 subscribe, 예제 정리
- [x] 발행/구독 예제 및 실행 가이드
- [x] 가상환경, requirements.txt, 프로젝트 루트 README
- [x] **RPC 설계 확정**: RPC_DESIGN (VISSv2 패턴, response_topic, call(service, payload))
- [x] **WSS RPC SDK MVP**: topics.py, RpcClient, call(), 예제, Mock WMT/WMO 시뮬레이션
- [x] **RPC 동기식 기본**: RpcClient(동기, 기본), RpcClientAsync(비동기, 고급). pub/sub와 동일 패턴.
