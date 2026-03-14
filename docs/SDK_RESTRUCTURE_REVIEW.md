# SDK 구조 분리 검토

> wss_mqtt_client / tgu-rpc-sdk 분리 및 통합 설치에 대한 검토 문서

---

## 1. SDK 폴더 아래 wss_mqtt_client와 tgu-rpc-sdk 구조적 분리

### 1.1 제안 구조

```
SDK/
├── pyproject.toml              # 메타 패키지 (선택적, 통합 설치용)
├── wss-mqtt-client/            # 패키지 A (폴더명: hyphen, Python 모듈: underscore)
│   ├── pyproject.toml
│   ├── src/
│   │   └── wss_mqtt_client/
│   │       ├── __init__.py
│   │       ├── client.py
│   │       ├── client_sync.py
│   │       ├── transport/
│   │       ├── protocol.py
│   │       └── ...
│   ├── tests/
│   ├── examples/               # wss-mqtt-client 전용 예제
│   └── README.md
├── tgu-rpc-sdk/                # 패키지 B
│   ├── pyproject.toml
│   ├── src/
│   │   └── tgu_rpc/
│   │       ├── __init__.py
│   │       ├── client.py
│   │       └── topics.py
│   ├── tests/
│   ├── examples/               # TGU RPC 예제
│   └── README.md
├── examples/                   # 통합 예제 (선택)
│   ├── run_mock_server.py
│   └── README.md
└── docker-compose.yml          # 공통 (MQTT 브로커 테스트)
```

### 1.2 검토 의견

| 항목 | 의견 |
|------|------|
| **폴더명** | `wss-mqtt-client`, `tgu-rpc-sdk` (hyphen) — PyPI 패키지명과 일치, 일반적 관례 |
| **Python 모듈명** | `wss_mqtt_client`, `tgu_rpc` (underscore) — import 시 `from wss_mqtt_client import ...` |
| **공유 리소스** | `run_mock_server.py`, `docker-compose.yml` → SDK 루트 또는 wss-mqtt-client 쪽이 적합 (Mock은 wss-mqtt-api 프로토콜용) |
| **examples 배치** | wss-mqtt-client 예제(pub/sub) vs tgu-rpc 예제(rpc_call) 분리 권장. 공통 Mock 서버는 SDK/examples에 둠 |

### 1.3 주의사항

- tgu-rpc-sdk는 `wss-mqtt-client`에 의존하므로, `pip install tgu-rpc-sdk` 시 자동으로 wss-mqtt-client 설치됨
- 각 패키지가 독립 `pyproject.toml`을 가지면 **별도 PyPI 배포** 가능

---

## 2. wss_mqtt_client 구조 정리

### 2.1 현재 구조

```
wss_mqtt_client/
├── __init__.py
├── client.py           # WssMqttClientAsync
├── client_sync.py      # WssMqttClient
├── protocol.py
├── models.py
├── exceptions.py
├── constants.py
├── validation.py
└── transport/
    ├── __init__.py
    ├── base.py         # TransportInterface
    ├── wss_mqtt_api.py
    └── mqtt.py
```

### 2.2 정리 방향

| 옵션 | 설명 | 권장 |
|------|------|------|
| **A. flat 유지** | 현재 구조 유지. 이미 적절히 분리됨 | ✅ |
| **B. src layout** | `src/wss_mqtt_client/` — editable install 시 import 오류 방지, 현대적 관례 | ✅ 권장 |
| **C. 계층 추가** | `wss_mqtt_client/transports/` 등 — 현재 규모에선 과함 | ❌ |

### 2.3 src layout 적용 시

```
wss-mqtt-client/
├── pyproject.toml
├── src/
│   └── wss_mqtt_client/
│       └── (기존 파일들)
└── tests/
```

pyproject.toml:

```toml
[tool.setuptools.packages.find]
where = ["src"]
```

- **장점**: `pip install -e .` 시 프로젝트 루트가 아닌 src 내 패키지만 import path에 등록되어, 실수로 개발 중인 미반영 코드가 import되는 문제 방지

---

## 3. SDK 폴더 통합 설치 준비

### 3.1 방식 비교

| 방식 | 설명 | 장단점 |
|------|------|--------|
| **A. 각각 독립** | `pip install -e SDK/wss-mqtt-client`, `pip install -e SDK/tgu-rpc-sdk` | 단순. 통합 설치 불가 |
| **B. 메타 패키지** | `pip install -e SDK` → 두 패키지 모두 설치 | 편리. SDK/pyproject.toml에서 하위 패키지 의존 선언 |
| **C. uv/pip workspace** | `uv sync` 등 — workspace 기능 | 최신 도구. 설정 복잡 |

### 3.2 권장: B. 메타 패키지

SDK/pyproject.toml (선택):

```toml
[project]
name = "wss-mqtt-sdk"  # 또는 sdk-bundle
version = "0.1.0"
description = "WSS-MQTT 클라이언트 및 TGU RPC SDK 통합 번들"
dependencies = [
    "wss-mqtt-client",
    "tgu-rpc-sdk",
]
# 배포된 PyPI 패키지 기준. 로컬 개발 시에는 scripts로 각각 -e 설치
```

**개발용**: 각 패키지를 개별 editable 설치하는 편이 일반적:

```bash
pip install -e SDK/wss-mqtt-client
pip install -e SDK/tgu-rpc-sdk
```

