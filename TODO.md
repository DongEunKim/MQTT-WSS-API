# 진행 예정 작업 (TODO)

> 프로젝트 루트 기준. 우선순위는 상황에 따라 조정.

---

## SDK 개선

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
