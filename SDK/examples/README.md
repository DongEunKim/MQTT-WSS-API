# 예제 실행 방법

Mock 서버와 발행/구독 클라이언트를 직접 실행해볼 수 있습니다.

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

이후 예제 실행 시에도 프로젝트 루트에서 작업합니다.

## 2. Mock 서버 실행

**터미널 1** (프로젝트 루트, 가상환경 활성화 후):

```bash
python SDK/examples/run_mock_server.py
# 또는 특정 포트 지정
python SDK/examples/run_mock_server.py --port 9000
```

서버가 `ws://localhost:8765` 에서 대기합니다.

## 3. 구독 클라이언트 실행

**터미널 2** (프로젝트 루트):

```bash
python SDK/examples/subscriber.py
```

`test/response` 토픽을 구독하며 메시지를 기다립니다.

## 4. 발행 클라이언트 실행

**터미널 3** (프로젝트 루트):

```bash
python SDK/examples/publisher.py
# 커스텀 메시지
python SDK/examples/publisher.py --message '{"action":"start","device_id":"001"}'
# 5회 발행, 2초 간격
python SDK/examples/publisher.py -n 5 -i 2
```

## 5. 동작 흐름

- Mock 서버는 **TGU 시뮬레이션**을 지원합니다.
- `X/command` 토픽으로 발행된 메시지는 자동으로 `X/response` 토픽 구독자에게 전달됩니다.
- 기본 토픽: 발행 `test/command` → 구독 `test/response`

## 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| WSS_URL | ws://localhost:8765 | Mock 서버 URL |
| SUBSCRIBE_TOPIC | test/response | 구독 토픽 |
| PUBLISH_TOPIC | test/command | 발행 토픽 |
