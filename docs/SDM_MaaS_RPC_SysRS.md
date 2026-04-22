# SDM MaaS RPC — 시스템 요구사항 (개발 단계 정리)

> 본 저장소(**wss-mqtt-api**)는 **MQTT 5.0**과 **WMT / WMO** 토픽 규격에 집중한다.  
> 과거 버전에 포함되었던 특정 클라우드 IoT 플랫폼 전제의 장문 시스템 서술은 제거되었다.  
> 제품·운영 환경별 브로커 선택, 인증 방식, 배포 토폴로지는 별도로 정의한다.

## 단일 출처 문서

| 문서 | 내용 |
|------|------|
| [TOPIC_AND_ACL_SPEC.md](TOPIC_AND_ACL_SPEC.md) | 토픽 구조, ACL, 페이로드 `action`, Reason Code |
| [RPC_DESIGN.md](RPC_DESIGN.md) | RPC 패턴 A~E, MQTT 5.0 Properties 활용 |
| [RPC 패턴.md](RPC%20패턴.md) | 패턴별 시퀀스 다이어그램 |
| [RPC 보안정책.md](RPC%20보안정책.md) | 인증·인가 개념(브로커 중립) |
| [SDK 설계요구사양서.md](SDK%20설계요구사양서.md) | `maas-client-sdk` / `maas-server-sdk` 요구사항 |

## SDK

- 클라이언트: `SDK/client/python/maas-client-sdk/README.md`
- 서버: `SDK/server/python/maas-server-sdk/README.md`

## 범위

- **프로토콜:** MQTT 5.0 (TCP / TLS / WebSocket Secure 등 전송은 브로커·배포에 따름)
- **애플리케이션 RPC:** [TOPIC_AND_ACL_SPEC.md](TOPIC_AND_ACL_SPEC.md)의 WMT 요청 / WMO 응답·이벤트
- **구현:** Python SDK 및 예제(`SDK/examples/`)

이전에 본 문서에 실렸던 인프라별(호스팅·벤더) 세부 항목이 필요하면 저장소 히스토리를 참고한다.
