# 진행 예정 작업 (TODO)

> **현행 스택:** MQTT 5.0 네이티브 RPC — `maas-client-sdk`, `maas-server-sdk` (Envelope·WSS-MQTT API 게이트웨이 없음).  
> 설계: [docs/RPC_DESIGN.md](docs/RPC_DESIGN.md), [docs/TOPIC_AND_ACL_SPEC.md](docs/TOPIC_AND_ACL_SPEC.md)

## 단기

- [ ] 클라이언트: JWT 자동 갱신·재연결 시 `pending` RPC 정책 보강
- [ ] 서버: X.509 / Greengrass TES 연동 옵션
- [ ] 양 SDK: 연결 끊김 시 스트림·pending 일괄 정리 (문서화된 동작과 일치 검증)
- [ ] 예제: AWS IoT Core 연동 샘플(토큰·엔드포인트는 환경변수)

## 중기

- [ ] 패턴 C 스트리밍: 대용량 페이로드·백압 정책
- [ ] API 문서(Sphinx 등) 및 PyPI 배포 검토

---

이전 `wss-mqtt-client` / `maas-rpc-client-sdk`(Envelope 기반) 로드맵은 아키텍처 전환으로 폐기되었다.
