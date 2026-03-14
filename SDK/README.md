# SDK

WSS-MQTT API 클라이언트 및 TGU RPC SDK 모음.

## 패키지 구성

| 패키지 | 경로 | 설명 |
|--------|------|------|
| **wss-mqtt-client** | `wss-mqtt-client/` | WSS-MQTT API / MQTT 브로커 클라이언트 |
| **tgu-rpc-sdk** | `tgu-rpc-sdk/` | TGU RPC 클라이언트 (wss-mqtt-client 의존) |

## 설치

```bash
# wss-mqtt-client (필수)
pip install -e SDK/wss-mqtt-client

# tgu-rpc-sdk (선택)
pip install -e SDK/tgu-rpc-sdk
```

## 통합 설치 (개발용)

```bash
pip install -e SDK/wss-mqtt-client[dev]
pip install -e SDK/tgu-rpc-sdk
```

## 예제 실행

Mock 서버와 클라이언트 예제는 [examples/README.md](examples/README.md) 참고.

## 문서

- [SDK 사용 설명서](../docs/SDK_USER_GUIDE.md) - wss-mqtt-client 상세 사용법
- [구조 분리 검토](../docs/SDK_RESTRUCTURE_REVIEW.md) - 패키지 구조 설계
