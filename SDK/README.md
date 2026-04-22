# SDK

MQTT 5.0 기반 **MaaS Client SDK** 및 **MaaS Server SDK** (Python 3.10+).

## 패키지

| 패키지 | 경로 | 설명 |
|--------|------|------|
| **maas-client-sdk** | [`client/python/maas-client-sdk/`](client/python/maas-client-sdk/) | 클라이언트 앱용 — 사용법은 패키지 [**README**](client/python/maas-client-sdk/README.md) |
| **maas-server-sdk** | [`server/python/maas-server-sdk/`](server/python/maas-server-sdk/) | 서비스 구현용 — 사용법은 패키지 [**README**](server/python/maas-server-sdk/README.md) |

별도 Envelope 프로토콜 없이 MQTT 5.0 `Response Topic`, `Correlation Data`, `User Properties`를 사용한다.

## 설치 (개발)

```bash
pip install -e SDK/client/python/maas-client-sdk[dev]
pip install -e SDK/server/python/maas-server-sdk[dev]
```

또는 저장소 루트에서 `pip install -r requirements.txt`.

각 언어 디렉터리의 `install.sh`로도 동일하게 editable 설치할 수 있다. 저장소 루트 기준 예:

```bash
bash SDK/client/python/install.sh --dev
bash SDK/server/python/install.sh --dev
```

## 문서

- [maas-client-sdk 사용법](client/python/maas-client-sdk/README.md) · [maas-server-sdk 사용법](server/python/maas-server-sdk/README.md)
- [RPC 설계](../docs/RPC_DESIGN.md) — 패턴 A~E, 내부 메커니즘
- [토픽·ACL 규격](../docs/TOPIC_AND_ACL_SPEC.md) — WMT/WMO 토픽 구조
- [문서 목록](../docs/README.md)

## 예제

로컬 브로커·통합 테스트는 [examples/README.md](examples/README.md)를 참고한다.
