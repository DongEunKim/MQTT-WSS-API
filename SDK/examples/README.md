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

## 로컬 MQTT 브로커 (선택)

```bash
cd SDK && docker compose up -d
```

기본 URL: `mqtt://localhost:1883` (환경변수 `MQTT_URL`로 변경 가능).

## 디버깅 스크립트

| 스크립트 | 설명 |
|----------|------|
| [mqtt_topic_monitor.py](mqtt_topic_monitor.py) | 브로커 토픽 실시간 출력 (`WMT/#`, `WMO/#` 필터 권장) |
| [tgu_simulator_mqtt.py](tgu_simulator_mqtt.py) | WMT 요청 수신 후 Mock 응답을 `Response Topic`으로 발행하는 단순 시뮬레이터 |

> 엔드투엔드 RPC 검증은 `maas-client-sdk` / `maas-server-sdk` 단위 테스트 및 실제 AWS IoT Core 연동으로 수행한다.

## 문서

- [RPC 설계](../../docs/RPC_DESIGN.md)
- [토픽 규격](../../docs/TOPIC_AND_ACL_SPEC.md)
