# TODO 1.5·1.6 입력 검증 및 유틸리티 상세 계획

> **상태**: 완료  
> **목표**: 토픽 입력 검증 강화 및 배치·로깅·가이드·최적화로 사용성 향상  
> **범위**: 1.5 입력 검증 + 1.6 유틸리티·사용성 (통합 진행)

---

## 1. 작업 항목 개요

| # | 항목 | 소속 | 우선순위 | 의존성 |
|---|------|------|----------|--------|
| 1 | 토픽 형식 검증 | 1.5 | 높음 | 없음 |
| 2 | 배치 publish/subscribe | 1.6 | 높음 | 없음 |
| 3 | unsubscribe 중복 호출 최적화 | 1.6 | 중간 | 없음 |
| 4 | 구독 미소비 가이드 (docstring) | 1.6 | 중간 | 없음 |
| 5 | 구조화 로깅 (structlog) | 1.6 | 낮음 | structlog (선택적) |

---

## 2. 1.5 토픽 형식 검증

### 2.1 배경

- **사양 6.1**: `topic`은 필수. API 서버 사양의 제약을 따름 (일반적으로 와일드카드 `+`, `#` 사용 불가)
- **MQTT 표준**: UTF-8 허용, 토픽 이름에 `+`, `#` 사용 불가 (구독 필터 전용). 이론상 65535바이트, 실무 200~250자 제한 흔함
- **현재**: `build_request()`, `publish()`, `subscribe()`, `unsubscribe()` 등에서 토픽 검증 없음

### 2.2 검증 규칙

| 규칙 | 조건 | 에러 메시지 |
|------|------|-------------|
| 빈 문자열 | `len(topic.strip()) == 0` | `"토픽은 빈 문자열일 수 없습니다"` |
| 최대 길이 | `len(topic) > max_len` (기본 512) | `"토픽 길이 초과: {len} > {max}"` |
| 와일드카드 금지 | `"+" in topic or "#" in topic` | `"토픽 이름에 와일드카드(+, #) 사용 불가"` |
| NUL 문자 금지 | `"\x00" in topic` | `"토픽에 NUL 문자 포함 불가"` |

- **설정 가능**: `validate_topic=False` 파라미터로 검증 비활성화 (호환용)
- **길이 기본값**: 512 (MQTT 실무 상한·대부분 브로커 수용 가능)

### 2.3 적용 위치

| 파일 | 적용 지점 |
|------|-----------|
| `validation.py` (신규) | `validate_topic(topic, max_len=512) -> None` — 검증 실패 시 `ValueError` |
| `protocol.py` | `build_request()` — `validate_topic(topic)` 호출 (옵션) |
| `client.py` | `publish()`, `subscribe()`, `unsubscribe()` — 클라이언트 진입점에서 검증 |

**권장**: `client.py`의 `publish()`, `subscribe()`, `unsubscribe()`에서 검증. `build_request()`는 내부용이므로 호출 전에 검증된 값만 전달. 검증 로직은 `validation.py`에 분리.

### 2.4 구현 방안

1. **`wss_mqtt_client/validation.py`** (신규)
   ```python
   def validate_topic(topic: str, *, max_len: int = 512) -> None:
       """토픽 형식 검증. 실패 시 ValueError."""
       if not isinstance(topic, str):
           raise ValueError("토픽은 문자열이어야 합니다")
       if not topic or not topic.strip():
           raise ValueError("토픽은 빈 문자열일 수 없습니다")
       if len(topic) > max_len:
           raise ValueError(f"토픽 길이 초과: {len(topic)} > {max_len}")
       if "+" in topic or "#" in topic:
           raise ValueError("토픽 이름에 와일드카드(+, #) 사용 불가")
       if "\x00" in topic:
           raise ValueError("토픽에 NUL 문자 포함 불가")
   ```

2. **`client.py`**: `WssMqttClient.__init__`에 `validate_topic: bool = True`, `topic_max_length: int = 512` 추가  
   - `publish()`, `subscribe()`, `unsubscribe()` 진입 시 `validate_topic`이 True면 `validate_topic(topic, max_len=self._topic_max_length)` 호출

3. **`protocol.py`**: `build_request()`는 검증하지 않음 (client에서 이미 검증)

---

## 3. 1.6 유틸리티·사용성

### 3.1 배치 publish/subscribe

#### 3.1.1 목표

- `publish_many(topic_payloads: Iterable[tuple[str, Any]])` — 다수 토픽에 순차 발행
- `subscribe_many(topics: Iterable[str])` — 다수 토픽 동시 구독, 단일 스트림으로 수신

#### 3.1.2 API 설계

**publish_many**

