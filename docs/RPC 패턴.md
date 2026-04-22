```mermaid
sequenceDiagram
    autonumber

    actor Client as Client (Web App)
    participant Broker as MQTT 5.0 브로커
    participant Edge as Edge RPC 서버

    rect rgb(240, 253, 244)
    Note over Client, Edge: [패턴 A] Liveness
    Client->>Broker: Subscribe WMO/+/+/+/{clientId}/response
    Edge->>Broker: Subscribe WMT/{ThingType}/{Service}/{VIN}/+/request
    Client->>Broker: PUBLISH WMT/.../request (QoS 0, Expiry, CorrData, ResponseTopic=WMO/.../response)
    Broker->>Edge: 라우팅
    Edge->>Edge: 로컬 조회
    Edge->>Broker: PUBLISH WMO/.../response (QoS 0, CorrData)
    Broker->>Client: 응답
    end

    rect rgb(254, 252, 232)
    Note over Client, Edge: [패턴 B·D] 신뢰성 제어·시한성
    Client->>Broker: PUBLISH WMT/.../request (QoS 1, Expiry[패턴D], CorrData)
    Broker->>Edge: 라우팅
    Edge->>Broker: PUBLISH WMO/.../response (QoS 1, ReasonCode)
    Broker->>Client: 응답
    end

    rect rgb(238, 242, 255)
    Note over Client, Edge: [패턴 C] 스트리밍
    Client->>Broker: PUBLISH WMT/.../request
    Broker->>Edge: 라우팅
    loop 청크
        Edge->>Broker: PUBLISH WMO/.../event (CorrData)
        Broker->>Client: 청크
    end
    Edge->>Broker: PUBLISH WMO/.../response (is_EOF)
    Broker->>Client: 완료
    end

    rect rgb(255, 245, 245)
    Note over Client, Edge: [패턴 E] 독점 세션
    Client->>Broker: session_start 등 (QoS 1)
    Edge->>Edge: Lock(clientId)
    Broker->>Edge: 타 클라이언트 요청
    Edge--xBroker: 0x8A Server Busy
    Client--xBroker: 단절
    Broker->>Edge: (선택) 브로커 수명주기·presence 이벤트
    Edge->>Edge: Lock 해제
    end
```

## 1. 개요 및 공통 규약

엣지에서 동작하는 RPC 서비스를 클라이언트가 **MQTT 5.0**으로 호출할 때의 패턴을 정의한다. 토픽·메타데이터 규격의 단일 출처는 [TOPIC_AND_ACL_SPEC.md](TOPIC_AND_ACL_SPEC.md) 및 [RPC_DESIGN.md](RPC_DESIGN.md)이다.

### 1.1. 통신 기반

- **엣지:** `maas-server-sdk`로 `WMT/{ThingType}/{Service}/{VIN}/+/request` 구독.
- **클라이언트:** `maas-client-sdk`로 요청 발행 및 `WMO/+/+/+/{clientId}/response|event` 구독 (전송: TCP / TLS / WSS 등 브로커·배포에 따름).

### 1.2. MQTT 5 속성

1. **User Property:** `content-type` 등 (JSON 권장).
2. **Response Topic:** `WMO/{ThingType}/{Service}/{VIN}/{ClientId}/response` — 클라이언트의 MQTT ClientId가 경로에 포함되며, [TOPIC_AND_ACL_SPEC.md](TOPIC_AND_ACL_SPEC.md)의 ACL과 일치해야 한다.
3. **Correlation Data:** 요청-응답·스트림 청크 매칭.
4. **Reason Code / User Property `reason_code`:** [TOPIC_AND_ACL_SPEC.md](TOPIC_AND_ACL_SPEC.md) Reason Code 표 준수.

### 1.3. 컴포넌트 가용성

일부 엣지·브로커 조합에서는 LWT(Last Will)가 제한될 수 있다. Heartbeat 토픽·브로커 제공 수명주기 이벤트(`MaasServer.lifecycle_topics`) 등으로 가용성을 보조할 수 있다.

### 1.4. Reason Code

[TOPIC_AND_ACL_SPEC.md](TOPIC_AND_ACL_SPEC.md) §7 및 [RPC_DESIGN.md](RPC_DESIGN.md) 참고.

---

## 2. RPC 패턴별 설계 명세

### 패턴 A: 상태 및 정보 조회 (Liveness/Health Check)

- 서버: 응답을 **QoS 0**, `Correlation Data` 유지.
- 클라이언트: **QoS 0**, 앱 타임아웃 약 3초 권장. QoS 0은 보통 비큐잉이라 Message Expiry는 생략·실효 제한적.

### 패턴 B: 신뢰성 보장 단일 제어 (Reliable Control)

- 서버: **QoS 1** 응답, 실패 시 Reason Code·`error_detail`.
- 클라이언트: **QoS 1**, 타임아웃 10~15초 등 여유 있게.

### 패턴 C: 대용량 데이터 스트리밍 (Chunked Streaming)

- 서버: 청크는 `WMO/.../event`, 완료는 `WMO/.../response` + `is_EOF`, 필요 시 Topic Alias.
- 클라이언트: 동일 `Correlation Data`로 청크 수신, `is_EOF`로 종료.
- 스트리밍 중 클라이언트 단절 시 브로커·서버가 제공하는 단절 감지(수명주기 이벤트 등)로 전송을 중단할 수 있다.

### 패턴 D: 시한성 안전 제어 (Time-bound)

- 클라이언트: **QoS 1**로 요청(브로커 큐·지연 전달 시 만료 의미 있음). SDK는 `timeout`과 **Message Expiry**를 맞춤. **Clean Start** 등으로 stale 응답 방지. QoS 0만으로는 브로커 Expiry 실효가 거의 없음.

### 패턴 E: 독점 세션 (Exclusive Session / Remote UDS)

- 서버: 세션 Lock, 타 `clientId`에 **0x8A**, 단절 시 Lock 해제.
- 클라이언트: 세션 획득·해제 RPC 순서 준수, **QoS 1** 권장.

---

## 3. 세션 및 연결 관리 표준

### 3.1. 웹 클라이언트 Keep-Alive

WebSocket 등 프록시·로드밸런서 Idle Timeout을 고려하여 MQTT **Keep-Alive 30~45초** 권장.
