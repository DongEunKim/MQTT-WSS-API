# TGU RPC SDK

TGU(Telematics Gateway Unit) 서비스/API 명세만으로 RPC를 쉽게 구현할 수 있는 SDK.

wss-mqtt-client 위에 구축되며, 표준화된 토픽 패턴과 RPC 인터페이스를 제공합니다.

## 상태

**Pre-Alpha** — 골격만 구성됨. Phase 3 이후 구현 예정.

## 설치

```bash
# wss-mqtt-client 의존성 포함
pip install -e SDK/tgu-rpc-sdk

# 로컬 개발 시 wss-mqtt-client 먼저 설치
pip install -e SDK/wss-mqtt-client
pip install -e SDK/tgu-rpc-sdk
```

## 예정 API

```python
from tgu_rpc import TguRpcClient

async with TguRpcClient(url=URL, token=TOKEN, vehicle_id="v001") as client:
    result = await client.call("RemoteUDS", "readDTC", {"source": 0x01})
```
