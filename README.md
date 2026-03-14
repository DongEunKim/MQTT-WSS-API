# WSS-MQTT API

WebSocket Secure(WSS) 클라이언트와 MQTT 브로커 간 프로토콜 변환 API 프로젝트입니다.

## 프로젝트 구조

```
├── docs/                    # 사양서
│   ├── system_specification_v1.md
│   └── wss-mqtt-message-schema.json
└── SDK/                     # Python SDK
    ├── wss-mqtt-client/     # WSS-MQTT 클라이언트
    ├── tgu-rpc-sdk/         # TGU RPC SDK (준비 중)
    └── examples/            # Mock 서버, 실행 가이드
```

## 개발 환경 설정

프로젝트 루트에서 가상환경을 구축합니다.

```bash
# 가상환경 생성
python3 -m venv .venv

# 활성화 (Linux/macOS)
source .venv/bin/activate

# SDK 설치 (에디터블 모드)
pip install -e SDK/wss-mqtt-client

# 또는 requirements.txt 사용 (개발 의존성 포함)
pip install -r requirements.txt
```

이후 `python` 명령으로 SDK 예제 및 테스트를 실행할 수 있습니다.

## 문서

- [SDK 사용 설명서](docs/SDK_USER_GUIDE.md) - 설치, 사용법, API 참조
- [SDK 예제 실행](SDK/examples/README.md) - Mock 서버 및 예제 실행 방법

### 주요 기능 (SDK)

- **WssMqttClient** (기본, 동기): 콜백 subscribe, `run_forever()`
- **WssMqttClientAsync** (고급, 비동기): async/await, 배치·다중 구독
- **transport**: wss-mqtt-api(기본), mqtt(네이티브 MQTT TCP/WebSocket)
- **MessagePack**: payload bytes 시 직렬화, 수신 자동 파싱
- **자동 재연결**: exponential backoff, 구독 복구 (비동기)

## 진행 예정 작업

추가 예정 기능 및 개선 사항은 [TODO.md](TODO.md) 를 참고하세요.
