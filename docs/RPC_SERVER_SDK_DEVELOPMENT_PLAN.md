# RPC Server SDK 개발 계획서

> **문서 목적**  
> 이 문서는 현재 프로젝트의 wss_mqtt_client / RPC Client SDK(`maas-rpc-client-sdk`) 설계를 기반으로,  
> **MQTT 기반 RPC 서버를 구현하기 위한 RPC Server SDK**(이하 *Server SDK*)의 아키텍처, 모듈 구조, 개발 단계를 정의한다.

---

## 1. 배경 및 목표

### 1.1 배경

- 클라이언트는 이미 다음 두 계층을 통해 RPC 서버와 통신할 수 있다.
  - **wss_mqtt_client (wss-mqtt-client 패키지)**  
    - wss-mqtt-api 또는 MQTT over WSS 로 MQTT 브로커에 연결하는 전송 SDK.
    - `transport="wss-mqtt-api" | "mqtt"` 옵션으로 전송 방식을 선택한다.
  - **RPC Client SDK (maas-rpc-client-sdk 패키지)**  
    - `RpcClient`, `RpcClientAsync` 를 통해 `call()`, `call_stream()`, `subscribe_stream()` 등의 RPC 인터페이스를 제공한다.
    - 토픽 패턴(`WMT/.../request`, `WMO/.../response`)과 `request_id`, `response_topic` 기반의 RPC 방법론을 캡슐화한다.

- 클라이언트 SDK는 **클라이언트가 “서비스 명세만 알고 RPC를 쉽게 호출”** 할 수 있도록 추상화되어 있다.
- 반면, **서버 측 서비스 개발자**는 여전히 다음을 직접 처리해야 한다.
  - MQTT 구독/발행 설정
  - `request_id`, `response_topic` 추출 및 응답 발행
  - 요청/응답 Payload 스키마 일관성 유지
  - 에러/타임아웃/로깅 처리 패턴 통일

### 1.2 목표

Server SDK의 최종 목표는 다음과 같다.

- **클라이언트 RPC 인터페이스에 대응하는 서버 측 개발 경험 제공**
  - 클라이언트: `client.call("RemoteUDS", {"action": "readDTC", "params": {...}})`  
  - 서버: `@rpc_service("RemoteUDS")` 데코레이터 또는 유사한 구조로 핸들러 구현
    - `async def handle_read_dtc(request: RemoteUdsReadDtcRequest) -> RemoteUdsReadDtcResponse: ...`

- **MQTT 토픽, 상관관계(request_id, response_topic), 응답 발행 로직을 SDK가 캡슐화**
  - 서비스 개발자는 *“요청을 받아 처리하고 응답 객체를 반환”* 하는 것에만 집중한다.

- **서버 측 공통 런타임/프레임워크 제공**
  - 요청 디스패치 (service / action 기반 라우팅)
  - 인증/JWT 검증 및 컨텍스트 전달
  - 표준 에러 포맷(`code`, `message`) 매핑
  - 로깅/트레이싱 훅 제공

- **기존 설계(RPC_DESIGN, TOPIC_AND_ACL_SPEC)와 정합성 유지**
  - 기존 토픽 패턴, Payload 스키마, ACL 규칙을 그대로 사용한다.
  - 클라이언트 SDK와 서버 SDK가 동일한 프로토콜을 바라본다.

---

## 2. 아키텍처 개요

### 2.1 계층 구조

서버 측에서의 계층 구조는 다음과 같이 정의한다.

```
┌─────────────────────────────────────────────────────────────────┐
│  서비스 레이어 (서버 애플리케이션 서비스 구현 코드)              │
│  - RemoteUDS, RemoteDashboard, VISSv3 등 도메인 서비스        │
│  - @rpc_service, @rpc_action 등으로 구현된 핸들러들            │
├─────────────────────────────────────────────────────────────────┤
│  Server SDK                                                     │
│  - 서비스/액션 라우팅, 요청/응답 직렬화                        │
│  - request_id, response_topic 처리                              │
│  - 표준 에러/컨텍스트/로깅 처리                                 │
├─────────────────────────────────────────────────────────────────┤
│  Transport 레이어                                               │
│  - TransportInterface (connect / disconnect / subscribe / publish)
│  - 기본: 순수 MQTT 브로커 연결 (paho-mqtt 등)                    │
│  - 옵션: AWS IoT Core (AWS IoT Device SDK 기반 MQTT)            │
│  - subscribe("WMT/+/{thing_name}/+/+/request")                 │
│  - publish(response_topic, payload)                             │
├─────────────────────────────────────────────────────────────────┤
│  MQTT Broker / AWS IoT Core MQTT                                │
└─────────────────────────────────────────────────────────────────┘
```

