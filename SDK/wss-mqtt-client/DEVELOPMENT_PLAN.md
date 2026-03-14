# WSS-MQTT 클라이언트 SDK for Python 개발 계획

> **기준 문서:** `docs/system_specification_v1.md`  
> **목표:** 클라이언트가 TGU 및 MQTT 브로커와 통신하는 것처럼 추상화된 Python SDK 제공

---

## 1. SDK 설계 목표

### 1.1 핵심 가치

- **추상화:** WSS 프로토콜, Envelope, req_id 상관관계 등을 내부에 숨기고, 개발자는 **토픽 기반 publish/subscribe** 인터페이스만 사용
- **TGU 연동 패턴:** 제어 명령 발행 → 응답 토픽 구독 → 응답 수신 흐름을 직관적인 API로 지원
- **안정성:** 사양서의 타임아웃·재연결·에러 처리 정책 준수

### 1.2 사용자 시나리오 예시

```python
# 목표: 개발자가 아래처럼 간단히 사용
# 기본(동기): WssMqttClient
from wss_mqtt_client import WssMqttClient

with WssMqttClient(url="wss://...", token="jwt") as client:
    client.publish("tgu/device_001/command", {"action": "start"})

# 고급(비동기): WssMqttClientAsync
from wss_mqtt_client import WssMqttClientAsync
import asyncio

async def main():
    async with WssMqttClientAsync(url="wss://...", token="jwt") as client:
        await client.publish("tgu/device_001/command", {"action": "start"})
        async with client.subscribe("tgu/device_001/response") as stream:
            async for msg in stream:
                print(msg.payload)
                break
asyncio.run(main())
```

---

## 2. 아키텍처 개요

### 2.1 계층 구조

```
┌─────────────────────────────────────────────────────────────┐
│  Public API (고수준)                                          │
│  - connect(), disconnect()                                   │
│  - publish(topic, payload)                                   │
│  - subscribe(topic) → AsyncIterator[SubscriptionEvent]       │
│  - unsubscribe(topic)                                        │
│  - [선택] request_response(topic, payload, response_topic)    │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│  내부 추상화 계층                                             │
│  - req_id 생성/관리, ACK 대기열                               │
│  - SUBSCRIPTION 라우팅 (req_id → 콜백/AsyncQueue)              │
│  - 타임아웃 처리 (5초 ACK, 30초 RPC 응답)                     │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│  프로토콜 계층 (저수준)                                        │
│  - Envelope 직렬화/역직렬화 (JSON, MessagePack)               │
│  - Request 전송 (PUBLISH, SUBSCRIBE, UNSUBSCRIBE)             │
│  - ACK/SUBSCRIPTION 파싱 및 분배                              │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│  전송 계층                                                    │
│  - WebSocket Secure (wss) 연결                               │
│  - 인증 (Bearer Token / Query Param)                         │
│  - Ping/Pong, 재연결 정책                                    │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 모듈 구조 (제안)

```
SDK/
├── pyproject.toml              # 프로젝트 메타데이터, 의존성
├── README.md
├── DEVELOPMENT_PLAN.md         # 본 문서
├── wss_mqtt_client/
│   ├── __init__.py             # 공개 API
│   ├── client.py               # WssMqttClientAsync (비동기)
│   ├── client_sync.py          # WssMqttClient (동기 래퍼)
│   ├── transport/              # 전송 계층 (TransportInterface, WssMqttApiTransport)
│   │   ├── base.py             # TransportInterface (Protocol)
│   │   └── wss_mqtt_api.py     # wss-mqtt-api WebSocket 전송
│   ├── protocol.py             # Envelope 직렬화, req_id, 메시지 파싱
│   ├── models.py               # Request, ACK, Subscription 데이터 클래스
│   ├── exceptions.py           # 커스텀 예외 (AckError, TimeoutError 등)
│   └── constants.py            # 에러 코드, 타임아웃 값 등
├── tests/
│   ├── conftest.py             # pytest 픽스처 ( mock WebSocket 등)
│   ├── test_client.py
│   ├── test_protocol.py
│   └── test_transport.py
└── examples/
    ├── basic_publish_subscribe.py
    └── rpc_pattern.py          # 제어 → 응답 토픽 구독 패턴
