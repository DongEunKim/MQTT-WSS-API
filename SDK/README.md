# SDK

WSS-MQTT API 클라이언트 및 MaaS RPC SDK 모음.

## 패키지 구성

| 패키지 | 경로 | 설명 |
|--------|------|------|
| **wss-mqtt-client** | `client/python/wss-mqtt-client/` | WSS-MQTT API / MQTT 브로커 클라이언트 |
| **maas-rpc-client-sdk** | `client/python/maas-rpc-client-sdk/` | MaaS RPC 클라이언트 (wss-mqtt-client 의존) |

> 각 패키지의 개별 설치 방법은 패키지 디렉터리 안의 `README.md`를 참고하세요.

## 전체 설치 (워크스페이스 루트 기준, 개발용)

```bash
# 의존 순서대로 설치
pip install -e SDK/client/python/wss-mqtt-client[dev]
pip install -e SDK/client/python/maas-rpc-client-sdk
```

## 예제 실행

Mock 서버와 클라이언트 예제는 [examples/README.md](examples/README.md) 참고.

## 문서

- [SDK 사용 설명서](../docs/SDK_USER_GUIDE.md) - wss-mqtt-client 상세 사용법
- [문서 목록](../docs/README.md) - 사양·가이드·설계 문서
