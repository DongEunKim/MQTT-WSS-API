# 예제 실행 방법

Mock 서버와 발행/구독 클라이언트를 직접 실행해볼 수 있습니다.

**기본**: publisher, subscriber (동기). **고급**: *_async (비동기).

## 1. 가상환경 구축 및 패키지 설치

**프로젝트 루트**에서:

```bash
# 가상환경 생성
python3 -m venv .venv

# 활성화 (Linux/macOS)
source .venv/bin/activate

# 패키지 설치
pip install -e SDK
```

## 2. Mock 서버 실행

**터미널 1**:

```bash
python SDK/examples/run_mock_server.py
# 또는 python SDK/examples/run_mock_server.py --port 9000
```

서버가 `ws://localhost:8765` 에서 대기합니다.

## 3. 구독 클라이언트 (기본, 동기)

**터미널 2**:

```bash
python SDK/examples/subscriber.py

# 테스트용 5초 후 종료
RUN_TIMEOUT=5 python SDK/examples/subscriber.py
```

## 4. 발행 클라이언트 (기본, 동기)

**터미널 3**:

```bash
python SDK/examples/publisher.py
python SDK/examples/publisher.py --message '{"action":"start"}'
python SDK/examples/publisher.py -n 5 -i 2  # 5회, 2초 간격
python SDK/examples/publisher.py --binary   # MessagePack
```

## 5. 고급 예제 (비동기)

```bash
# 비동기 구독 (async for, 자동 재연결)
AUTO_RECONNECT=1 python SDK/examples/subscriber_async.py

# 비동기 발행
python SDK/examples/publisher_async.py

# 배치 발행·다수 토픽 구독
WSS_MQTT_URL=ws://localhost:8765 python SDK/examples/batch_publish_subscribe.py

# RPC 패턴
python SDK/examples/rpc_pattern.py
```

## 6. 기타 예제

| 예제 | 설명 |
|------|------|
| basic_publish_subscribe.py | 기본 발행→구독→수신 (동기) |
| rpc_pattern.py | RPC 패턴 (비동기) |
| mqtt_subscriber.py | MQTT 브로커 직접 연결 (비동기) |
| mqtt_publisher.py | MQTT 브로커 발행 (비동기) |

## 7. 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| WSS_URL | ws://localhost:8765 | Mock 서버 URL |
| WSS_MQTT_URL | wss://api.example.com/... | API URL |
| WSS_MQTT_TOKEN | - | JWT 토큰 |
| WSS_URL | ws://localhost:8765 | Mock 서버 URL |
| TOPIC | test/response | 구독 토픽 (subscriber) |
| PUBLISH_TOPIC | test/command | 발행 토픽 (publisher) |
| RUN_TIMEOUT | - | subscriber run 대기 시간(초) |
| AUTO_RECONNECT | - | 1 시 자동 재연결 (subscriber_async) |
| MQTT_URL | mqtt://localhost:1883 | MQTT 브로커 (mqtt_* 예제) |

## 8. MQTT Transport

```bash
cd SDK && docker compose up -d

python SDK/examples/mqtt_subscriber.py   # 터미널 1
python SDK/examples/mqtt_publisher.py    # 터미널 2
```
