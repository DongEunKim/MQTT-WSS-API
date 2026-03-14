# TODO 1.3 기능 확장 상세 계획

> **상태**: ✅ 구현 완료  
> **목표**: MessagePack 발송, 재연결 정책, MQTT 지원, publish/subscribe 통일, 동기 래퍼  
> **네이밍**: `transport="mqtt"` — URL scheme으로 TCP vs WebSocket 자동 선택

---

## 1. 작업 항목 개요

| # | 항목 | 우선순위 | 의존성 | 상태 |
|---|------|----------|--------|------|
| 1 | MQTT Transport (TCP + WSS) | 높음 | paho-mqtt | ✅ 완료 |
| 2 | publish/subscribe 인터페이스 통일 | 높음 | 1 | ✅ 완료 |
| 3 | MessagePack 발송 지원 | 중간 | msgpack (선택적) | ✅ 완료 |
| 4 | 재연결 정책 | 중간 | 없음 | ✅ 완료 |
| 5 | 재연결 시 구독 복구 | 중간 | 4 | ✅ 완료 |
| 6 | 동기(Sync) 래퍼 | 낮음 | 없음 | → 1.7로 이관 |

---

## 2. 네이밍: transport="mqtt" (URL 기반)

### 2.1 배경

- **wss-mqtt-api**: 커스텀 Envelope over WebSocket → API 게이트웨이 경유
- **MQTT**: 네이티브 MQTT 프로토콜, URL scheme으로 전송 방식 결정
  - `mqtt://`, `mqtts://` → TCP (로컬 Mosquitto 등)
  - `ws://`, `wss://` → WebSocket (AWS IoT Core, Mosquitto 9001 등)

### 2.2 채택 명칭

| transport | URL 예시 | 실제 전송 |
|-----------|----------|-----------|
| `wss-mqtt-api` | `wss://api/v1/messaging` | 커스텀 API over WebSocket |
| `mqtt` | `mqtt://localhost:1883` | MQTT over TCP |
| `mqtt` | `ws://localhost:9001` | MQTT over WebSocket |
| `mqtt` | `wss://xxx.iot.amazonaws.com/mqtt` | MQTT over WSS (AWS IoT Core 등) |

- `transport="mqtt"` 하나로 순수 MQTT·MQTT over WSS 모두 지원
- AWS IoT Core 등 대부분 클라우드 브로커는 `wss://` 사용

---

## 3. 상세 작업 계획

### 3.1 MessagePack 발송 지원

**현재**
- 수신: protocol._decode_data()에서 bytes → msgpack 우선 (1.2 완료)
- 발송: encode_request()가 JSON만 반환

**목표**
- 사양 5.1: payload가 `bytes`이면 전체 Envelope을 MessagePack 직렬화
- 클라이언트: `publish(topic, payload)` 호출 시 `payload` 타입에 따라 직렬화 선택

**구현 방안**

1. `protocol.py`에 `encode_request_binary(request) -> bytes` 추가 (msgpack 사용)
2. `WssMqttClient.publish()`에서 payload 타입 분기:
   - `payload`가 `bytes` → MessagePack 직렬화, `transport.send(bytes)`
   - 그 외 → 기존 JSON, `transport.send(str)`
3. msgpack 없으면 `bytes` payload 시 `ImportError` 또는 JSON fallback(사양과 다를 수 있음) → **선택**: msgpack 없으면 `TypeError` raise

**파일**
- `protocol.py`: `encode_request_binary()`
- `client.py`: `publish()` 내 직렬화 분기

**의존성**
- msgpack optional. `bytes` payload 사용 시에만 필요.

---

### 3.2 MQTT Transport (MqttTransport) ✅

**목표**
- `transport="mqtt"` 시 paho-mqtt로 MQTT 브로커 직접 연결
- URL scheme으로 TCP vs WebSocket 자동 선택 (순수 MQTT + MQTT over WSS 일괄 지원)

**역할 분담**
- WssMqttClient: 기존대로 build_request, encode_request 사용
- MqttTransport: Envelope ↔ MQTT 프로토콜 변환 어댑터

**동작**
1. `send(data)`: JSON Envelope 파싱 후 action에 따라 paho publish/subscribe/unsubscribe
2. ACK: PUBACK/SUBACK/UNSUBACK → AckEvent 변환 (mid→req_id 매핑)
3. SUBSCRIPTION: MQTT PUBLISH → SubscriptionEvent (topic→req_id 매핑)
4. req_id 매핑: 토픽별 req_id set 유지, 동일 토픽 다중 구독 지원

**URL scheme → paho 전송**
| scheme | paho transport | 비고 |
|--------|----------------|------|
| mqtt | tcp | 기본 1883 |
| mqtts | ssl | 기본 8883 |
| ws | websockets | 기본 80 |
| wss | websockets + tls | 기본 443 |

**파일**
- `transport/mqtt.py`: MqttTransport 클래스
- `transport/__init__.py`: MqttTransport 노출
- `client.py`: `transport=="mqtt"` 분기
- `pyproject.toml`: paho-mqtt 의존성

---

### 3.3 publish/subscribe 인터페이스 통일

**목표**
- 두 transport에서 동일한 시그니처:
  - `publish(topic: str, payload: Any) -> None`
  - `subscribe(topic: str, timeout=None, ...) -> SubscriptionStream`

