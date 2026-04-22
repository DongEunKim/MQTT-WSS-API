# 예제 및 로컬 브로커

## 패키지 설치

저장소 루트에서:

```bash
pip install -r requirements.txt
```

또는:

```bash
pip install -e SDK/client/python/maas-client-sdk[dev]
pip install -e SDK/server/python/maas-server-sdk[dev]
```

설치 스크립트:

```bash
bash SDK/client/python/install.sh --dev
bash SDK/server/python/install.sh --dev
```

## 로컬 MQTT 브로커 (선택)

예제는 기본으로 **TCP 1883** 에 붙는다.

[Eclipse Mosquitto](https://mosquitto.org/) 를 패키지로 설치한 뒤, 이 저장소의 설정으로 브로커를 띄운다.

```bash
sudo apt update
sudo apt install -y mosquitto
```

시스템에 이미 `mosquitto` 서비스가 1883을 쓰고 있으면 충돌할 수 있다. 그때는 한쪽만 쓰도록 한다.

```bash
# (선택) 배포판 기본 서비스가 1883을 잡고 있으면 잠시 중지
sudo systemctl stop mosquitto
```

저장소 **루트**에서, 이 프로젝트용 설정으로 **포그라운드** 실행 (MQTT 1883 + WS 9001, 익명 허용):

```bash
mosquitto -c SDK/mosquitto/mosquitto.conf -v
```

다른 터미널에서 `rpc_local_*` 예제를 실행한다. 종료는 해당 터미널에서 Ctrl+C.

기본 URL: `mqtt://localhost:1883` (환경변수 `MQTT_URL` / `MQTT_HOST`·`MQTT_PORT`로 변경 가능).

## SDK 기반 RPC 예제 (권장)

`maas-client-sdk` / `maas-server-sdk`를 설치한 뒤, 브로커를 띄우고 다음 순서로 실행한다. 클라이언트는 생성자에 `thing_type` / `service` / `vin`을 고정하고 **`call(action, params)`** 로 한 번 호출한다.

| 순서 | 스크립트 | 설명 |
|------|----------|------|
| 1 | [rpc_local_echo_service.py](rpc_local_echo_service.py) | `MaasServer`로 `WMT/.../request` 구독, `get` 액션 목 응답 |
| 2 | [rpc_local_call_client.py](rpc_local_call_client.py) | `MaasClient`로 동일 토픽·페이로드 규격에 맞춰 `call` 1회 |

환경변수 `MQTT_HOST`(기본 `127.0.0.1`), `MQTT_PORT`(기본 `1883`)로 브로커를 바꿀 수 있다.

## 디버깅용 스크립트 (SDK 미사용)

원시 `paho-mqtt`만 사용하는 보조 도구이다. 토픽 덤프·구형 시뮬레이터 용도.

| 스크립트 | 설명 |
|----------|------|
| [mqtt_topic_monitor.py](mqtt_topic_monitor.py) | 브로커 토픽 실시간 출력 (`WMT/#`, `WMO/#` 필터 권장) |
| [tgu_simulator_mqtt.py](tgu_simulator_mqtt.py) | **비권장.** 구형 페이로드/토픽 패턴. 새 규격 검증은 위 RPC 예제 사용 |

## 문서

- [RPC 설계](../../docs/RPC_DESIGN.md)
- [토픽 규격](../../docs/TOPIC_AND_ACL_SPEC.md)
