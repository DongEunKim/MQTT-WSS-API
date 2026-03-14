# 예제 실행 방법

Mock 서버와 발행/구독 클라이언트를 직접 실행해볼 수 있습니다.

**기본**: publisher, subscriber (동기). **고급**: *_async (비동기).

## 1. 패키지 설치

**프로젝트 루트**에서:

```bash
pip install -e SDK/wss-mqtt-client
pip install -e SDK/tgu-rpc-sdk   # TGU RPC 예제용
```

## 2. Mock 서버 실행

**터미널 1**:

```bash
python SDK/examples/run_mock_server.py
# 또는 python SDK/examples/run_mock_server.py --port 9000
```

서버가 `ws://localhost:8765` 에서 대기합니다.

## 3. 클라이언트 예제 (wss-mqtt-client)

**터미널 2, 3** — 예제는 `SDK/wss-mqtt-client/examples/` 에 있습니다:

```bash
# 구독 (기본, 동기)
python SDK/wss-mqtt-client/examples/subscriber.py
RUN_TIMEOUT=5 python SDK/wss-mqtt-client/examples/subscriber.py

# 발행 (기본, 동기)
python SDK/wss-mqtt-client/examples/publisher.py
python SDK/wss-mqtt-client/examples/publisher.py --message '{"action":"start"}'
python SDK/wss-mqtt-client/examples/publisher.py -n 5 -i 2
python SDK/wss-mqtt-client/examples/publisher.py --binary

# 고급 (비동기)
AUTO_RECONNECT=1 python SDK/wss-mqtt-client/examples/subscriber_async.py
python SDK/wss-mqtt-client/examples/publisher_async.py
WSS_MQTT_URL=ws://localhost:8765 python SDK/wss-mqtt-client/examples/batch_publish_subscribe.py
python SDK/wss-mqtt-client/examples/rpc_pattern.py
```

## 3-2. TGU RPC SDK 예제

```bash
# Mock 서버 자동 시작 + RPC 호출 (권장)
python SDK/tgu-rpc-sdk/examples/run_rpc_example.py

# Mock 서버 별도 실행 시
# 터미널 1: python SDK/examples/run_mock_server.py
# 터미널 2: WSS_MQTT_URL=ws://localhost:8765 python SDK/tgu-rpc-sdk/examples/rpc_call_wss_api.py
```

## 4. 기타 (wss-mqtt-client)

```bash
python SDK/wss-mqtt-client/examples/basic_publish_subscribe.py
python SDK/wss-mqtt-client/examples/mqtt_subscriber.py   # MQTT 브로커 (docker)
python SDK/wss-mqtt-client/examples/mqtt_publisher.py
```

## 5. 실제 MQTT 브로커 + TGU 시뮬레이터 (디버깅용)

실제 브로커(Mosquitto)와 TGU 시뮬레이터를 사용하여 RPC를 테스트하고, 토픽 모니터로 모든 메시지를 감시할 수 있다.

```bash
# 1. 브로커 실행
cd SDK && docker compose up -d

# 2. TGU 시뮬레이터 (WMT 요청 수신 → Mock 응답 발행)
python SDK/examples/tgu_simulator_mqtt.py

# 3. 토픽 모니터 (디버깅용 — 모든 토픽 실시간 출력)
python SDK/examples/mqtt_topic_monitor.py
# 또는 WMT/WMO만: python SDK/examples/mqtt_topic_monitor.py --filter "WMT/#" "WMO/#"
# ※ WMT/WMO 둘 다 보려면 모니터를 먼저 실행하고, "구독 완료" 메시지 출력 후 2~3초 뒤에 RPC 실행

# 4. RPC 호출 (별도 터미널)
python SDK/tgu-rpc-sdk/examples/rpc_call_mqtt.py
```

**환경변수**: `MQTT_URL` (기본 `mqtt://localhost:1883`). WebSocket은 `ws://localhost:9001`.

**기본 pub/sub** (같은 브로커):

```bash
python SDK/wss-mqtt-client/examples/mqtt_subscriber.py   # 터미널 1
python SDK/wss-mqtt-client/examples/mqtt_publisher.py   # 터미널 2
```

## 6. 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| WSS_URL | ws://localhost:8765 | Mock 서버 URL |
| WSS_MQTT_URL | wss://api.example.com/... | API URL |
| WSS_MQTT_TOKEN | - | JWT 토큰 |
| TOPIC | test/response | 구독 토픽 |
| PUBLISH_TOPIC | test/command | 발행 토픽 |
| RUN_TIMEOUT | - | subscriber 대기 시간(초) |
| AUTO_RECONNECT | - | 1 시 자동 재연결 |
| MQTT_URL | mqtt://localhost:1883 | MQTT 브로커 (TCP). WebSocket: ws://localhost:9001 |
