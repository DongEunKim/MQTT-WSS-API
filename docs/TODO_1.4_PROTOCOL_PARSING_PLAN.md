# TODO 1.4 프로토콜·파싱 상세 계획

> **상태**: 완료  
> **목표**: 수신 메시지 파싱 실패 시 상세 로깅으로 디버깅 용이성 향상  
> **범위**: unknown event, req_id 누락, 파싱 실패 등 비정상 메시지 처리

---

## 1. 작업 항목 개요

| # | 항목 | 우선순위 | 의존성 |
|---|------|----------|--------|
| 1 | 알 수 없는 event 타입 처리 | 중간 | 없음 |
| 2 | req_id 누락 메시지 처리 | 중간 | 없음 |
| 3 | 파싱 실패 시 상세 에러 로깅 | 중간 | 없음 |

---

## 2. 현황 분석

### 2.1 현재 처리 흐름

```
수신 raw
  → protocol.decode_message(raw)
      → _decode_data(raw): str/json bytes → dict
      → event 필드 분기
          - ACK: code 필수 검증, AckEvent 반환
          - SUBSCRIPTION: topic 필수 검증, SubscriptionEvent 반환
          - 그 외: ValueError("Unknown event type: {event}")
      → req_id 없음: ValueError("Missing req_id in message")
  → ValueError 발생 시
      → WssMqttApiTransport.receive_loop: _log.warning("메시지 파싱 실패: %s", e)
      → 메시지 폐기, 수신 루프 계속
```

### 2.2 한계

- **알 수 없는 event**: `ValueError` 메시지만 로그. 원본 메시지(raw)나 event 값 등 디버깅 정보 부족.
- **req_id 누락**: 동일. 어떤 메시지에서 실패했는지 추적 어려움.
- **직렬화 실패**: `_decode_data`에서 `json.loads`/`msgpack.unpackb` 예외 시 상위로 전파. 로그에 raw 미포함.

---

## 3. 상세 작업 계획

### 3.1 알 수 없는 event 타입 처리

**목표**
- `event`가 `"ACK"`, `"SUBSCRIPTION"`이 아닌 메시지 수신 시 상세 로깅 후 폐기

**구현 방안**

1. **protocol.py**: `decode_message()`에서 unknown event 시
   - 기존: `raise ValueError(f"Unknown event type: {event}")`
   - 개선: 예외 메시지에 `event`, `req_id`, `topic`(있으면) 포함
   - `ParseError` 또는 기존 `ValueError` 유지 (호출부 호환)

2. **Transport 수신 루프**: 예외 로깅 시
   - `event`, `req_id`, raw 메시지 요약(앞 N바이트) 추가
   - raw가 길면 truncate (예: 200자)

**로그 예시**
```
WARNING: 알 수 없는 event 타입, 메시지 폐기: event=PING req_id=abc123 raw_preview='{"event":"PING","timestamp":...'
```

**파일**
- `protocol.py`: `decode_message()` 예외 메시지 개선
- `transport/wss_mqtt_api.py`: 로깅 시 context 추가

---

### 3.2 req_id 누락 메시지 처리

**목표**
- `req_id`가 없거나 빈 문자열인 메시지 수신 시 상세 로깅 후 폐기

**구현 방안**

1. **protocol.py**:
   - `req_id = data.get("req_id")` 후 `if not req_id` (None, "", 0 등)
   - 예외 메시지: `"Missing req_id in message. event=%s keys=%s"` (event, data.keys())

2. **동일 적용**: `code` 누락(ACK), `topic` 누락(SUBSCRIPTION) 시
   - `ValueError("Missing code in ACK message. req_id=%s" % req_id)`
   - `ValueError("Missing topic in SUBSCRIPTION message. req_id=%s" % req_id)`

**로그 예시**
```
WARNING: 메시지 파싱 실패: Missing req_id in message. event=ACK keys=dict_keys(['event','code'])
```

**파일**
- `protocol.py`: `decode_message()` 예외 메시지 개선

---

### 3.3 파싱 실패 시 상세 에러 로깅

