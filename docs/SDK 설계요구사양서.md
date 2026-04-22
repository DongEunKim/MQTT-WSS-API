# SDK 설계 요구사양서

본 문서는 **서버용 `maas-server-sdk`**와 **클라이언트용 `maas-client-sdk`**에 대한 기능·비기능 요구사항을 정의한다. 토픽·페이로드·Reason Code의 규범은 [TOPIC_AND_ACL_SPEC.md](TOPIC_AND_ACL_SPEC.md), RPC 패턴 설명은 [RPC_DESIGN.md](RPC_DESIGN.md)를 단일 출처로 한다.

---

## Part 1. 서버 SDK (`maas-server-sdk`)

### 1.1 개요 및 목적

엣지 Python 환경에서 MQTT 5.0으로 클라이언트와 비동기 RPC를 수행할 때, 연결·구독·디스패치·응답 발행을 캡슐화한다. 개발자는 `@server.action("이름")`으로 페이로드의 **라우팅 필드**(기본 키 이름 `"action"`, `MaasServer(..., route_key=...)`로 변경 가능)와 일치하는 핸들러를 등록한다. `route_key=None`이면 `@server.default`만 사용하고 JSON 본문을 분해하지 않는다.

### 1.2 타겟 환경

- **언어:** Python 3.8+
- **전송:** MQTT 5.0 (TCP / TLS / WebSocket Secure 등; 인증서·엔드포인트는 브로커·배포에 맞게 구성)

### 1.3 코어 아키텍처

#### 연결 및 수명주기

- 브로커와의 연결 유지, 재연결 정책(환경에 맞게).
- 구독: `WMT/{ThingType}/{Service}/{VIN}/+/request` (서버가 담당하는 ThingType·Service·VIN 고정).
- 선택: 브로커가 제공하는 연결 단절 이벤트 토픽 구독(`MaasServer.lifecycle_topics`).

#### RPC 디스패처

- 수신 메시지의 **서비스 토픽**이 자신의 ThingType·Service·VIN과 일치하는지 검증한다.
- JSON 페이로드를 파싱하고 **`route_key`로 지정한 필드**(기본 `"action"`) 값으로 등록된 핸들러를 선택한다. `route_key=None`이면 단일 `@server.default`로만 처리한다. (구 설계의 페이로드 `group` 등은 사용하지 않는다.)
- MQTT 5 **Correlation Data**, **Response Topic**, **User Property**(`reason_code`, `error_detail`, `is_EOF` 등)를 [TOPIC_AND_ACL_SPEC.md](TOPIC_AND_ACL_SPEC.md)에 맞게 처리한다.

#### 세션·락 (패턴 E)

- `exclusive` / `acquire_lock` / `release_lock` 옵션으로 독점 세션을 지원한다.
- 클라이언트 단절 시 락 해제 등은 Presence와 연동한다.

### 1.4 개발자 인터페이스 (요구사항)

- **`MaasServer(thing_type, service_name, vin, endpoint, ..., route_key="action")`** 로 인스턴스를 생성한다. `route_key`는 라우팅에 사용할 JSON 키(기본 규격과 동일하게 `"action"`); `None`이면 `@server.default` 단일 핸들러만 허용한다.
- **`@server.action(action_name, streaming=..., exclusive=..., acquire_lock=..., release_lock=...)`** 로 핸들러를 등록한다. `action_name`은 요청 JSON의 **`route_key` 필드** 값과 동일해야 한다(기본 시 `"action"`).
- 핸들러 시그니처는 **`RpcContext`** 를 받아 동기 반환값 또는 (스트리밍 시) 제너레이터를 반환할 수 있어야 한다.
- 임의 토픽용 **`@server.subscribe("패턴")`** 은 RPC 외 pub/sub에 사용할 수 있다.

#### 예시 (개념)

```python
server = MaasServer(
    thing_type="CGU",
    service_name="viss",
    vin="VIN-123456",
    endpoint="mqtt.example.com",
    route_key="action",  # TOPIC_AND_ACL_SPEC 권장과 동일(기본값). 다른 키 또는 None 은 README 참고.
)

@server.action("get")
def get_datapoint(ctx: RpcContext):
    return {"value": read_sensor(ctx.payload.get("path"))}

@server.action("diag_log", streaming=True)
def stream_log(ctx: RpcContext):
    for chunk in read_chunks():
        yield chunk

server.run()
```

### 1.5 패턴별 기대 동작 (서버)

| 패턴 | SDK 동작 요약 |
|------|----------------|
| A (Liveness) | QoS·타임아웃은 클라이언트와 합의; 응답은 Correlation Data 유지 |
| B (Reliable) | 예외 시 `reason_code` 매핑, 필요 시 `error_detail` |
| C (Streaming) | 청크는 `WMO/.../event`, 완료는 `WMO/.../response` + `is_EOF` |
| D (Time-bound) | 브로커 Message Expiry와 조합; 서버는 만료된 요청 처리 정책을 문서화 |
| E (Exclusive) | 락 미보유 시 `0x8A` 등으로 거절 |

