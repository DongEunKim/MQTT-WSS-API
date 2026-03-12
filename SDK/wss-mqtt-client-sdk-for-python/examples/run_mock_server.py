#!/usr/bin/env python3
"""
Mock WSS-MQTT API 서버 직접 실행.

Usage:
    python examples/run_mock_server.py [--port 8765]
    python examples/run_mock_server.py --port 9000

옵션:
    --port PORT  : 포트 번호 (기본 8765)
    --no-simulate: TGU 시뮬레이션 비활성화 (기본: PUBLISH → /response 토픽으로 자동 릴레이)

실행 후, 다른 터미널에서:
    python examples/subscriber.py   # 구독 클라이언트
    python examples/publisher.py   # 발행 클라이언트
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가
_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from tests.mock_server import MockWssMqttServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Mock WSS-MQTT API 서버")
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="리스닝 포트 (기본: 8765)",
    )
    parser.add_argument(
        "--no-simulate",
        action="store_true",
        help="TGU 시뮬레이션 비활성화 (PUBLISH → /response 릴레이 끔)",
    )
    args = parser.parse_args()

    url = f"ws://localhost:{args.port}"
    logger.info("Mock 서버 시작: %s", url)
    logger.info(
        "연결 후 발행/구독 예제: python SDK/.../examples/publisher.py / subscriber.py"
    )
    if not args.no_simulate:
        logger.info(
            "TGU 시뮬레이션: PUBLISH → X/command → SUBSCRIPTION → X/response"
        )

    async def run() -> None:
        server = MockWssMqttServer(
            host="0.0.0.0",
            port=args.port,
            simulate_tgu=not args.no_simulate,
        )
        await server.start()
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        finally:
            await server.stop()

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("서버 종료")


if __name__ == "__main__":
    main()