- 클라이언트 측 `wss_mqtt_client` / `maas-rpc-client-sdk` 와는 **분리된 서버 측 SDK** 이지만,  
  **RPC_DESIGN.md에서 정의한 RPC 전송 래퍼 스키마**를 그대로 따른다.

### 2.2 요청/응답 처리 플로우

1. 서버 SDK가 MQTT 브로커에 연결하고, 자신의 `thing_name`을 기준으로 요청 토픽을 구독한다.
   - `WMT/+/{thing_name}/+/+/request` (service 와일드카드, oem/asset은 접근 제어 계층에서 검증)
2. MQTT 메시지 수신 시:
   - Payload를 파싱하여 `request_id`, `response_topic`, `request`를 추출한다.
   - `request.action`, `request.params` 정보와 함께 내부 **요청 컨텍스트**를 생성한다.
3. SDK의 **디스패처**가 service/action 에 해당하는 핸들러 함수를 찾는다.
4. 핸들러 함수가 비즈니스 로직을 수행하고, `result` 또는 예외를 반환한다.
5. SDK가 표준 응답 Payload를 구성하여 `response_topic`으로 발행한다.
   - `{ "request_id": "...", "result": {...}, "error": null }`
   - 또는 `{ "request_id": "...", "result": null, "error": { "code": "...", "message": "..." } }`

### 2.3 서버 SDK와 시스템 전체 관계

- 기존 문서의 클라이언트 관점 계층 구조에 **서버 SDK** 레이어를 추가한 형태:

```
클라이언트 측:
  애플리케이션 → RPC Client SDK (maas-rpc-client-sdk) → wss_mqtt_client → MQTT Broker / AWS IoT Core

서버 측:
  서버 애플리케이션 서비스 구현 → RPC Server SDK → Transport(MQTT / AWS IoT) → MQTT Broker / AWS IoT Core

양쪽은 RPC_DESIGN의 토픽/페이로드 규격으로 상호 통신.
```

### 2.4 모바일/불안정 환경 특성 및 설계 방향

이 SDK는 “서버용”이지만, 대상 환경이 **모바일(차량/디바이스)** 일 수 있다는 점에서 일반적인 백엔드 서버와 다르다.

- **특징**
  - 네트워크 품질이 일정하지 않으며, 이동/전원 상태에 따라 **불시에 연결이 끊기거나 시스템이 종료(shutdown)** 될 수 있다.
  - 재부팅 후 동일 서비스가 다시 올라오더라도, 이전 세션 상태는 보존되지 않을 수 있다.
- **RPC Client SDK와의 비교**
  - Client SDK(`maas-rpc-client-sdk`)는
    - `wss_mqtt_client` 의 **auto_reconnect / auto_resubscribe**, 지수 백오프 재시도에 의존하여 연결을 복구하고,
    - `call()` 측에서 **타임아웃 + 재시도** 전략을 취함으로써 서버 측 일시 장애/끊김을 견딘다.
  - Server SDK는
    - **요청을 수신하고 처리하는 쪽**이므로, 재시작·끊김 시 “요청 손실/중복”에 대한 방어가 중요하다.
- **Server SDK 설계 방향**
  - Transport 레벨
    - MQTT/AWS IoT 전송 모두에서 **자동 재연결 및 재구독(auto-resubscribe)** 지원.
    - QoS 1(At-least-once)을 기본으로 사용하여, 네트워크 단절 구간 이후에도 가능한 한 메시지를 재전달받도록 한다.
  - Runtime 레벨
    - 최근 처리한 `request_id` 캐시를 유지하여 **중복 요청에 대한 idempotency** 패턴을 지원할 수 있도록 훅 제공(예: “이미 처리된 요청이면 동일 응답 재전송 또는 무시”).
    - 핸들러 구현 가이드에서 **idempotent 설계**(동일 요청에 대해 부작용이 중복 발생하지 않도록) 를 권장한다.
  - 클라이언트와의 협조
    - Client SDK 측에서는 타임아웃 후 **재시도 정책**을 취하고, Server SDK 측에서는 위의 idempotent 처리와 결합해 **at-least-once + 안전한 재시도** 모델을 완성한다.


