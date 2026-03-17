#!/usr/bin/env bash
# MaaS RPC Client SDK 설치 스크립트
#
# 사용법 (이 파일이 있는 python/ 디렉터리 안에서 실행):
#   bash install.sh              — 기본 설치
#   bash install.sh --msgpack    — msgpack 직렬화 포함
#   bash install.sh --dev        — 개발 의존성 포함 (pytest 등)
#   bash install.sh --msgpack --dev

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MSGPACK=0
DEV=0

for arg in "$@"; do
    case $arg in
        --msgpack) MSGPACK=1 ;;
        --dev)     DEV=1 ;;
    esac
done

echo "=== MaaS RPC Client SDK 설치 ==="

# 1. wss-mqtt-client (전송 인프라) — 의존 패키지이므로 먼저 설치
WSS_EXTRAS=""
[ "$MSGPACK" -eq 1 ] && WSS_EXTRAS="${WSS_EXTRAS},msgpack"
[ "$DEV"     -eq 1 ] && WSS_EXTRAS="${WSS_EXTRAS},dev"
WSS_EXTRAS="${WSS_EXTRAS#,}"  # 앞쪽 쉼표 제거

if [ -n "$WSS_EXTRAS" ]; then
    pip install -e "${SCRIPT_DIR}/wss-mqtt-client[${WSS_EXTRAS}]"
else
    pip install -e "${SCRIPT_DIR}/wss-mqtt-client"
fi

# 2. maas-rpc-client-sdk (RPC 클라이언트)
if [ "$DEV" -eq 1 ]; then
    pip install -e "${SCRIPT_DIR}/maas-rpc-client-sdk[dev]"
else
    pip install -e "${SCRIPT_DIR}/maas-rpc-client-sdk"
fi

echo ""
echo "설치 완료."
echo "  from maas_rpc_client import RpcClient  으로 사용하세요."