**목표**
- JSON/MessagePack 디코딩 실패, 타입 오류 등 모든 파싱 예외에 raw 요약 포함

**구현 방안**

1. **protocol.py**:
   - `_decode_data()` 실패 시: `json.JSONDecodeError`, `msgpack.UnpackException` 등
   - `decode_message()`에서 try/except로 감싸, 원본 예외 + raw 요약으로 `ValueError` 재발생
   - 예: `raise ValueError(f"직렬화 파싱 실패: {e}. raw_preview={_truncate(raw, 200)}") from e`

2. **헬퍼**:
   ```python
   def _truncate(raw: str | bytes, max_len: int = 200) -> str:
       s = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
       return repr(s[:max_len] + "..." if len(s) > max_len else s)
   ```

3. **Transport**: 기존 `_log.warning("메시지 파싱 실패: %s", e)` 유지
   - 예외에 이미 상세 정보가 포함되므로 메시지만으로 충분

**파일**
- `protocol.py`: `_decode_data()` 예외 처리, `_truncate()` 헬퍼, `decode_message()` 래핑

---

## 4. 예외 구조 (선택)

기존 `ValueError` 유지 vs 전용 예외 도입:

| 옵션 | 장점 | 단점 |
|------|------|------|
| ValueError 유지 | 호출부 변경 없음, 기존 except 처리 유지 | 파싱 오류 vs 로직 오류 구분 불가 |
| ParseError(ValueError) | 의도 명확, 나중에 별도 처리 가능 | 호출부에서 ParseError catch 필요 시 수정 |

**권장**: `ValueError` 유지. 로깅 개선이 목적이므로 기존 흐름 유지.

---

## 5. 로깅 레벨 정책

| 상황 | 레벨 | 비고 |
|------|------|------|
| unknown event | WARNING | 의도치 않은 메시지 |
| req_id 누락 | WARNING | 프로토콜 위반 |
| code/topic 누락 | WARNING | 프로토콜 위반 |
| 직렬화 파싱 실패 | WARNING | 손상/비표준 메시지 |

---

## 6. 작업 순서

| 순서 | 항목 | 이유 |
|------|------|------|
| 1 | 3.3 파싱 실패 로깅 | _truncate, _decode_data 래핑 — 기반 |
| 2 | 3.2 req_id 누락 | decode_message 내 검증 메시지 개선 |
| 3 | 3.1 unknown event | event 분기 예외 메시지 개선 |
| 4 | Transport 로깅 보강 | 필요 시 raw_preview 추가 (선택) |

---

## 7. 검증 포인트

| 항목 | 방법 |
|------|------|
| unknown event | event=UNKNOWN 메시지 주입 → WARNING 로그에 event 포함 확인 |
| req_id 누락 | req_id 없는 메시지 → 로그에 keys 또는 event 포함 확인 |
| 직렬화 실패 | 잘못된 JSON 주입 → raw_preview truncate 확인 |
| 기존 동작 | 정상 ACK/SUBSCRIPTION 수신 시 로그 변화 없음 |

---

## 8. 파일 변경 요약

| 파일 | 변경 |
|------|------|
| `protocol.py` | `_truncate()`, `_decode_data()` 예외 래핑, `decode_message()` 예외 메시지 개선 |
| `transport/wss_mqtt_api.py` | 기존 `_log.warning("메시지 파싱 실패: %s", e)` 유지 (예외에 상세 정보 포함) |

---

## 9. 완료 사항 (구현 기록)

- **protocol.py**
  - `_truncate(raw, max_len=200)`: raw truncate 헬퍼 추가
  - `_decode_data()`: 직렬화 실패 시 `ValueError`에 `raw_preview` 포함
  - `decode_message()`: unknown event, req_id 누락, code/topic 누락 시 상세 예외 메시지
- **테스트**: `test_protocol.py`에 5개 신규 테스트 추가 (missing_req_id, missing_code, missing_topic, parse_failure, invalid_event 보강)
- **예제**: 내부 파싱 개선이므로 예제 변경 없음. `basic_publish_subscribe.py` 실행 검증 완료.