---

## 3. 모듈/패키지 구조 설계

> 실제 리포지토리 구조는 이후 확정하되, 여기서는 Python 패키지 기준으로 개념적 구조를 정의한다.  
> (예: `SDK/maas-rpc-server-sdk/maas_rpc_server/` 등)

### 3.1 상위 패키지 구조 (예시)

```text
maas-rpc-server-sdk/
├── maas_rpc_server/
│   ├── __init__.py
│   ├── config.py          # 설정 로딩, 브로커/토픽/인증/transport 관련
│   ├── server.py          # 서버 런타임, 메인 엔트리포인트(Server)
│   ├── runtime.py         # 디스패처, 요청/응답 파이프라인
│   ├── transport/
│   │   ├── __init__.py
│   │   ├── base.py        # TransportInterface (추상)
│   │   ├── mqtt.py        # 기본 순수 MQTT 전송 (paho-mqtt 등)
│   │   └── aws_iot.py     # 옵션: AWS IoT Core 전송 (AWS IoT Device SDK)
│   ├── decorators.py      # @rpc_service, @rpc_action 등
│   ├── models.py          # Request/Response, Context 데이터 모델
│   ├── exceptions.py      # 서버 SDK용 예외 정의
│   ├── logging.py         # 로깅/트레이싱 훅 (선택)
│   └── utils.py           # 공용 유틸 (request_id 생성 등)
└── examples/
    ├── remote_uds_server.py
    └── remote_dashboard_server.py
```

### 3.2 주요 모듈 역할

- **`config.py`**
  - 브로커 접속 정보, 기본 토픽 패턴, 인증 및 전송(transport) 관련 설정을 관리한다.
  - 예: `ServerConfig`
    - `transport_type` (예: `"mqtt"`, `"aws_iot"`)
    - `mqtt_host`, `mqtt_port`, `use_tls`
    - `aws_iot_endpoint`, `aws_iot_client_id`
    - `aws_iot_cert_path`, `aws_iot_private_key_path`, `aws_iot_ca_cert_path`
    - `thing_name` (엣지 서버의 IoT Thing 이름 — 구독 패턴의 라우팅 키)
    - `service_definitions` (로드할 서비스 모듈 목록)
  - 설정 로딩 편의를 위해 다음과 같은 생성 헬퍼를 제공한다.
    - `ServerConfig.from_ini(path: str)`  
      - INI 형식 파일에서 설정을 로드한다. 섹션/키 예:
        - `[server] transport_type, thing_name, ...`
        - `[mqtt] host, port, use_tls, ...`
        - `[aws_iot] endpoint, client_id, cert_path, private_key_path, ca_cert_path, ...`
    - `ServerConfig.from_env(prefix: str = "SERVER_")`  
      - 환경변수에서 설정을 로드한다. 예: `SERVER_TRANSPORT_TYPE`, `SERVER_MQTT_HOST` 등.
    - 필요 시 `from_ini_and_env()` 형태로 INI + 환경변수 오버라이드 조합도 제공할 수 있다.

