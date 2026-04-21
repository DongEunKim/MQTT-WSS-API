# maas-client-sdk

MQTT 5.0 over WSS(AWS IoT Core) 기반 MaaS RPC 클라이언트 SDK.

## 요구 사항

- Python 3.10+
- `paho-mqtt` 2.x (MQTT 5.0)

## 설치

```bash
pip install -e .[dev]   # 개발(테스트) 포함
```

## 토픽·RPC

토픽 형식은 `docs/TOPIC_AND_ACL_SPEC.md` 를 따른다.

- `MaasClient` — 동기 API (기본)
- `MaasClientAsync` — `asyncio`용

RPC 호출 시 `action` 은 SDK가 페이로드에 넣는다. 서비스 구분은 토픽의 `{Service}` 세그먼트(`call(..., service=...)`)로 한다.

## 라이선스

Proprietary (프로젝트 정책에 따름).