```python
async def publish_many(
    self,
    topic_payloads: Iterable[tuple[str, Any]],
    *,
    stop_on_error: bool = True,
) -> list[tuple[str, Any, Optional[Exception]]]:
    """
    다수 토픽에 메시지 발행.

    Args:
        topic_payloads: (topic, payload) 튜플의 iterable
        stop_on_error: True면 첫 실패 시 중단, False면 계속 시도

    Returns:
        (topic, payload, error) 리스트. 성공 시 error는 None
    """
```

**subscribe_many**

- `subscribe()`가 단일 토픽만 받으므로, `subscribe_many(topics)`는 내부적으로 여러 `SubscriptionStream`을 래핑
- 또는 `MultiTopicStream` 같은 새 타입: 여러 토픽을 한 번에 구독하고, `async for event in stream` 시 `event.topic`으로 구분

**간소화**: 1차는 `publish_many`만 구현. `subscribe_many`는 사용 패턴이 복잡하므로 2차 또는 제외 검토.

**최종 제안**:
- `publish_many()`: 구현
- `subscribe_many()`: `AsyncContextManager`로 진입 시 여러 SUBSCRIBE, 퇴장 시 여러 UNSUBSCRIBE. `async for` 시 어느 토픽인지 `event.topic`으로 구분. `queue_maxsize`, `timeout` 공유

#### 3.1.3 구현

- **파일**: `client.py`
- **publish_many**:
  ```python
  async def publish_many(
      self,
      topic_payloads: Iterable[tuple[str, Any]],
      *,
      stop_on_error: bool = True,
  ) -> list[tuple[str, Any, Optional[Exception]]]:
      results = []
      for topic, payload in topic_payloads:
          try:
              await self.publish(topic, payload)
              results.append((topic, payload, None))
          except Exception as e:
              results.append((topic, payload, e))
              if stop_on_error:
                  break
      return results
  ```

- **subscribe_many**:
  - `MultiTopicSubscriptionStream` 클래스: `__aenter__`에서 각 topic에 대해 `build_request(SUBSCRIBE, t)` 후 `_send_and_wait_ack`, `__aexit__`에서 각 topic에 대해 UNSUBSCRIBE
  - 단, 현재 구조는 `_topic_to_req_ids`가 topic별로 여러 req_id를 가질 수 있음. `subscribe_many`는 topic당 1 req_id.
  - `subscribe_many(topics)` → 내부에서 `topic in topics`인 각각에 대해 `subscribe(topic)`을 호출? 아니다. `subscribe()`는 `SubscriptionStream`을 반환하고, `async with`로 진입해야 함.
  - **선택 A**: `subscribe_many(topics)` → `MultiTopicStream(topics)` 반환. `async with stream` 시 topics 전부 SUBSCRIBE, `async for event` 시 하나의 queue에 모든 SUBSCRIPTION 합침. `event.topic`으로 구분.
  - **선택 B**: `subscribe_many` 제외, docstring에 `for topic in topics: async with client.subscribe(topic) as s: ...` 패턴 안내만 추가.

  **권장**: 선택 A. `MultiTopicSubscriptionStream` 구현.

---

### 3.2 unsubscribe 중복 호출 최적화 (idempotent)

#### 3.2.1 현황

- `unsubscribe(topic)` 호출 시 `req_ids = self._topic_to_req_ids.get(topic)` 존재하면 각 req_id에 대해 `_unsubscribe_and_unregister` 호출
- 이미 구독이 없는 topic에 `unsubscribe(topic)` 호출 시: `req_ids`가 None/빈 집합 → 아무것도 하지 않음 (이미 idempotent)
- **실제 이슈**: 동일 context에서 `unsubscribe`를 두 번 호출하면? 첫 호출에서 UNSUBSCRIBE 전송 후 `_remove_topic_subscriber`로 제거. 두 번째 호출 시 `req_ids` 비어있음 → 조용히 무시. 즉 **이미 idempotent**.

- **재검토**: `SubscriptionStream.__aexit__`에서 `_unsubscribe_and_unregister` 호출. `async with` 중복 진입은 없음. 하지만 `unsubscribe(topic)`을 사용자가 직접 여러 번 호출할 수 있음. → 이미 안전.

- **추가 고려**: `disconnect(unsubscribe_first=True)` 시 특정 topic이 이미 해제된 경우? `_topic_to_req_ids`를 순회하므로, 이미 비어있으면 해당 topic은 건너뜀. 역시 문제없음.

**결론**: 현재 구현이 이미 idempotent. 다만 다음을 보강:
- `unsubscribe(topic)` docstring에 "이미 구독이 없으면 무시(idempotent)" 명시
- (선택) `unsubscribe(topic)`에서 해당 topic이 없을 때 DEBUG 로그: `"구독 없음, 무시: topic=%s"` — 로그는 생략 가능, docstring만 추가해도 충분