**현재**
- WssMqttClient가 이미 통일 인터페이스 제공
- Transport는 `send(data)`, `receive_callback` 수준
- MqttOverWssTransport가 Envelope을 해석해 동작하므로 클라이언트 로직 변경 불필요

**검증**
- 두 transport로 동일 테스트 실행
- Mock: wss-mqtt-api는 기존 Mock 서버, mqtt는 실제 MQTT 브로커 (Mosquitto 등)

---

### 3.4 재연결 정책

**목표**
- 연결 끊김 시 exponential backoff로 자동 재연결
- 최대 재시도 횟수, 최대 대기 시간 설정 가능

**구현 방안**
- `WssMqttClient`에 `auto_reconnect: bool = False`, `reconnect_max_attempts`, `reconnect_base_delay`, `reconnect_max_delay` 파라미터
- `receive_loop` 종료(연결 끊김) 감지 시 `_on_connection_lost` 호출 후, `auto_reconnect`이면 백그라운드 태스크에서 재연결 시도
- `connect()` 성공 시 `_receive_task` 재시작

**고려사항**
- `disconnect()` 호출 시에는 재연결하지 않음 (의도적 종료)
- 재연결 중 `publish()` 호출 시: 대기 또는 즉시 실패 선택 가능

**파일**
- `client.py`: 재연결 로직

---

### 3.5 재연결 시 구독 복구

**목표**
- 재연결 후 이전에 구독 중이던 토픽 자동 재구독
- 서버 TTL로 구독이 만료되므로 재연결 시 필수

**구현 방안**
- `_topic_to_req_ids`에 저장된 토픽 목록 유지
- 재연결 성공 시 `auto_resubscribe: bool = True`이면 각 토픽에 대해 SUBSCRIBE 재전송
- 구독 스트림의 queue는 유지. 새 req_id로 핸들러 재등록

**파일**
- `client.py`: `_on_reconnected()` 또는 재연결 성공 후 구독 복구 로직

---

### 3.6 동기(Sync) 래퍼

→ **TODO 1.7 API 사용성 단순화**로 이관.  
`docs/TODO_1.7_API_SIMPLIFICATION_PLAN.md` 참조.

---

## 4. 작업 순서 제안

| 순서 | 항목 | 이유 |
|------|------|------|
| 1 | 3.2 MqttOverWssTransport | 핵심 기능, 다른 항목 기반 |
| 2 | 3.3 인터페이스 통일 검증 | 1과 함께 테스트 |
| 3 | 3.1 MessagePack 발송 | 독립적, 수신은 완료됨 |
| 4 | 3.4 재연결 정책 | wss-mqtt-api에 먼저 적용 |
| 5 | 3.5 재연결 구독 복구 | 4 의존 |
| 6 | 3.6 동기 래퍼 | → 1.7 |

---

## 5. Transport 선택 흐름 (client.py)

```python
if isinstance(transport, str):
    if transport == "wss-mqtt-api":
        self._transport = WssMqttApiTransport(...)
    elif transport == "mqtt":
        self._transport = MqttTransport(url, token, logger=logger)
    else:
        raise ValueError(
            f"알 수 없는 transport: {transport!r}. "
            "'wss-mqtt-api', 'mqtt' 또는 TransportInterface 인스턴스를 사용하세요."
        )
```

---

## 6. MqttTransport 인터페이스 정합성

TransportInterface 준수:

| 메서드/속성 | MqttTransport 구현 |
|-------------|--------------------|
| connect() | paho connect (URL scheme에 따라 tcp/websockets) |
| disconnect() | paho disconnect |
| send(data) | Envelope 파싱 → MQTT PUBLISH/SUBSCRIBE/UNSUBSCRIBE |
| set_receive_callback(cb) | 수신 메시지 → AckEvent/SubscriptionEvent 변환 후 cb 호출 |
| receive_loop() | loop_start + disconnected_event.wait |
| is_connected | _connected 플래그 |
| set_on_connection_lost | on_disconnect에서 호출 |

---

## 7. 검증 포인트

| 항목 | 방법 |
|------|------|
| mqtt 연결 (TCP) | Mosquitto localhost:1883 |
| mqtt 연결 (WS) | Mosquitto localhost:9001 |
| publish/subscribe 동작 | 두 transport로 동일 시나리오 테스트 |
| ACK/SUBSCRIPTION 변환 | MQTT 메시지 → Envelope 이벤트 변환 검증 |
| 연결 끊김 sentinel | on_disconnect → sentinel |

---

## 8. 의존성

| 패키지 | 용도 | 필요성 |
|--------|------|--------|
| paho-mqtt | MQTT | transport="mqtt" 사용 시 필수 |
| msgpack | MessagePack 발송 | bytes payload 사용 시. optional |

**pyproject.toml**
```toml
[project]
dependencies = ["websockets", "paho-mqtt>=2.0"]

[project.optional-dependencies]
msgpack = ["msgpack"]
```

---

## 9. 관련 문서 업데이트

| 문서 | 반영 내용 |
|------|-----------|
| TODO.md | transport="mqtt", MessagePack, 재연결 완료 표시 |
| system_specification_v1.md | 클라이언트 SDK 기능(transport, MessagePack, 재연결) |
| SDK/README.md | transport, MessagePack, 자동 재연결 문서화 |
| SDK/examples/README.md | 자동 재연결, MessagePack 발행 예제 |
| TGU_RPC_SDK_DEVELOPMENT_PLAN.md | mqtt Transport 반영 |
