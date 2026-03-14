# TODO 1.1 Transport 추상화 상세 계획

> **상태**: ✅ 구현 완료  
> **목표**: WssMqttClient가 transport를 주입받아 교체 가능하도록 추상화.  
> **범위**: MQTT over WSS 구현은 제외, 인터페이스 정의 및 wss-mqtt-api 분리만 수행.

---

## 1. 현재 구조

```
WssMqttClient
    └── Transport (concrete)  ← websockets 기반, wss-mqtt-api 프로토콜 하드코딩
            ├── connect(), disconnect()
            ├── send(data), receive_loop()
            ├── set_receive_callback()
            └── is_connected
```

**문제점**
- Transport와 WssMqttClient가 강결합
- MQTT over WSS 등 다른 transport 추가 시 기존 로직 수정 필요

---

## 2. 목표 구조

```
WssMqttClient
    └── TransportInterface (Protocol)
            ↑
            ├── WssMqttApiTransport  ← 기존 Transport 로직 (websockets)
            └── MqttOverWssTransport ← 추후 1.3에서 구현
```

---

## 3. 작업 항목 (순서)

### 3.1 TransportInterface (Protocol) 정의

**파일**: `wss_mqtt_client/transport/base.py` (신규)

**인터페이스 시그니처**:

```python
from typing import Any, Callable, Protocol, runtime_checkable

@runtime_checkable
class TransportInterface(Protocol):
    """전송 계층 프로토콜. WssMqttClient가 요구하는 최소 인터페이스."""

    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def send(self, data: str | bytes) -> None: ...
    def set_receive_callback(self, callback: Callable[[Any], None]) -> None: ...
    async def receive_loop(self) -> None: ...

    @property
    def is_connected(self) -> bool: ...
```

**전달 데이터 규약**
- `send(data)`: `data`는 JSON 문자열 또는 MessagePack 바이너리
- `receive_callback`: `decode_message(raw)` 결과 (AckEvent | SubscriptionEvent) 전달

**디렉터리 구조**
```
wss_mqtt_client/
├── transport/
│   ├── __init__.py    # TransportInterface, WssMqttApiTransport 노출
│   ├── base.py        # TransportInterface (Protocol)
│   └── wss_mqtt_api.py  # WssMqttApiTransport
```

---

### 3.2 기존 Transport → WssMqttApiTransport 분리

**파일**: `wss_mqtt_client/transport/wss_mqtt_api.py` (신규)

**조치**
1. `transport.py`의 `Transport` 클래스 전체를 `WssMqttApiTransport`로 복사
2. 클래스명 변경: `Transport` → `WssMqttApiTransport`
3. `TransportInterface`를 구현 (Protocol 준수)

**이동할 내용**
- `_build_ws_url`, `_build_headers` 헬퍼 함수
- `WssMqttApiTransport` 클래스 전체 (connect, disconnect, send, receive_loop, set_receive_callback, is_connected)

**기존 transport.py**
- 삭제 또는 `from .transport.wss_mqtt_api import WssMqttApiTransport`로 리다이렉트 후 deprecated 경고
- **권장**: transport.py 삭제, `transport/` 패키지로 완전 이전

---

### 3.3 WssMqttClient에 transport 파라미터 추가

**파일**: `wss_mqtt_client/client.py`

**변경 전**
```python
def __init__(
    self,
    url: str,
    token: Optional[str] = None,
    *,
    ack_timeout: float = ACK_TIMEOUT_DEFAULT,
    use_query_token: bool = False,
    logger: Optional[logging.Logger] = None,
) -> None:
    self._transport = Transport(url, token, use_query_token=use_query_token, logger=logger)
```

**변경 후**
```python
def __init__(
    self,
    url: str,
    token: Optional[str] = None,
    *,
    transport: str | TransportInterface = "wss-mqtt-api",
    ack_timeout: float = ACK_TIMEOUT_DEFAULT,
    use_query_token: bool = False,
    logger: Optional[logging.Logger] = None,
) -> None:
    if isinstance(transport, str):
        if transport == "wss-mqtt-api":
            self._transport = WssMqttApiTransport(url, token, use_query_token=use_query_token, logger=logger)
        else:
            raise ValueError(f"알 수 없는 transport: {transport}. 'wss-mqtt-api' 또는 TransportInterface 인스턴스")
    else:
        self._transport = transport
```

**호환성**
- `transport` 미지정 시 `"wss-mqtt-api"` 기본값 → 기존 동작 유지

---

### 3.4 패키지 노출 및 import 경로 정리

**`wss_mqtt_client/transport/__init__.py`**
```python
"""전송 계층. TransportInterface 및 구현체."""

from .base import TransportInterface
from .wss_mqtt_api import WssMqttApiTransport

__all__ = ["TransportInterface", "WssMqttApiTransport"]
```

**`wss_mqtt_client/__init__.py`** (기존)
- `from .transport import Transport` 등 기존 공개 API 유지 여부 결정
- 외부에서 `Transport`를 직접 쓰는 코드가 있다면 `Transport = WssMqttApiTransport` 별칭 또는 deprecated

**`wss_mqtt_client/client.py`**
```python
from .transport import TransportInterface, WssMqttApiTransport
```

---

### 3.5 기존 transport.py 처리

**옵션 A (권장)**: 완전 이전
- `transport.py` 삭제
- 모든 import를 `from .transport import WssMqttApiTransport` 등으로 변경

**옵션 B**: 호환 레이어 유지
- `transport.py`에 `from .transport.wss_mqtt_api import WssMqttApiTransport as Transport` 및 deprecation warning

---

## 4. 검증 포인트

| 항목 | 방법 |
|------|------|
| 기존 동작 유지 | `pytest tests/` 전체 통과 |
| TransportInterface 준수 | `isinstance(transport, TransportInterface)` 체크 (선택) |
| transport="wss-mqtt-api" 기본값 | 별도 지정 없이 기존 예제/테스트 동작 |
| 잘못된 transport 문자열 | `ValueError` 발생 확인 |

---

## 5. 작업 순서 요약

1. `transport/` 디렉터리 생성
2. `transport/base.py` — TransportInterface 정의
3. `transport/wss_mqtt_api.py` — 기존 Transport 로직 이전 및 클래스명 변경
4. `transport/__init__.py` — 노출
5. `client.py` — transport 파라미터 추가, WssMqttApiTransport 사용
6. 기존 `transport.py` 삭제 및 import 경로 수정
7. `tests/` 실행으로 회귀 검증

---

## 6. 추후 확장 (1.3 MQTT over WSS)

> 상세 계획: `docs/TODO_1.3_FEATURE_EXPANSION_PLAN.md`

- `transport="mqtt"` 추가 완료 (MqttTransport)
- `MqttOverWssTransport`는 동일 `TransportInterface` 구현