### 1.6 비기능 요구사항 (서버)

- 핸들러 실행은 스레드 풀 또는 asyncio 등으로 블로킹을 분리할 수 있어야 한다.
- 처리되지 않은 예외는 크래시 대신 클라이언트에 오류 응답으로 귀결되어야 한다.

---

## Part 2. 클라이언트 SDK (`maas-client-sdk`)

### 2.1 개요 및 목적

브라우저·백오피스 등에서 MQTT 브로커(예: WSS)를 통해 엣지 서비스를 호출할 때, 토픽 조립·`Correlation Data`·타임아웃·스트림 수신을 캡슐화한다. 개발자는 **`thing_type`, `service`, `action`, `vin`** 만 지정하면 된다.

### 2.2 설계 원칙

- **비동기 우선:** `MaasClientAsync` 및 `asyncio` 기반 API를 제공한다.
- **토픽 은닉:** 애플리케이션은 WMT/WMO 전체 경로를 몰라도 되며 SDK가 [TOPIC_AND_ACL_SPEC.md](TOPIC_AND_ACL_SPEC.md)에 따라 생성한다.
- **상태 비침습:** 서버 내부 상태를 가정하지 않고 응답 `reason_code`와 타임아웃에 의존한다.

### 2.3 코어 아키텍처

#### 연결

- `endpoint`, `client_id`, 선택적 `token_provider`(JWT)로 WSS 연결.
- 연결 후 **`WMO/+/+/+/{clientId}/response`**, **`WMO/+/+/+/{clientId}/event`** 구독을 등록한다.
- **Clean Start**로 stale 응답을 방지한다(요구사항).

#### RPC 호출기

- 요청마다 Correlation Data를 생성하고, 응답 매칭용 맵을 유지한다.
- **Response Topic**을 `WMO/.../response`로 설정하고, 요청은 **`WMT/.../request`**에 발행한다.

### 2.4 API 요구사항

- **`call(thing_type, service, action, vin, params=..., qos=..., timeout=..., expiry=...)`**  
  단일 응답 RPC. `expiry`는 패턴 D(Message Expiry Interval)에 사용.
- **`stream(thing_type, service, action, vin, ...)`**  
  `async for`로 `event` 토픽 청크 수신 후 `response`로 완료.
- **`exclusive_session(thing_type, service, vin, acquire_action=..., release_action=...)`**  
  `async with` 진입 시 락 획득 RPC, 종료 시 해제 RPC.
- 선택: **`publish` / `subscribe`** 로 임의 토픽 pub/sub.

### 2.5 개발자 인터페이스 예시 (개념)

```python
client = MaasClientAsync(
    endpoint="mqtt.example.com",
    client_id="webapp-uuid",
    token_provider=get_jwt_from_at_server,
)
await client.connect()

# 패턴 A/B
resp = await client.call(
    thing_type="CGU",
    service="viss",
    action="get",
    vin="VIN-123456",
    params={"path": "Vehicle.Speed"},
    qos=0,
    timeout=3.0,
)

# 패턴 C
async for ev in client.stream(
    thing_type="CGU", service="viss", action="diag_log", vin="VIN-123456",
    params={"hours": 1},
):
    process(ev)

# 패턴 E
async with client.exclusive_session(
    thing_type="CGU", service="diagnostics", vin="VIN-123456",
) as session:
    await session.call(action="ecu_reset", params={})

await client.disconnect()
```

### 2.6 비기능 요구사항 (클라이언트)

1. **메모리:** 타임아웃·완료 시 Pending 맵에서 Correlation 항목을 반드시 제거한다.
2. **단절:** 연결 끊김 시 대기 중인 호출은 명시적 네트워크 예외로 일괄 실패 처리한다.
3. **직렬화:** dict 등은 JSON과 `content-type` user property를 일관되게 설정한다.
4. **토큰 갱신:** JWT 만료 전 재발급·만료로 인한 재연결(Clean Start)을 지원하는 것이 바람직하다.
5. **권한 오류:** 샌드박스 위반·브로커 거부는 일반 타임아웃과 구분 가능한 **`NotAuthorizedError`** (또는 Reason `0x87`)로 전달할 수 있어야 한다.

---

## 부록: 문서 간 역할

| 문서 | 내용 |
|------|------|
| [TOPIC_AND_ACL_SPEC.md](TOPIC_AND_ACL_SPEC.md) | WMT/WMO 토픽, ACL, 페이로드 `action`, Reason Code |
| [RPC_DESIGN.md](RPC_DESIGN.md) | 패턴 A~E, 서버/클라이언트 동작 개요 |
| [RPC 보안정책.md](RPC%20보안정책.md) | AGT/AT, 브로커 연결 게이트웨이, 토픽 샌드박스 |