- **`transport/`**
  - 공통 전송 추상화 및 구현체들을 포함한다.
  - `base.py`
    - `TransportInterface`: `connect()`, `disconnect()`, `subscribe()`, `publish()` 등 정의.
  - `mqtt.py`
    - 기본 순수 MQTT 브로커 연결 (paho-mqtt 등).
    - subscribe/publish 인터페이스를 단순화하여 `runtime.py` 가 의존한다.
    - 재연결 정책, QoS, keepalive 등 처리.
  - `aws_iot.py`
    - AWS IoT Core MQTT 연결을 위한 전송 구현.
    - **전제**: AWS IoT Device SDK(v2) 설치 및 AWS 관련 환경변수(프로파일/리전 등) 또는 자격증명 파일이 사전에 설정되어 있음.
    - 내부적으로 AWS IoT Device SDK가 제공하는 MQTT pub/sub IPC를 사용한다.
      - 예: `mqtt_connection_builder.mtls_from_path(...)` 로 `mqtt.Connection` 생성
      - `connection.connect()`, `connection.publish(topic, payload, qos)`, `connection.subscribe(topic, qos, callback)` 를 통해 MQTT 동작 수행
    - 엔드포인트/인증서/키는 다음 두 가지 중 하나로 구성한다.
      - `ServerConfig` (예: INI/환경변수에서 로딩된 `aws_iot_endpoint`, `aws_iot_cert_path` 등)
      - AWS IoT Device SDK가 참조하는 기본 환경설정(AWS_PROFILE, AWS_REGION 등)
    - 이 MQTT 연결을 감싸는 `AwsIotTransport` 클래스를 통해 `TransportInterface` 를 구현하여,
      상위 레이어에서 전송 방식(MQTT 브로커 vs AWS IoT Core)이 완전히 은닉되도록 한다.

- **`runtime.py`**
  - 서버 SDK의 핵심 런타임.
  - 기능:
    - 요청 수신 루프
    - JSON/MessagePack 등 직렬화/역직렬화
    - service/action 기반 핸들러 라우팅
    - 예외 → 표준 에러 응답 매핑
    - 요청 컨텍스트(`RequestContext`) 생성 및 핸들러 전달

- **`decorators.py`**
  - 서비스/액션 핸들러 등록을 위한 데코레이터 제공.
  - 예:
    - `@rpc_service("RemoteUDS")` : 서비스 클래스/모듈 등록
    - `@rpc_action("readDTC")` : 액션 핸들러 등록
  - 런타임이 이 메타데이터를 기반으로 디스패치 테이블을 구성한다.

- **`models.py`**
  - 서버 SDK 내부에서 사용하는 데이터 모델 정의.
  - 예:
    - `RpcRequestEnvelope` (request_id, response_topic, request)
    - `RpcResponseEnvelope` (request_id, result, error)
    - `RequestContext` (thing_name, oem, asset, client_id, jwt_claims, raw_message 등)

- **`exceptions.py`**
  - 서버 SDK에서 사용하는 표준 예외 타입 정의.
  - 예:
    - `RpcServerError` (내부 에러)
    - `RpcBadRequestError` (요청 형식 오류)
    - `RpcUnauthorizedError` (인증/인가 실패)
    - 이 예외들은 `code`, `message` 필드에 매핑된다.

- **`server.py`**
  - 외부에서 사용하는 메인 엔트리포인트.
  - 예: `Server` 클래스
    - `start()`, `stop()`, `run_forever()` 메서드 제공
    - 서비스 모듈 등록, 설정 로딩, MQTT 연결 초기화까지 한 번에 처리

---

## 4. RPC Server SDK 사용 UX (목표)

### 4.1 기본 서버 예제 (개념)

```python
from maas_rpc_server import Server, rpc_service, rpc_action, RequestContext


@rpc_service("RemoteUDS")
class RemoteUdsService:
    @rpc_action("readDTC")
    async def read_dtc(self, ctx: RequestContext, params: dict) -> dict:
        # ctx.thing_name, ctx.oem, ctx.asset, ctx.client_id, ctx.jwt_claims 등 사용 가능
        result = await self._read_dtc_from_backend(params)
        return {"dtcList": result}


if __name__ == "__main__":
    server = Server.from_ini("server.ini")  # 또는 Server(config=ServerConfig.from_env())
    server.run_forever()
```

- 서비스 구현자는
  - **서비스 이름("RemoteUDS")** 과 **액션 이름("readDTC")** 만 맞추면 되고,
  - MQTT 토픽, request_id/response_topic, 에러 포맷 등은 SDK에 위임한다.

### 4.2 동기/비동기 처리

- 서버 SDK는 기본적으로 **비동기(asyncio)** 기반을 권장한다.
  - 여러 vehicle/client에서 동시에 들어오는 RPC 요청을 하나의 프로세스에서 효율적으로 처리하기 위해,
    Transport 계층(MQTT/AWS IoT)과 Runtime 계층(스트리밍, subscribe_stream 등)을 비동기 코어로 설계한다.
