# MaaS SDK — Python

이 디렉터리에는 다음 패키지가 있다.

| 디렉터리 | 패키지 |
|----------|--------|
| `maas-client-sdk/` | 클라이언트용 MQTT 5.0 RPC SDK |

## 설치

```bash
pip install -e maas-client-sdk[dev]
```

## 사용

```python
from maas_client import MaasClient

client = MaasClient(
    endpoint="xxxx.iot.ap-northeast-2.amazonaws.com",
    client_id="my-app-id",
    token_provider=lambda: fetch_jwt(),  # 선택
)
client.connect()

r = client.call(
    thing_type="CGU",
    service="viss",
    action="get",
    vin="VIN-123456",
    payload={"path": "Vehicle.Speed"},
)
print(r.payload)

client.disconnect()
```

상세는 `maas-client-sdk/README.md` 및 `docs/RPC_DESIGN.md` 참고.