---

### 3.3 구독 미소비 가이드 (docstring)

#### 3.3.1 목표

- `subscribe()` 후 `async for`로 스트림을 소비하지 않으면 큐가 쌓여 메모리 증가
- docstring 및 주의사항 안내 추가

#### 3.3.2 적용

- **`SubscriptionStream`** docstring:
  ```
  주의: async for로 이벤트를 소비하지 않으면 구독 큐(queue_maxsize)가
  쌓여 메모리가 증가할 수 있습니다. 메시지를 사용하지 않는 구독은
  적극적으로 소비하거나, queue_maxsize를 적게 설정하세요.
  ```

- **`subscribe()`** docstring: "구독 후 stream을 반드시 소비(iterate)할 것" 권장 문구 추가

---

### 3.4 구조화 로깅 (structlog)

#### 3.4.1 목표

- `structlog` 사용 시 기존 `logging`과 연동
- **선택 사항**: `structlog`는 optional 의존성. 기본은 기존 `logging` 유지.

#### 3.4.2 방안

1. **표준 logging 유지**: 현재 `logger.info(...)`, `logger.warning(...)` 계속 사용. `structlog`는 `logging`에 바인딩 가능하므로, 사용자가 `structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(...))` 등으로 연동 가능.
2. **문서화**: README 또는 개발 가이드에 "구조화 로깅을 쓰려면 structlog를 logging에 연동하세요" 예시 추가.
3. **코드 변경 최소화**: SDK 내부에서 `structlog` 직접 사용하지 않음. 호환성 문서만 추가.

**권장**: 3.4는 이번 스코프에서 **문서만** 추가. 코드 변경 없음.

---

## 4. 작업 순서

| 순서 | 항목 | 이유 |
|------|------|------|
| 1 | 1.5 토픽 검증 | 배치/헬퍼에서 topic 사용 전 검증 필요 |
| 2 | publish_many | 구현 단순, 검증 재사용 |
| 3 | subscribe_many | MultiTopicStream 설계·구현 |
| 4 | unsubscribe docstring | idempotent 명시, 변경 없음 |
| 5 | 구독 미소비 docstring | SubscriptionStream, subscribe 보강 |
| 6 | structlog 문서 | README/개발 가이드 (선택) |

---

## 5. 파일 변경 요약

| 파일 | 변경 |
|------|------|
| `validation.py` (신규) | `validate_topic(topic, max_len=512)` |
| `client.py` | `validate_topic`, `topic_max_length` 파라미터; `publish()`, `subscribe()`, `unsubscribe()` 검증; `publish_many()`, `subscribe_many()` 추가; docstring 보강 |
| `exceptions.py` | (선택) `ValidationError` — `ValueError` 상속, 토픽 검증용. 기존 ValueError로 충분하면 생략 |
| `README.md` 또는 `docs/` | 구조화 로깅 연동 안내 (선택) |

---

## 6. 검증 포인트

| 항목 | 방법 |
|------|------|
| 토픽 검증 | 빈 문자열, `+`, `#`, 길이 초과, NUL 주입 → ValueError 확인 |
| validate_topic=False | 검증 비활성화 시 기존 동작 유지 |
| publish_many | 다수 (topic, payload) 전달 → 순차 발행, stop_on_error 동작 확인 |
| subscribe_many | 다수 토픽 구독 → 한 스트림에서 수신, event.topic 구분 확인 |
| 기존 테스트 | 전부 통과 |

---

## 7. 완료 사항 (구현 기록)

- **validation.py** (신규): `validate_topic(topic, max_len=512)`
- **client.py**
  - `validate_topic`, `topic_max_length` 파라미터
  - `publish()`, `subscribe()`, `unsubscribe()` 진입 시 검증
  - `publish_many()`, `subscribe_many()` (MultiTopicSubscriptionStream)
  - SubscriptionStream, subscribe, unsubscribe docstring 보강
- **예제**: `batch_publish_subscribe.py` 추가
- **테스트**: test_validation.py, test_client_integration 확장 (topic 검증, publish_many, subscribe_many)
- **문서**: README 업데이트 (배치 API, 토픽 검증, structlog)

---

## 8. 미구현·이관 항목

| 항목 | 사유 |
|------|------|
| ValidationError 전용 예외 | ValueError로 통일해도 무방. 필요 시 추후 도입 |
| subscribe_many 생략 | 사용 패턴이 복잡하면 docstring 패턴 안내만 하고 구현 연기 가능 |
