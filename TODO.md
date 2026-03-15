# 진행 예정 작업 (TODO)

> 프로젝트 루트 기준. 우선순위는 상황에 따라 조정.  
> **계층 순서**: wss_mqtt_client(기반) → TGU RPC SDK(상위)  
> 상세 계획: `docs/TGU_RPC_SDK_DEVELOPMENT_PLAN.md`

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
> 상세: `docs/TGU_RPC_SDK_DEVELOPMENT_PLAN.md`, `docs/RPC_TRANSPORT_LAYER_DESIGN.md`

### 2.1 사전 작업: 토픽·Payload 패턴 ✅
> 상세: `docs/TOPIC_AND_ACL_SPEC.md`, `docs/MQTT_RPC_METHODOLOGY.md`
- [x] 토픽 패턴: `WMT/{service}/{vehicle_id}/request`, `WMO/{service}/{vehicle_id}/{client_id}/response`
- [x] RPC Payload: `request_id`, `response_topic`, `request` (VISSv2 스타일)
- [x] WMT 발행 시 vehicle_id ACL 필터

### 2.2 RPC MVP ✅
> 상세: `docs/TODO_2.2_RPC_MVP_IMPLEMENTATION_PLAN.md`
- [x] tgu-rpc-sdk 프로젝트 셋업 (SDK/tgu-rpc-sdk, wss-mqtt-client 의존)
- [x] 토픽 생성 유틸 (`topics.py`): `build_request_topic`, `build_response_topic`
- [x] TguRpcClient 구현: WssMqttClient 래핑, transport 전달, client_id 자동 생성
- [x] `call(service, payload)` 구현
  - payload 규격: `{ "action": str, "params": object? }`
  - request_id, response_topic 생성 → WMT 발행 → response_topic 구독 → request_id 매칭 → 응답 반환
  - asyncio.Lock으로 동시 call 직렬화, 타임아웃 처리

### 2.3 스트리밍 API 및 pub/sub
> 상세 계획: `docs/TODO_2.3_IMPLEMENTATION_PLAN.md`  
> 패턴 구분: **call_stream** (1요청→멀티응답) vs **subscribe_stream** (pub/sub 구독)

- [x] **stop()**: `run_forever()` 블로킹 해제 — WssMqttClient, TguRpcClient
- [x] **call_stream**: 1회 요청 → 멀티 응답 (동기 콜백, 비동기 iterator)
- [x] **subscribe_stream**: pub/sub 구독형 (동기 callback+run_forever, 비동기 async with stream)
- [x] **build_stream_topic**, topics 확장
- [x] 예제: call_stream_example.py, subscribe_stream_example.py (동기+비동기)
- [x] 기본 pub/sub 노출 — 동기/비동기 각각 publish, subscribe 위임

### 2.4 Heartbeat (TODO 2.3 완료 후)
> 종단 간·서비스별 heartbeat. subscribe_stream 등 장기 구독 시 TGU가 클라이언트 끊김 감지.

- [ ] 스트림 수준 양방향 heartbeat 설계 (토픽, 주기, 타임아웃)
- [ ] TGU/클라이언트 구현 — TODO 2.3 완료 후 진행

### 2.5 문서화 및 테스트
- [x] tgu-rpc-sdk README 및 사용법
- [x] 단위 테스트 (mock 기반, call 시나리오)
- [x] 통합 테스트: RPC 패턴 (Mock 서버 WMT/WMO 시뮬레이션 포함)
- [ ] ACK 에러(403, 422), 타임아웃 시나리오 (추가)

---

## 3. 문서·배포

- [ ] **API 문서화**: docstring 보완, Sphinx/Read the Docs 검토
- [ ] **PyPI 배포**: `wss-mqtt-client` 패키지 공개 (버전 0.2.0 등)

---

## 4. 인프라

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
- [x] **RPC 설계 확정**: MQTT_RPC_METHODOLOGY, RPC_TRANSPORT_LAYER_DESIGN (VISSv2 패턴, response_topic, call(service, payload))
- [x] **TGU RPC SDK MVP**: topics.py, TguRpcClient, call(), 예제, Mock WMT/WMO 시뮬레이션
- [x] **RPC 동기식 기본**: TguRpcClient(동기, 기본), TguRpcClientAsync(비동기, 고급). pub/sub와 동일 패턴.
