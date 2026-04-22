# maas-server-sdk

MQTT 5.0 기반 **MaaS RPC 서비스(핸들러)** Python 패키지. 장비·엣지 런타임에서 `WMT/{ThingType}/{Service}/{VIN}/+/request`를 구독하고, MQTT 5.0 Properties로 응답·스트림을 발행한다.

규격·토픽·ACL·Reason Code:

- [TOPIC_AND_ACL_SPEC.md](../../../../docs/TOPIC_AND_ACL_SPEC.md)
- [RPC_DESIGN.md](../../../../docs/RPC_DESIGN.md)

---

## 요구 사항

- Python 3.10+
- `paho-mqtt` 2.x (MQTT 5.0)

인증서·TLS/WSS는 연결 옵션(`use_wss`, `port`)으로 선택한다.

---

## 설치

패키지 디렉터리(`maas-server-sdk/`)에서:

```bash
pip install -e .[dev]
```

저장소 루트에서:

```bash
pip install -e SDK/server/python/maas-server-sdk[dev]
```

또는:

```bash
bash SDK/server/python/install.sh --dev
```

---

## 패키지에서 가져오기

```python
from maas_server import MaasServer, RpcContext
from maas_server import topics  # 선택: 토픽 빌더·파서
```

---

## `MaasServer` 생성

담당 **ThingType**, **Service**, **VIN**, 브로커 **endpoint**를 고정한다. 이 조합에 맞는 WMT 요청만 처리한다.  
클라이언트 측 [`MaasClient`](../../../client/python/maas-client-sdk/README.md)도 동일하게 생성자에 `thing_type` / `service` / `vin`을 맞추고 `call(action[, params])`로 호출하는 패턴과 대칭이다.

### 생성자 인자

| 인자 | 기본 | 설명 |
|------|------|------|
| `thing_type` | (필수) | 토픽 `{ThingType}` |
| `service_name` | (필수) | 토픽 `{Service}` |
| `vin` | (필수) | 토픽 `{VIN}` |
| `endpoint` | (필수) | 브로커 호스트 |
| `port` | `8883` | TCP TLS 등. 로컬 Mosquitto는 보통 `1883` + `use_wss=False` |
| `use_wss` | `False` | `True`면 WebSocket+TLS(경로 `/mqtt`) |
| `client_id` | `f"{service_name}-{vin}"` | MQTT ClientId |
| `session_idle_timeout` | `300` | 독점 세션 유휴 해제(초) |
| `route_key` | `"action"` | 페이로드에서 라우팅에 쓸 JSON 키. `None`이면 아래 **라우팅** 참고 |
| `lifecycle_topics` | `None` | 연결/단절 이벤트용 구독 패턴 목록. 브로커가 제공할 때만 설정 |
| `logger` | — | 선택 로거 |

### 환경변수에서 생성

환경변수로 엔드포인트·VIN을 넘기는 배포용 팩토리:

```python
server = MaasServer.from_env(
    "CGU",
    "viss",
    vin_env="THING_VIN",
    endpoint_env="MQTT_ENDPOINT",
    route_key="action",
)
```

`THING_VIN`, `MQTT_ENDPOINT`가 없으면 `KeyError`이다.

### 예: TLS 브로커(TCP 8883)

```python
server = MaasServer(
    thing_type="CGU",
    service_name="viss",
    vin="VIN-123456",
    endpoint="mqtt.example.com",
    port=8883,
    use_wss=False,
    route_key="action",
)
```

### 예: 로컬 Mosquitto(TCP 1883)

```python
server = MaasServer(
    thing_type="CGU",
    service_name="viss",
    vin="VIN-123456",
    endpoint="127.0.0.1",
    port=1883,
    use_wss=False,
    client_id="example-viss-service",
    route_key="action",
)
```

저장소 예제: [SDK/examples/rpc_local_echo_service.py](../../../../SDK/examples/rpc_local_echo_service.py).

---

## 라우팅: `route_key` · `@server.action` · `@server.default`

- **`route_key="action"`(기본):** 요청 JSON에서 `action` 필드를 읽어 `@server.action("이름")`과 매칭한다. [TOPIC_AND_ACL_SPEC.md](../../../../docs/TOPIC_AND_ACL_SPEC.md) §5와 동일.
- **다른 키:** `route_key="method"` 등으로 바꿀 수 있다. 클라이언트·문서와 **같은 키**를 써야 한다.
- **`route_key=None`:** `@server.action`은 **사용할 수 없다**. `@server.default` **하나만** 등록한다. 페이로드에서 라우팅 필드를 제거하지 않고 **전체 dict**가 `RpcContext.payload`로 전달된다.
- **기본 핸들러(선택):** `route_key`가 문자열일 때, 해당 필드가 없거나 빈 값이면 `@server.default`가 호출된다.

```python
@server.action("get")
def get_datapoint(ctx: RpcContext):
    return {"value": 42, "path": ctx.payload.get("path")}

@server.default()
def fallback(ctx: RpcContext):
    return {"error": "unknown route"}
```

---

## RPC 핸들러: `@server.action`

```python
@server.action("get")
def get_datapoint(ctx: RpcContext):
    return {"path": ctx.payload.get("path"), "value": 42.0}
```

데코레이터 옵션:

| 옵션 | 의미 |
|------|------|
| `streaming=True` | 핸들러는 동기/비동기 **제너레이터**. 청크는 `WMO/.../event`, 완료는 `response` + `is_EOF` |
| `exclusive=True` | 독점 세션을 잡은 클라이언트만 호출 허용 |
| `acquire_lock=True` | 이 액션에서 세션 락 획득 |
| `release_lock=True` | 이 액션에서 세션 락 해제 |

`RpcContext` 주요 필드: `thing_type`, `service`, `action`(라우트 라벨), `vin`, `client_id`, `payload`(라우팅 키 제거 후 나머지), `correlation_id`, `response_topic`, `user_props`.

---

## 임의 구독·발행: `@server.subscribe`, `publish`

```python
@server.subscribe("shadow/update/#")
def on_shadow(topic: str, payload: bytes) -> None:
    ...

server.run()  # 블로킹
# 실행 중에만:
server.publish("some/topic", {"a": 1}, qos=1)
```

`run()`이 돌고 있는 동안에만 `publish`를 호출할 수 있다. 종료는 `KeyboardInterrupt` 또는 다른 스레드에서 `server.stop()`.

---

## 실행

```python
server.run()   # asyncio.run 기반, 블로킹
```

---

## 문서

- [SDK 설계요구사양서](../../../../docs/SDK%20설계요구사양서.md) Part 1
- [SDK 개요](../../../../SDK/README.md)

---

## 라이선스

Proprietary (프로젝트 정책에 따름).
