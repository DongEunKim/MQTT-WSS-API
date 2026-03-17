# MaaS RPC Client SDK — Python

이 폴더에는 MaaS RPC 클라이언트를 위한 Python 패키지 두 개가 포함되어 있습니다.

```
python/
├── wss-mqtt-client/        # 전송 인프라 (WSS-MQTT API / MQTT 브로커 클라이언트)
└── maas-rpc-client-sdk/    # MaaS RPC 클라이언트 (wss-mqtt-client 의존)
```

> Python 3.8 이상이 필요합니다.

## 설치

### 방법 1 — 스크립트 (권장)

이 폴더(`python/`) 안에서 실행합니다.

```bash
bash install.sh              # 기본 설치
bash install.sh --msgpack    # msgpack 직렬화 포함
bash install.sh --dev        # 개발 의존성 포함 (pytest 등)
```

### 방법 2 — 직접 설치

`wss-mqtt-client`가 의존 패키지이므로 **순서대로** 설치해야 합니다.

```bash
# 이 폴더(python/) 안에서 실행
pip install -e ./wss-mqtt-client
pip install -e ./maas-rpc-client-sdk
```

## 빠른 사용법

```python
from maas_rpc_client import RpcClient

with RpcClient(
    url="wss://api.example.com/v1/messaging",
    token="your_jwt_token",
    vehicle_id="device_001",
    transport="wss-mqtt-api",
) as client:
    result = client.call("RemoteUDS", {"action": "readDTC"})
    print(result)
```

상세 사용법은 각 패키지의 `README.md`를 참고하세요.

- `wss-mqtt-client/README.md` — WSS-MQTT 클라이언트 사용법
- `maas-rpc-client-sdk/README.md` — MaaS RPC 클라이언트 사용법