```

---

## 3. 개발 단계별 계획

### Phase 1: 기반 구축 (Foundation)

| 순서 | 작업 | 상세 내용 |
|------|------|-----------|
| 1.1 | 프로젝트 셋업 | `pyproject.toml`, 가상환경, `wss_mqtt_client` 패키지 생성 |
| 1.2 | `models.py` | `Request`, `ACK`, `Subscription` 데이터 클래스, `Action` enum |
| 1.3 | `constants.py` | ACK 타임아웃(5초), RPC 응답 타임아웃(30초), 에러 코드 상수 |
| 1.4 | `exceptions.py` | `WssMqttError`, `AckError`, `ConnectionError`, `TimeoutError` |
| 1.5 | `protocol.py` | `encode_request()`, `decode_message()`, `req_id` 생성 유틸 |

**산출물:** 메시지 모델, 직렬화/역직렬화, 기본 예외

---

### Phase 2: 전송 계층 (Transport)

| 순서 | 작업 | 상세 내용 |
|------|------|-----------|
| 2.1 | `transport.py` | `websockets` 라이브러리 기반 WSS 클라이언트 |
| 2.2 | 연결 수립 | `wss://[API_DOMAIN]/v1/messaging`, Bearer 토큰/쿼리 인증 |
| 2.3 | 메시지 송수신 | JSON 문자열 전송, 수신 메시지 파싱 및 이벤트 분류 |
| 2.4 | Ping/Pong | `websockets` 기본 Ping/Pong 활용, 연결 유지 |
| 2.5 | 재연결 정책 | 선택적 exponential backoff, 연결 끊김 시 재시도 |

**산출물:** WebSocket 기반 송수신, 인증, 연결 유지

---

### Phase 3: 프로토콜 및 요청-응답 추상화

| 순서 | 작업 | 상세 내용 |
|------|------|-----------|
| 3.1 | req_id 관리 | UUID v4 또는 증가 시퀀스로 요청 식별 |
| 3.2 | ACK 대기열 | `req_id` → `asyncio.Future` 매핑, ACK 수신 시 resolve |
| 3.3 | ACK 타임아웃 | 5초 이내 미수신 시 `TimeoutError` raise |
| 3.4 | SUBSCRIPTION 라우팅 | `req_id`별 구독 핸들러 등록, SUBSCRIPTION 수신 시 콜백/Queue로 전달 |
| 3.5 | RPC 응답 타임아웃 | `subscribe()` + `publish()` 조합 시 30초 타임아웃 (선택 옵션) |

**산출물:** ACK 기반 요청-응답, SUBSCRIPTION 이벤트 라우팅

---

### Phase 4: 고수준 클라이언트 API

| 순서 | 작업 | 상세 내용 |
|------|------|-----------|
| 4.1 | `client.py` | `WssMqttClient` 클래스, `connect()`, `disconnect()` |
| 4.2 | `publish()` | `PUBLISH` 전송, ACK 대기, 에러 시 `AckError` |
| 4.3 | `subscribe()` | `SUBSCRIBE` 전송, `AsyncIterator` 반환하여 `payload` 스트리밍 |
| 4.4 | `unsubscribe()` | `UNSUBSCRIBE` 전송, 구독 해제 |
| 4.5 | 에러 처리 | ACK `code` 4xx/5xx 시 `AckError` + `code`, `payload` 전달 |
| 4.6 | context manager | `async with WssMqttClient(...) as client:` 지원 |

**산출물:** 사용자 친화적 Public API

---

### Phase 5: 부가 기능 및 품질

| 순서 | 작업 | 상세 내용 |
|------|------|-----------|
| 5.1 | MessagePack | 선택적 직렬화 포맷 (의존성: `msgpack`), 설정 플래그 |
| 5.2 | 로깅 | `logging` 연동, 디버그 모드에서 Envelope 로그 |
| 5.3 | 문서화 | docstring, 타입 힌트, README 사용법 |
| 5.4 | 단위 테스트 | `pytest` + `pytest-asyncio`, Mock WebSocket으로 시나리오 검증 |
| 5.5 | 예제 | `basic_publish_subscribe.py`, `rpc_pattern.py` |

