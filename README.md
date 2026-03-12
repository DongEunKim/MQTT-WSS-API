# WSS-MQTT API

WebSocket Secure(WSS) 클라이언트와 MQTT 브로커 간 프로토콜 변환 API 프로젝트입니다.

## 프로젝트 구조

```
├── docs/                    # 사양서
│   ├── system_specification_v1.md
│   └── wss-mqtt-message-schema.json
└── SDK/
    └── wss-mqtt-client-sdk-for-python/   # Python 클라이언트 SDK
```

## 개발 환경 설정

프로젝트 루트에서 가상환경을 구축합니다.

```bash
# 가상환경 생성
python3 -m venv .venv

# 활성화 (Linux/macOS)
source .venv/bin/activate

# SDK 설치 (에디터블 모드)
pip install -e SDK/wss-mqtt-client-sdk-for-python

# 또는 requirements.txt 사용
pip install -r requirements.txt
```

이후 `python` 명령으로 SDK 예제 및 테스트를 실행할 수 있습니다.

## Mock 서버 및 예제 실행

`SDK/wss-mqtt-client-sdk-for-python/examples/README.md` 를 참고하세요.

## 진행 예정 작업

추가 예정 기능 및 개선 사항은 [TODO.md](TODO.md) 를 참고하세요.