- 대신, **사용 편의성을 위해 동기 래퍼를 함께 제공**한다.
  - 예: 내부적으로 asyncio 이벤트 루프를 관리하는 `ServerSync` 또는 `Server.run_sync()` 형태의 헬퍼.
  - 서비스 개발자는 필요 시 동기 스타일로 핸들러를 작성하고, SDK가 이를 비동기 이벤트 루프 위에서 실행하도록 래핑한다.
  - 또한, `@rpc_action(sync=True)` 옵션 또는 별도 헬퍼를 통해 동기 핸들러를 스레드풀 등으로 자동 래핑하는 기능을 제공할 수 있다.

### 4.3 단일 클라이언트 전용 서비스 제어 (예: RemoteDMS)

일부 서비스(예: RemoteDMS)는 **동시에 하나의 클라이언트만 연결/요청을 허용**해야 할 수 있다. 이를 위해 RPC Server SDK는 다음과 같은 제어 기능을 제공하는 것을 목표로 한다.

- **서비스 수준 동시성 정책**
  - 서비스 등록 시 “동시 접속 허용 개수”를 설정할 수 있도록 한다.
    - 예: `@rpc_service("RemoteDMS", max_concurrent_clients=1)`
  - SDK 런타임은 `(oem, asset, client_id)` 조합 단위로 현재 활성 세션/요청 수를 추적한다.
- **단일 클라이언트 강제 전략**
  - 정책 예시:
    - (a) 두 번째 클라이언트 요청을 **즉시 거부** (`error.code = "CONCURRENCY_LIMIT_EXCEEDED"`)
    - (b) 기존 클라이언트를 강제 종료하고 새 클라이언트를 허용 (옵션으로만 지원)
  - 어떤 전략을 쓸지는 서비스별 설정으로 선택 가능하게 한다.
- **클라이언트 SDK와의 연동**
  - RPC Client SDK가 위 에러 코드를 인지하고,
    - 사용자에게 “이미 다른 세션이 사용 중”임을 알리거나,
    - 재시도/백오프 정책을 적용할 수 있도록 한다.
  - 이렇게 하면 RemoteDMS처럼 **“동시에 하나의 클라이언트만 허용되는 서비스”** 도 SDK 레벨에서 일관되게 제어할 수 있다.

---

## 5. 개발 단계 계획

### 5.1 Phase 1 — 요구사항 정리 및 최소 스펙 확정

- [ ] 서버 SDK의 **최소 지원 대상 서비스/액션 범위** 정리
  - 예: RemoteUDS / RemoteDashboard 우선
- [ ] 인증/컨텍스트 정보에서 **필수 클레임/필드** 정의
  - thing_name, oem, asset, client_id, 권한 스코프 등
- [ ] 서버 측에서 사용할 MQTT 라이브러리(paho-mqtt 등) 및 런타임 제약(Python 버전 등) 확정

### 5.2 Phase 2 — Transport 추상화 및 기본 MQTT 구현 (`transport/base.py`, `transport/mqtt.py`)

- [ ] `TransportInterface` 정의
  - `connect()`, `disconnect()`, `subscribe()`, `publish()` 등 공통 메서드 시그니처 확정
- [ ] 기본 MQTT 전송(`MqttTransport`) 구현
  - MQTT 클라이언트 래퍼: connect / disconnect / subscribe / publish
  - QoS, keepalive, 재연결 정책 (모바일/불안정 환경을 고려한 지수 백오프, 재구독 등)
- [ ] `WMT/+/{thing_name}/+/+/request` 토픽 구독 로직 구현
  - `thing_name`은 `ServerConfig`에서 읽어 구독 패턴에 삽입
  - 수신 메시지에서 `oem`, `asset` 세그먼트를 파싱하여 `RequestContext`에 주입
- [ ] TLS, 인증서, JWT 관련 설정 훅 제공 (필요 시)

### 5.3 Phase 3 — AWS IoT 전송 구현 (옵션) (`transport/aws_iot.py`)

- [ ] AWS IoT Core MQTT 연결용 `AwsIotTransport` 구현
  - AWS IoT Device SDK 활용
  - 엔드포인트, client_id, 인증서/프라이빗 키/CA 번들 설정 처리