**산출물:** 선택적 기능, 테스트, 문서

---

## 4. 의존성

### 필수

| 패키지 | 용도 | 버전 요구 |
|--------|------|-----------|
| `websockets` | WSS 클라이언트 | >= 12.0 (async 지원) |

### 선택

| 패키지 | 용도 |
|--------|------|
| `msgpack` | MessagePack 직렬화 |
| `pytest` | 테스트 |
| `pytest-asyncio` | 비동기 테스트 |

### Python 버전

- **권장:** Python 3.10+
- **최소:** Python 3.8 (typing, async/await)

---

## 5. API 설계 상세

### 5.1 `WssMqttClient` (기본, 동기)

```python
class WssMqttClient:
    """동기 래퍼. 내부적으로 WssMqttClientAsync + asyncio.run 사용."""
    def __init__(self, url: str, token: str | None = None, ...) -> None: ...
    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    def publish(self, topic: str, payload: Any) -> None: ...
    def subscribe(self, topic: str, callback: Callable) -> None: ...
    def run_forever(self) -> None: ...
    def run(self, timeout: float | None = None) -> None: ...
```

### 5.2 `WssMqttClientAsync` (고급, 비동기)

```python
class WssMqttClientAsync:
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def __aenter__(self) -> "WssMqttClientAsync": ...
    async def __aexit__(self, *args) -> None: ...
    async def publish(self, topic: str, payload: Any) -> None: ...
    def subscribe(self, topic: str) -> "SubscriptionStream": ...
    async def unsubscribe(self, topic: str) -> None: ...
```

### 5.3 `SubscriptionStream` (구독 스트림)

- `async for event in client.subscribe(topic):` 형태
- `event`: `payload` (및 필요 시 `req_id`, `topic`)를 포함하는 객체

### 5.4 예외 계층

- `WssMqttError` (기본)
  - `ConnectionError` - 연결 실패/끊김
  - `AckError` - ACK 4xx/5xx (`code`, `payload`)
  - `TimeoutError` - ACK 5초 / RPC 응답 30초 초과

---

## 6. 사양서 매핑

| 사양 항목 | SDK 반영 |
|-----------|----------|
| 4.1 엔드포인트 | `url` 파라미터: `wss://[API_DOMAIN]/v1/messaging` |
| 4.3 인증 | `token` → `Authorization: Bearer` 또는 `?token=` |
| 5.1 직렬화 | JSON(기본), MessagePack(선택) |
| 6.1~6.4 Envelope | `protocol.py`에서 생성/파싱 |
| 7 에러 코드 | `AckError.code`에 400, 401, 403, 422, 504 전달 |
| 8.1 ACK 타임아웃 | `ack_timeout` (기본 5초) |
| 8.2 RPC 응답 타임아웃 | `subscribe()` iterator에 optional `timeout` 파라미터 |
| 8.4 TTL 40초 | 사용자 문서에 "응답 토픽 구독은 제어 발송 직전에" 안내 |

---

## 7. 마일스톤 및 예상 일정

| 마일스톤 | Phase | 예상 기간 |
|----------|-------|-----------|
| M1: 프로토콜·모델·전송 | Phase 1, 2 | 1~2일 |
| M2: 요청-응답·구독 | Phase 3 | 1일 |
| M3: Public API | Phase 4 | 1~2일 |
| M4: 테스트·문서·예제 | Phase 5 | 1일 |

**총 예상:** 4~6일 (1인 기준)

---

## 8. 후속 고려 사항

- ~~동기(Sync) 래퍼~~: ✅ WssMqttClient로 제공 완료
- 재연결 시 구독 자동 복구: 서버 TTL 때문에 재구독 필요 가능성
- 배치 publish/subscribe: 다수 토픽 일괄 처리용 유틸
- 구조화 로깅: `structlog` 등 연동
