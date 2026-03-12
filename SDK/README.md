# WSS-MQTT 클라이언트 SDK for Python

WSS-MQTT API 게이트웨이와 통신하여 TGU(Telematics Gateway Unit) 및 MQTT 브로커와 토픽 기반 publish/subscribe로 메시지를 주고받는 Python 클라이언트 SDK입니다.

## 설치

```bash
# PyPI (배포 시)
pip install wss-mqtt-client

# 로컬 개발 (패키지 디렉터리에서)
pip install -e .
```

## 요구 사항

- Python 3.8+
- websockets >= 12.0

## 사용법

### 기본 예제

```python
import asyncio
from wss_mqtt_client import WssMqttClient

async def main():
    async with WssMqttClient(
        url="wss://api.example.com/v1/messaging",
        token="your_jwt_token",
    ) as client:
        # TGU에 제어 명령 발행
        await client.publish("tgu/device_001/command", {"action": "start"})

        # 응답 구독 및 수신 (RPC 패턴)
        async with client.subscribe("tgu/device_001/response") as stream:
            async for event in stream:
                print("수신:", event.payload)
                break  # 1건 수신 후 종료

asyncio.run(main())
```

### subscribe() 사용 시 주의사항

- **TTL 40초:** 게이트웨이 구독 TTL이 40초이므로, 응답 토픽 구독은 **제어 명령 발행 직전**에 수행하는 것을 권장합니다.
- **Context Manager 필수:** `subscribe()`는 반드시 `async with`로 사용하세요. 벗어날 때 자동으로 UNSUBSCRIBE가 전송됩니다.

### 토큰 전달 방식

```python
# 헤더 (권장)
client = WssMqttClient(url="wss://...", token="jwt")

# 쿼리 파라미터
client = WssMqttClient(
    url="wss://...",
    token="jwt",
    use_query_token=True,
)
```

### 에러 처리

```python
from wss_mqtt_client import WssMqttClient, AckError, AckTimeoutError

try:
    await client.publish("topic", {"data": 1})
except AckError as e:
    print(f"서버 거부: code={e.code}, payload={e.payload}")
except AckTimeoutError as e:
    print(f"ACK 타임아웃: req_id={e.req_id}")
```

## API 요약

| 메서드 | 설명 |
|--------|------|
| `connect()` | WebSocket 연결 |
| `disconnect()` | 연결 종료 |
| `publish(topic, payload)` | 토픽에 메시지 발행 |
| `subscribe(topic, timeout?)` | 토픽 구독 (context manager + async iterator) |
| `unsubscribe(topic)` | 토픽 구독 해제 |

## 라이선스

MIT
