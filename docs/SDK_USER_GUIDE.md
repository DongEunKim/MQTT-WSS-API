# WSS-MQTT 클라이언트 SDK 사용 설명서

> WSS-MQTT API 게이트웨이 및 MQTT 브로커와 통신하는 Python 클라이언트 SDK의 사용법을 설명합니다.

---

## 목차

1. [개요](#1-개요)
2. [설치 및 요구사항](#2-설치-및-요구사항)
3. [빠른 시작](#3-빠른-시작)
4. [클라이언트 선택 가이드](#4-클라이언트-선택-가이드)
5. [WssMqttClient (동기)](#5-wssmqttclient-동기)
6. [WssMqttClientAsync (비동기)](#6-wssmqttclientasync-비동기)
7. [Transport 옵션](#7-transport-옵션)
8. [인증](#8-인증)
9. [에러 처리](#9-에러-처리)
10. [고급 기능](#10-고급-기능)
11. [예제 실행](#11-예제-실행)
12. [API 참조](#12-api-참조)

---

## 1. 개요

### 1.1 SDK 역할

WSS-MQTT 클라이언트 SDK는 다음을 지원합니다.

- **WSS-MQTT API 게이트웨이** 경유: WebSocket으로 API 서버에 연결하여 MQTT 브로커와 통신
- **MQTT 브로커 직접 연결**: TCP 또는 WebSocket으로 Mosquitto, AWS IoT Core 등에 직접 연결

### 1.2 두 가지 클라이언트

| 클래스 | 용도 | 특징 |
|--------|------|------|
| **WssMqttClient** | 기본, 동기 | `asyncio` 불필요, 콜백 기반 구독, 발행·수신 단순 흐름 |
| **WssMqttClientAsync** | 고급, 비동기 | `async/await`, 스트리밍, 다중 구독, 자동 재연결 |

---

## 2. 설치 및 요구사항

### 2.1 설치

```bash
# PyPI (배포 시)
pip install wss-mqtt-client

# 로컬 개발 (프로젝트 루트)
pip install -e SDK
```

### 2.2 요구사항

- **Python 3.8+**
- **websockets** >= 12.0 (필수)
- **paho-mqtt** (MQTT transport 사용 시)
- **msgpack** (MessagePack 발송 시, 선택)

---

## 3. 빠른 시작

### 3.1 발행 (동기)

```python
from wss_mqtt_client import WssMqttClient

with WssMqttClient(
    url="wss://api.example.com/v1/messaging",
    token="your_jwt_token",
) as client:
    client.publish("tgu/device_001/command", {"action": "start"})
```

### 3.2 구독 (동기, 콜백)

```python
def on_message(event):
    print("수신:", event.payload)

with WssMqttClient(url=URL, token=TOKEN) as client:
    client.subscribe("tgu/device_001/response", callback=on_message)
    client.run_forever()  # Ctrl+C로 종료
```

### 3.3 비동기 (async)

```python
import asyncio
from wss_mqtt_client import WssMqttClientAsync

async def main():
    async with WssMqttClientAsync(url=URL, token=TOKEN) as client:
        await client.publish("topic/command", {"action": "ping"})
        async with client.subscribe("topic/response") as stream:
            async for event in stream:
                print(event.payload)
                break

asyncio.run(main())
```

---

## 4. 클라이언트 선택 가이드

| 사용 시나리오 | 권장 클라이언트 |
|---------------|-----------------|
| 단순 발행, 1~2개 토픽 구독 | WssMqttClient (동기) |
| 콜백 기반 수신, 스크립트형 앱 | WssMqttClient (동기) |
| 다중 토픽 동시 구독, 스트리밍 | WssMqttClientAsync |
| async/await 기반 앱과 통합 | WssMqttClientAsync |
| 연결 끊김 시 자동 재연결 | WssMqttClientAsync |
| 배치 발행(`publish_many`) | WssMqttClientAsync |

---

## 5. WssMqttClient (동기)

### 5.1 연결 방식

**Context manager (권장)**

```python
with WssMqttClient(url=URL) as client:
    client.publish("topic", {"data": 1})
# 종료 시 자동 disconnect
```

**수동 connect/disconnect**

```python
client = WssMqttClient(url=URL)
client.connect()
client.publish("topic", {"data": 1})
client.disconnect()
```

### 5.2 발행

```python
with WssMqttClient(url=URL) as client:
    # dict → JSON 직렬화
    client.publish("sensor/data", {"temp": 25.5, "humidity": 60})

    # bytes → MessagePack 직렬화 (msgpack 패키지 필요)
    client.publish("binary/topic", b"raw_bytes")
```

### 5.3 구독 (콜백)

```python
def on_message(event):
    """event: SubscriptionEvent (topic, payload, req_id)"""
    print(f"[{event.topic}] {event.payload}")

with WssMqttClient(url=URL) as client:
    client.subscribe("topic/response", callback=on_message)

    # 무한 대기 (Ctrl+C로 종료)
    client.run_forever()

    # 또는 제한 시간 대기
    # client.run(timeout=30)  # 30초
```

### 5.4 다중 구독

```python
with WssMqttClient(url=URL) as client:
    client.subscribe("device/001/response", callback=on_msg_001)
    client.subscribe("device/002/response", callback=on_msg_002)
    client.run_forever()
```

### 5.5 disconnect 시 구독 해제

```python
client.disconnect(unsubscribe_first=True)
```

---

## 6. WssMqttClientAsync (비동기)

### 6.1 기본 사용

```python
async with WssMqttClientAsync(url=URL, token=TOKEN) as client:
    await client.publish("topic/command", {"action": "status"})
    async with client.subscribe("topic/response") as stream:
        async for event in stream:
            print(event.payload)
            break
```

### 6.2 배치 발행

```python
results = await client.publish_many([
    ("topic/a", {"id": 1}),
    ("topic/b", {"id": 2}),
    ("topic/c", {"id": 3}),
])
for topic, payload, err in results:
    if err:
        print(f"실패: {topic} - {err}")
    else:
        print(f"성공: {topic}")
```

### 6.3 다수 토픽 구독

```python
async with client.subscribe_many(["topic/1", "topic/2", "topic/3"]) as stream:
    async for event in stream:
        print(f"[{event.topic}] {event.payload}")
```

### 6.4 자동 재연결

```python
client = WssMqttClientAsync(
    url=URL,
    auto_reconnect=True,
    reconnect_max_attempts=10,
)
async with client:
    async with client.subscribe("topic") as stream:
        async for event in stream:
            print(event.payload)
# 연결 끊김 시 exponential backoff로 재연결
# 구독 자동 복구 (auto_resubscribe)
```

---

## 7. Transport 옵션

### 7.1 wss-mqtt-api (기본)

API 게이트웨이를 경유하여 MQTT 브로커와 통신.

```python
client = WssMqttClient(
    url="wss://api.example.com/v1/messaging",
    token="jwt",
    transport="wss-mqtt-api",  # 기본값
)
```

### 7.2 mqtt (네이티브 MQTT)

Mosquitto, AWS IoT Core 등 MQTT 브로커에 직접 연결.

```python
# TCP (로컬 Mosquitto)
client = WssMqttClient(
    url="mqtt://localhost:1883",
    transport="mqtt",
)

# WebSocket (AWS IoT Core 등)
client = WssMqttClient(
    url="wss://xxx.iot.amazonaws.com/mqtt",
    transport="mqtt",
)
```

### 7.3 URL 형식

| transport | URL 예시 |
|-----------|----------|
| wss-mqtt-api | `wss://api.example.com/v1/messaging` |
| mqtt | `mqtt://localhost:1883` (TCP) |
| mqtt | `ws://localhost:9001` (WebSocket) |
| mqtt | `wss://xxx.iot.amazonaws.com/mqtt` |

---

## 8. 인증

### 8.1 토큰 전달 방식

**Authorization 헤더 (기본)**

```python
client = WssMqttClient(url="wss://...", token="jwt")
```

**쿼리 파라미터**

```python
client = WssMqttClient(
    url="wss://...",
    token="jwt",
    use_query_token=True,
)
```

### 8.2 토큰 없이 연결

Mock 서버 등 토큰이 필요 없는 환경:

```python
client = WssMqttClient(url="ws://localhost:8765")
```

---

## 9. 에러 처리

### 9.1 주요 예외

| 예외 | 설명 |
|------|------|
| `WssConnectionError` | 연결 실패, 연결 끊김 |
| `AckError` | 서버 거부 (403, 422 등). `e.code`, `e.payload` |
| `AckTimeoutError` | ACK 타임아웃. `e.req_id` |
| `SubscriptionTimeoutError` | 구독 수신 타임아웃 |

### 9.2 동기 예외 처리

```python
from wss_mqtt_client import WssMqttClient, AckError, AckTimeoutError

try:
    with WssMqttClient(url=URL) as client:
        client.publish("topic", {"data": 1})
except AckError as e:
    print(f"서버 거부: code={e.code}, payload={e.payload}")
except AckTimeoutError as e:
    print(f"ACK 타임아웃: req_id={e.req_id}")
```

### 9.3 비동기 예외 처리

```python
try:
    async with WssMqttClientAsync(url=URL) as client:
        async with client.subscribe("topic") as stream:
            async for event in stream:
                ...
except WssConnectionError as e:
    print(f"연결 오류: {e}")
```

---

## 10. 고급 기능

### 10.1 토픽 검증

기본적으로 토픽 형식 검증이 활성화됩니다. 와일드카드(`+`, `#`) 및 NUL 문자는 거부됩니다.

```python
# 검증 비활성화
client = WssMqttClient(url=URL, validate_topic=False)

# 수동 검증
from wss_mqtt_client import validate_topic

validate_topic("my/topic")   # OK
validate_topic("sensor/+")   # ValueError
```

### 10.2 MessagePack 발송

payload가 `bytes`이면 MessagePack으로 직렬화됩니다. `msgpack` 패키지가 필요합니다.

```python
client.publish("topic", b"binary_payload")
```

### 10.3 구조화 로깅

```python
import structlog
import logging

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
)
client = WssMqttClient(url=URL, logger=logging.getLogger(__name__))
```

### 10.4 구독 큐 크기

```python
# 동기: subscribe의 queue_maxsize
client.subscribe("topic", callback=fn, queue_maxsize=1000)

# 비동기: subscribe의 queue_maxsize
async with client.subscribe("topic", queue_maxsize=1000) as stream:
    ...
```

---

## 11. 예제 실행

### 11.1 Mock 서버 기반 테스트

```bash
# 터미널 1: Mock 서버
python SDK/examples/run_mock_server.py  # Mock 서버

# 터미널 2: 구독
python SDK/wss-mqtt-client/examples/subscriber.py

# 터미널 3: 발행
python SDK/wss-mqtt-client/examples/publisher.py
```

### 11.2 MQTT 브로커 (Docker)

```bash
cd SDK && docker compose up -d

python SDK/wss-mqtt-client/examples/mqtt_subscriber.py   # 터미널 1
python SDK/wss-mqtt-client/examples/mqtt_publisher.py    # 터미널 2
```

### 11.3 예제 목록

| 예제 | 설명 |
|------|------|
| publisher.py | 기본 발행 (동기) |
| subscriber.py | 기본 구독 (동기) |
| publisher_async.py | 비동기 발행 |
| subscriber_async.py | 비동기 구독 (자동 재연결 옵션) |
| basic_publish_subscribe.py | 발행→구독→수신 흐름 (동기) |
| batch_publish_subscribe.py | 배치 발행·다수 구독 |
| rpc_pattern.py | RPC 패턴 |
| mqtt_publisher.py | MQTT 브로커 발행 |
| mqtt_subscriber.py | MQTT 브로커 구독 |

자세한 실행 방법은 `SDK/examples/README.md`를 참고하세요. (예제 경로: `SDK/wss-mqtt-client/examples/`)

---

## 12. API 참조

### 12.1 WssMqttClient (동기)

| 메서드 | 설명 |
|--------|------|
| `connect()` | 연결 (블로킹) |
| `disconnect(unsubscribe_first=False)` | 연결 종료 |
| `publish(topic, payload)` | 발행 |
| `subscribe(topic, callback, queue_maxsize?)` | 구독 등록 |
| `run_forever()` | 수신 루프 (무한) |
| `run(timeout=초)` | 수신 루프 (제한 시간) |

### 12.2 WssMqttClientAsync (비동기)

| 메서드 | 설명 |
|--------|------|
| `connect()` | WebSocket 연결 |
| `disconnect(unsubscribe_first?)` | 연결 종료 |
| `publish(topic, payload)` | 토픽 발행 |
| `publish_many(topic_payloads, stop_on_error?)` | 다수 토픽 발행 |
| `subscribe(topic, timeout?, queue_maxsize?)` | 토픽 구독 |
| `subscribe_many(topics, timeout?, queue_maxsize?)` | 다수 토픽 구독 |
| `unsubscribe(topic)` | 구독 해제 |

### 12.3 공통 생성자 인자

| 인자 | 기본값 | 설명 |
|------|--------|------|
| `url` | - | API/MQTT URL |
| `token` | None | JWT 또는 API 키 |
| `transport` | "wss-mqtt-api" | "wss-mqtt-api" 또는 "mqtt" |
| `use_query_token` | False | 토큰을 쿼리 파라미터로 전달 |
| `validate_topic` | True | 토픽 형식 검증 |
| `topic_max_length` | 512 | 토픽 최대 길이 |
| `logger` | None | 로거 인스턴스 |

### 12.4 SubscriptionEvent

| 속성 | 타입 | 설명 |
|------|------|------|
| `topic` | str | 토픽 |
| `payload` | Any | 페이로드 (dict, list, str, bytes 등) |
| `req_id` | str | 구독 요청 ID |

---

## 참고 문서

- [시스템 사양서](system_specification_v1.md) - WSS-MQTT API 프로토콜
- [SDK README](../SDK/README.md) - 패키지 개요
- [예제 실행 가이드](../SDK/examples/README.md) - 예제 실행 방법