- [ ] `TransportInterface` 구현체로서 `runtime.py` 에서 투명하게 사용 가능하도록 설계
- [ ] `ServerConfig.transport_type` 이 `"aws_iot"` 인 경우 이 구현을 선택

### 5.4 Phase 4 — 런타임/디스패처 구현 (`runtime.py`, `models.py`, `exceptions.py`)

- [ ] 요청 Envelope 파싱/검증
  - `request_id`, `response_topic`, `request` 필수 필드 검사
- [ ] `RequestContext` 설계 및 채우기
  - thing_name, oem, asset, client_id, jwt_claims, raw_message 등
  - `oem`, `asset`은 요청 토픽(`WMT/…/{oem}/{asset}/request`)에서 파싱
- [ ] service/action 기반 디스패치 테이블 구조 정의
  - (service, action) → 핸들러 함수 매핑
- [ ] 예외 → 표준 에러 응답 변환 로직 구현
  - `RpcBadRequestError`, `RpcUnauthorizedError`, `RpcServerError` 등
- [ ] 응답 Envelope 직렬화 및 `response_topic` 발행
 - [ ] 모바일/불안정 환경 대응 기능 설계 및 부분 구현
   - 최근 처리한 `request_id` 캐시 관리 훅(중복 요청 방지/재응답 지원)
   - 재시도/재연결 시나리오에서 idempotent 처리를 위한 베이스 유틸리티 제공

### 5.5 Phase 5 — 데코레이터 및 서버 엔트리포인트 (`decorators.py`, `server.py`)

- [ ] `@rpc_service(service_name)` 데코레이터 구현
  - (일반화 후 이름: `@rpc_service(service_name)`)
  - 클래스 또는 함수 기반 서비스 정의 지원
- [ ] `@rpc_action(action_name)` 데코레이터 구현
  - 메서드/함수를 디스패처에 등록
- [ ] `Server` 엔트리포인트 구현
  - 설정 로딩, 서비스 등록, MQTT 연결, 런타임 시작
- [ ] 간단한 예제(RemoteUDS readDTC 서버) 작성

### 5.6 Phase 6 — 통합 테스트 및 예제 강화

- [ ] 클라이언트 SDK(`maas-rpc-client-sdk`)와 실제 MQTT 브로커를 통한 **종단 간 테스트**
  - 클라이언트: `RpcClient.call("RemoteUDS", {...})`
  - 서버: Server SDK 예제 서비스
- [ ] 에러/타임아웃/재연결 시나리오 테스트
- [ ] RemoteDashboard 등 추가 서비스 예제 작성

### 5.7 Phase 7 — 문서화 및 운영 고려

- [ ] RPC Server SDK README, 설치/사용 가이드 작성
- [ ] 서비스 개발자를 위한 “베스트 프랙티스” 문서화
  - 에러 코드 정의, 로깅 전략, 성능 튜닝 팁 등
- [ ] 향후 확장 포인트 정의
  - 서비스 버전닝, 멀티 테넌트, 서비스 디스커버리 등

---

## 6. 향후 확장 방향

- **다른 언어 서버 SDK**
  - Python 서버 SDK를 기준으로, Go/Node.js 등으로 확장 가능하도록 프로토콜 수준에서 일관성 유지.
- **스키마 기반 코드 생성**
  - 서비스별 Request/Response 스키마가 정리되면, 서버/클라이언트 양쪽 코드 스텁을 자동 생성하는 도구로 확장.
- **고급 기능**
  - 스트리밍 API 서버 측 추상화 (call_stream, subscribe_stream에 대응)
  - 백프레셔, 메시지 큐 통합, 모니터링/메트릭 내장 등.

---

## 7. 서비스 개발 가이드 (베스트 프랙티스)

RPC Server SDK를 사용하는 서비스 개발자를 위한 권장 가이드이다. SDK는 공통적인 훅과 컨텍스트를 제공하고, **정책·도메인별 로직은 각 서비스에서 구현**하는 것을 전제로 한다.

### 7.1 단일 클라이언트 전용 서비스 (예: RemoteDMS)

- **단일 클라이언트 제약이 필요한 이유**
  - RemoteDMS 등 일부 서비스는 동시 두 클라이언트가 같은 차량/장비에 대해 작업하면 **상태 충돌, 자원 경합, 보안 위험**이 발생할 수 있다.
  - 이런 서비스는 “한 시점에 최대 1개의 활성 세션만 허용”하는 정책이 필요하다.

