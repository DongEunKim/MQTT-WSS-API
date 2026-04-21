# maas-server-sdk

MQTT 5.0 기반 MaaS RPC 서비스(핸들러) SDK. Greengrass Component 등에서 장비 측 서비스를 구현할 때 사용한다.

## 요구 사항

- Python 3.10+
- `paho-mqtt` 2.x (MQTT 5.0)

인증서/키 연동은 추후 버전에서 추가할 수 있도록 연결 계층과 분리되어 있다.

## 설치

```bash
pip install -e .[dev]
```

## 개요

- `MaasServer(thing_type, service_name, vin, endpoint)` 가 `WMT/{ThingType}/{Service}/{VIN}/+/request` 를 구독한다.
- `@server.action("이름")` 은 페이로드 `{"action":"이름", ...}` 와 매칭한다.

## 문서

`docs/RPC_DESIGN.md`, `docs/TOPIC_AND_ACL_SPEC.md` 참고.
