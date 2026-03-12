# 진행 예정 작업 (TODO)

> 프로젝트 루트 기준. 우선순위는 상황에 따라 조정.  
> 상세 계획: `docs/TGU_RPC_SDK_DEVELOPMENT_PLAN.md`

---

## TGU RPC SDK 개발 (개발계획서 반영)

### Phase 1: 토픽 패턴 정의 (사전 작업)
- [ ] 토픽 패턴 규칙 확정 (예: `tgu/{vehicle_id}/{service}/{api}/request`, `.../response`, `.../data`)
- [ ] wss-mqtt-api Request 토픽 필터(ACL) 규칙 확정

### Phase 2: wss_mqtt_client — Transport 추상화
- [ ] TransportInterface (Protocol) 정의
- [ ] 기존 Transport 로직을 WssMqttApiTransport로 분리
- [ ] WssMqttClient에 `transport` 파라미터 추가
- [ ] `transport="wss-mqtt-api"` 시 WssMqttApiTransport 사용 (기본값, 기존 동작 호환)

### Phase 3: TGU RPC SDK — 골격 및 RPC (MVP 우선)
- [ ] tgu-rpc-sdk 프로젝트 셋업 (wss-mqtt-client 의존)
- [ ] 토픽 생성 유틸 (`topics.py`)
- [ ] TguRpcClient 구현 (WssMqttClient 래핑, transport 전달)
- [ ] `call()` 메서드 구현

### Phase 4: wss_mqtt_client — MQTT over WSS 지원
- [ ] paho-mqtt 의존성 추가
- [ ] MqttOverWssTransport 구현 (MQTT over WSS, JWT 인증 VISS 방식)
- [ ] `transport="mqtt"` 옵션 지원
- [ ] publish/subscribe 인터페이스 통일 (두 transport 동일 시그니처)

### Phase 5: TGU RPC SDK — 구독형 API 및 기본 pub/sub
- [ ] `subscribe_stream()` 메서드 구현
- [ ] 기본 pub/sub 노출 (publish, subscribe 위임, raw_client 노출)
- [ ] 예제 코드 작성 (rpc_call_wss_api, rpc_call_mqtt, subscribe_stream)

### Phase 6: 문서화 및 테스트
- [ ] wss-mqtt-client, tgu-rpc-sdk README 및 사용법
- [ ] 단위 테스트 (mock 기반)
- [ ] 통합 테스트 (실 서버 연동 시 선택)

---

## SDK 개선 (wss_mqtt_client 기존)

### 기능 확장
- [ ] **MessagePack 지원**: 사양 5.1. payload가 `bytes`이면 자동으로 MessagePack 사용 (플래그 없음)
- [ ] **재연결 정책**: 연결 끊김 시 exponential backoff 자동 재연결
- [ ] **동기(Sync) 래퍼**: `asyncio.run()` 기반 sync API (예: `WssMqttClientSync`)

### 안정성
- [ ] **재연결 시 구독 복구**: 서버 TTL 때문에 재구독 필요. 재연결 후 구독 자동 재등록 옵션
- [ ] **바이너리 수신 처리**: 서버가 MessagePack으로 보낸 SUBSCRIPTION 파싱

### 유틸리티
- [ ] **배치 publish/subscribe**: 다수 토픽 일괄 처리 헬퍼
- [ ] **구조화 로깅**: `structlog` 등 연동 옵션

---

## 테스트

- [ ] **통합 테스트 확장**: ACK 에러(403, 422 등) 시나리오, 타임아웃 시나리오
- [ ] **Mock 서버 wss 지원**: 실제 TLS 테스트용 (선택)

---

## 문서·배포

- [ ] **API 문서화**: docstring 보완, Sphinx/Read the Docs 검토
- [ ] **PyPI 배포**: `wss-mqtt-client` 패키지 공개 (버전 0.2.0 등)

---

## 인프라

- [ ] **WSS-MQTT API 게이트웨이 구현**: 현재는 Mock 서버만 존재. 실제 게이트웨이 서버 개발

---

## 참고 (완료된 항목)

- [x] SDK 기반 구현 (publish, subscribe, unsubscribe)
- [x] Mock 서버 및 통합 테스트
- [x] 발행/구독 예제 및 실행 가이드
- [x] 가상환경, requirements.txt, 프로젝트 루트 README