- **권장 패턴**
  1. **세션 개념 도입**
     - 서비스별로 `session_id` 또는 `(oem, asset, client_id)` 조합을 세션으로 보고 관리한다.
     - 세션 시작/종료를 명시하는 RPC(action)를 설계한다. 예:
       - `openSession`, `closeSession`, `heartbeatSession`
  2. **세션 매니저 구현 (서비스 레벨)**
     - SDK가 제공하는 `RequestContext`에서 `oem`, `asset`, `client_id`를 읽어,
       서비스 내부의 세션 매니저(예: 인메모리 딕셔너리, 외부 KV 스토어)에 기록한다.
     - 이미 활성 세션이 있는 상태에서 또 다른 클라이언트가 `openSession`을 호출하면:
       - `CONCURRENCY_LIMIT_EXCEEDED` 와 같은 표준화된 에러 코드를 사용해 즉시 거부한다.
  3. **세션 만료/이탈 처리**
     - 클라이언트가 정상 종료 시 `closeSession` 을 호출하도록 서비스/클라이언트 스펙에 명시한다.
     - 비정상 종료/네트워크 이탈에 대비해:
       - 주기적인 `heartbeatSession` 요청 또는 스트림 이벤트를 요구하고,
       - “마지막 heartbeat 시각 + grace period” 기준으로 세션을 만료 처리한다.
     - MQTT/AWS IoT 연결 단절 신호는 참고 정보로만 사용하고, **최종 세션 종료 판단은 heartbeat/타임아웃 규칙**으로 수행한다.
  4. **에러 코드 및 클라이언트 UX**
     - 단일 클라이언트 제한에 걸렸을 때는 서비스 공통 에러 스키마의 `error.code` 에 다음과 같은 값을 권장한다.
       - `CONCURRENCY_LIMIT_EXCEEDED`
       - `SESSION_ALREADY_ACTIVE`
     - RPC Client SDK 또는 서비스별 클라이언트 래퍼(RemoteDmsClient 등)에서 이 코드를 인지하여:
       - 사용자에게 “이미 다른 세션이 사용 중”임을 알려주거나,
       - 일정 시간 후 재시도하는 UX를 구현한다.

### 7.2 모바일/불안정 네트워크 환경에서의 서비스 설계

- **Idempotent 핸들러**
  - 동일 `request_id`에 대한 재전달/재시도에 대비하여, 가능한 한 **idempotent** 하게 핸들러를 설계한다.
  - 예: 이미 처리된 작업이면 같은 결과를 반환하거나 “이미 처리됨” 에러를 명시적으로 돌려주는 식.
- **서버 측 request_id 캐시 활용**
  - RPC Server SDK가 제공하는 `request_id` 및 캐시 훅(계획된 기능)을 활용해,
    서비스가 “이미 처리한 요청”을 식별하고 중복 처리를 피하거나 동일 응답을 재전송할 수 있도록 구현한다.

### 7.3 서비스별 설정/정책 정의

- 각 서비스는 다음 항목을 명시적으로 문서화하고, 코드/설정으로 표현하는 것이 좋다.
  - 허용 동시 세션 수 (예: 1, N, 무제한)
  - 세션 타임아웃/heartbeat 주기
  - 주요 에러 코드와 의미 (`CONCURRENCY_LIMIT_EXCEEDED`, `SESSION_TIMEOUT`, `SESSION_NOT_FOUND` 등)
  - 재시도/보상 트랜잭션 전략 (클라이언트/서버 양쪽)

RPC Server SDK는 위와 같은 패턴을 **구현하기 쉽게 하는 공통 인프라**(컨텍스트, 전송 추상화, request_id, 에러 스키마 등)를 제공하고,  

- `docs/RPC_DESIGN.md` — RPC 전송 방법론 및 MQTT 계층 설계
- `docs/TOPIC_AND_ACL_SPEC.md` — WMT/WMO 토픽 패턴 및 ACL 규격
- `docs/RPC_CLIENT_SDK_DEVELOPMENT_PLAN.md` — RPC Client SDK 개발 계획서