**배포 시**: wss-mqtt-client, tgu-rpc-sdk를 각각 PyPI에 배포. tgu-rpc-sdk의 dependencies에 `wss-mqtt-client` 포함.

### 3.3 결론

- **로컬 개발**: `pip install -e SDK/wss-mqtt-client` 및 `pip install -e SDK/tgu-rpc-sdk` 개별 실행
- **통합 설치**: 선택 사항. `make install-sdk` 또는 `./scripts/install-all.sh` 같은 스크립트로 두 패키지 editable 설치
- **PyPI 배포**: wss-mqtt-client, tgu-rpc-sdk 각각 독립 배포

---

## 4. wss_mqtt_client → wss-mqtt-client 변경 검토

### 4.1 현재 명칭

| 구분 | 현재 | 비고 |
|------|------|------|
| **PyPI 패키지명** | wss-mqtt-client | 이미 hyphen |
| **Python 모듈명** | wss_mqtt_client | import 시 사용 |
| **폴더명** | wss_mqtt_client | SDK 내 패키지 루트 |

### 4.2 제안 정리

| 구분 | 제안 | 이유 |
|------|------|------|
| **패키지 폴더명** | `wss-mqtt-client` | PyPI명과 맞추고, SDK 내에서 패키지 식별 용이 |
| **Python 모듈 (import)** | `wss_mqtt_client` 유지 | Python은 hyphen을 식별자로 쓸 수 없음. 관례상 underscore |
| **소스 위치** | `wss-mqtt-client/src/wss_mqtt_client/` | 폴더=패키지명, 내부=모듈명 |

### 4.3 변경 불필요

- **import 경로** `from wss_mqtt_client import ...` 는 그대로 유지
- PyPI 패키지명 `wss-mqtt-client` 도 유지
- 변경하는 부분은 **SDK 내 폴더명** (`wss_mqtt_client` → `wss-mqtt-client`) 정도

---

## 5. transport 선택 + 패키지 이름 재설정 검토

### 5.1 현재 역할

- wss-mqtt-client: `transport="wss-mqtt-api"` (기본), `transport="mqtt"` 지원
- WSS-MQTT API 게이트웨이 경유 + 네이티브 MQTT 브로커 직접 연결 모두 지원

### 5.2 패키지 이름 후보

| 후보 | 의미 | 검토 |
|------|------|------|
| **wss-mqtt-client** (유지) | WSS-MQTT API 클라이언트 강조 | ✅ 역사·사양서와 일치. MQTT transport는 확장 |
| **mqtt-client** | 범용 MQTT 클라이언트 | ⚠️ paho-mqtt 등과 혼동, WSS-MQTT API 특성 희석 |
| **tgu-mqtt-client** | TGU용 MQTT 클라이언트 | ❌ TGU는 tgu-rpc-sdk 책임. transport 계층은 범용 |
| **mqtt-gateway-client** | 게이트웨이 경유 MQTT | ⚠️ "gateway"가 MQTT 직접 연결과 맞지 않음 |

### 5.3 권장: **wss-mqtt-client 유지**

이유:

1. **사양서·문서와의 일치**: `WSS-MQTT API` 사양과 네이밍이 맞음
2. **주 사용 시나리오**: wss-mqtt-api 게이트웨이 경유가 핵심, MQTT 직접 연결은 부가
3. **호환성**: 이미 사용 중인 이름 변경 시 마이그레이션 부담
4. **의미**: "WSS로 MQTT에 접근하는 클라이언트" — transport 종류와 무관하게 수용 가능

### 5.4 transport와 패키지의 관계

- transport는 **구현 세부사항**
- 패키지명은 **용도·역할**을 나타냄
- wss-mqtt-client = "WSS-MQTT API 사양을 따르는 클라이언트 (여러 transport 지원)" 로 해석 가능

---

## 6. 요약 및 권장안

| 항목 | 권장 |
|------|------|
| **1. 구조 분리** | SDK/wss-mqtt-client/, SDK/tgu-rpc-sdk/ 각각 독립 패키지 |
| **2. wss_mqtt_client 구조** | src layout 적용 (`src/wss_mqtt_client/`), flat 모듈 구조 유지 |
| **3. 통합 설치** | `scripts/install-all.sh` 또는 makefile로 두 패키지 editable 설치. PyPI는 각각 독립 배포 |
| **4. wss-mqtt-client 명칭** | 패키지 폴더명만 `wss-mqtt-client`로 통일. PyPI명·import 경로는 유지 |
| **5. 패키지 이름** | `wss-mqtt-client` 유지. transport 지원은 확장 기능으로 표현 |

---

## 7. 마이그레이션 체크리스트

- [x] `SDK/wss_mqtt_client/` → `SDK/wss-mqtt-client/wss_mqtt_client/` 이동 (flat layout)
- [x] `SDK/wss-mqtt-client/pyproject.toml` 생성 (flat layout, where = ["."])
- [x] `SDK/tgu-rpc-sdk/` 초기 구조 생성 (tgu_rpc 패키지)
- [x] `SDK/tgu-rpc-sdk/pyproject.toml` — dependency: wss-mqtt-client
- [x] examples 분배: pub/sub → wss-mqtt-client/examples, run_mock_server → SDK/examples
- [x] run_mock_server.py, docker-compose.yml 위치 결정 (SDK/examples, SDK/)
- [x] 테스트 경로 수정 (SDK/wss-mqtt-client/tests)
- [x] 문서 내 경로 업데이트
