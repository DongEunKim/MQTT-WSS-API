# 문서

프로젝트 이해 및 연동에 필요한 문서 목록.

## SDK 문서

| 문서 | 용도 |
|------|------|
| [RPC_DESIGN.md](RPC_DESIGN.md) | MQTT 5.0 기반 RPC 설계 (패턴 A~E, 내부 메커니즘) |
| [TOPIC_AND_ACL_SPEC.md](TOPIC_AND_ACL_SPEC.md) | 토픽 구조(WMT/WMO), ACL 규격, Reason Code 표준 |
| [RPC 패턴.md](RPC%20패턴.md) | RPC 패턴별 시퀀스 다이어그램 및 설계 표준 |
| [SDK 설계요구사양서.md](SDK%20설계요구사양서.md) | Client SDK / Server SDK 기능 요구사양 |

## 시스템 문서

| 문서 | 용도 |
|------|------|
| [SDM_MaaS_RPC_SysRS.md](SDM_MaaS_RPC_SysRS.md) | SDM MaaS 전체 시스템 요구사양서 |
| [MQTT Bridge.md](MQTT%20Bridge.md) | SDM 내 MQTT 브리지 인프라 정의 |
| [RPC 보안정책.md](RPC%20보안정책.md) | RPC 인증/인가 보안 정책 |

## SDK 패키지

| 패키지 | 경로 | 용도 |
|--------|------|------|
| `maas-client-sdk` | `SDK/client/python/maas-client-sdk/` | RPC 클라이언트 SDK (클라이언트 앱용) |
| `maas-server-sdk` | `SDK/server/python/maas-server-sdk/` | RPC 서비스 서버 SDK (Greengrass Component 등) |

예제 실행 방법은 [SDK/examples/README.md](../SDK/examples/README.md) 참고.
