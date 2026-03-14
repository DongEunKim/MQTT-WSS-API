# WSS-MQTT 클라이언트 SDK for Python

WSS-MQTT API 게이트웨이와 통신하여 TGU(Telematics Gateway Unit) 및 MQTT 브로커와 토픽 기반 publish/subscribe로 메시지를 주고받는 Python 클라이언트 SDK입니다.

**기본**: `WssMqttClient` (동기). **고급**: `WssMqttClientAsync` (비동기).

📖 상세 사용법: [SDK 사용 설명서](../../docs/SDK_USER_GUIDE.md)

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

### 기본 예제 (WssMqttClient, 동기)

```python
from wss_mqtt_client import WssMqttClient

# 발행
with WssMqttClient(
    url="wss://api.example.com/v1/messaging",
    token="your_jwt_token",
) as client:
    client.publish("tgu/device_001/command", {"action": "start"})

# 구독 (콜백)
def on_message(event):
    print("수신:", event.payload)

with WssMqttClient(url=URL, token=TOKEN) as client:
    client.subscribe("tgu/device_001/response", callback=on_message)
    client.run_forever()  # Ctrl+C로 종료
```

### WssMqttClient (기본, 동기)

asyncio 없이 사용. paho-mqtt 스타일.

```python
from wss_mqtt_client import WssMqttClient

# context manager
with WssMqttClient(url=URL) as client:
    client.publish("topic/command", {"action": "ping"})

# 수동 connect/disconnect
client = WssMqttClient(url=URL)
client.connect()
client.publish("topic", {"x": 1})
client.disconnect()

# 구독 (콜백 + run)
with WssMqttClient(url=URL) as client:
    client.subscribe("topic/response", callback=on_message)
    client.run(timeout=30)  # 30초 대기
```

### WssMqttClientAsync (고급, 비동기)

스트리밍, 다중 구독, async/await 통합에 적합.

```python
import asyncio
from wss_mqtt_client import WssMqttClientAsync

async def main():
    async with WssMqttClientAsync(url=URL, token=TOKEN) as client:
        await client.publish("topic/command", {"action": "start"})
        async with client.subscribe("topic/response") as stream:
            async for event in stream:
                print(event.payload)
                break

asyncio.run(main())
```

### 배치 발행 및 다수 토픽 구독 (WssMqttClientAsync)

```python
# publish_many, subscribe_many는 Async 전용
async with WssMqttClientAsync(url=URL) as client:
    results = await client.publish_many([
        ("topic/a", {"n": 1}),
        ("topic/b", {"n": 2}),
    ])
    async with client.subscribe_many(["topic/1", "topic/2"]) as stream:
        async for event in stream:
            print(f"[{event.topic}] {event.payload}")
```

### 토픽 형식 검증

```python
from wss_mqtt_client import WssMqttClient, validate_topic

# 검증 비활성화
client = WssMqttClient(url=URL, validate_topic=False)

# 수동 검증
validate_topic("my/topic")  # OK
validate_topic("sensor/+")  # ValueError
```

### Transport 옵션

```python
# wss-mqtt-api (기본값)
client = WssMqttClient(url="wss://...", token="jwt")

# MQTT 브로커 (TCP 또는 WebSocket)
client = WssMqttClient(url="mqtt://localhost:1883", transport="mqtt")
client = WssMqttClient(url="ws://localhost:9001", transport="mqtt")
```

### 토큰 전달

```python
# 헤더 (기본)
client = WssMqttClient(url="wss://...", token="jwt")

# 쿼리 파라미터
client = WssMqttClient(url="wss://...", token="jwt", use_query_token=True)
```

### 에러 처리 (동기)

```python
from wss_mqtt_client import WssMqttClient, AckError, AckTimeoutError

try:
    with WssMqttClient(url=URL) as client:
        client.publish("topic", {"data": 1})
except AckError as e:
    print(f"서버 거부: code={e.code}")
except AckTimeoutError as e:
    print(f"ACK 타임아웃: {e.req_id}")
```

### MessagePack 발송

payload가 `bytes`이면 MessagePack 직렬화 (msgpack 패키지 필요).

```python
client.publish("topic", b"binary_payload")
```

### 구조화 로깅 (structlog)

```python
import structlog
import logging

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
)
client = WssMqttClient(url=URL, logger=logging.getLogger(__name__))
```

## API 요약

### WssMqttClient (기본, 동기)

| 메서드 | 설명 |
|--------|------|
| `connect()` | 연결 (블로킹) |
| `disconnect(unsubscribe_first?)` | 연결 종료 |
| `publish(topic, payload)` | 발행 (블로킹) |
| `subscribe(topic, callback, queue_maxsize?)` | 구독 등록 (콜백) |
| `run_forever()` | 수신 루프 (무한 대기) |
| `run(timeout=초)` | 수신 루프 (제한 시간 대기) |

### WssMqttClientAsync (고급, 비동기)

| 메서드 | 설명 |
|--------|------|
| `connect()` | WebSocket 연결 |
| `disconnect()` | 연결 종료 |
| `publish(topic, payload)` | 토픽 발행 |
| `publish_many(topic_payloads, stop_on_error?)` | 다수 토픽 순차 발행 |
| `subscribe(topic, timeout?, queue_maxsize?)` | 토픽 구독 (async iterator) |
| `subscribe_many(topics, timeout?, queue_maxsize?)` | 다수 토픽 동시 구독 |
| `unsubscribe(topic)` | 구독 해제 |

### 공통 생성자 인자

| 인자 | 설명 |
|------|------|
| `url` | wss://[API_DOMAIN]/v1/messaging 또는 mqtt://... |
| `token` | JWT 또는 API 키 (선택) |
| `transport` | `"wss-mqtt-api"`(기본), `"mqtt"` |
| `validate_topic` | 토픽 검증 여부 (기본 True) |
| `topic_max_length` | 토픽 최대 길이 (기본 512) |

## 라이선스

MIT
