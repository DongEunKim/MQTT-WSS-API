#!/usr/bin/env python3
"""
RPC 연속 호출 — 벤치마크/지연 분석용.
연결 재사용 vs 매 호출마다 새 연결 비교.

Usage:
    # 연결 재사용 (권장 — 지연 패턴 확인)
    python SDK/client/python/maas-rpc-client-sdk/examples/rpc_call_mqtt_continuous.py --count 20

    # 매 호출마다 새 연결 (rpc_call_mqtt 연속 실행과 동일)
    python SDK/client/python/maas-rpc-client-sdk/examples/rpc_call_mqtt_continuous.py --count 20 --reconnect

환경변수:
    MQTT_URL   : MQTT 브로커 URL (기본: mqtt://localhost:1883)
    MQTT_TOKEN : JWT 토큰 (선택)
"""

import argparse
import os
import time

from maas_rpc_client import RpcClient

URL = os.environ.get("MQTT_URL", "mqtt://localhost:1883")
TOKEN = os.environ.get("MQTT_TOKEN", "")


def run_single_call(
    client: RpcClient,
    index: int,
    verbose: bool,
) -> float:
    """단일 RPC 호출 후 소요 시간(초) 반환."""
    t0 = time.perf_counter()
    try:
        result = client.call(
            "RemoteUDS",
            {"action": "readDTC", "params": {"source": 1}},
        )
        elapsed = time.perf_counter() - t0
        if verbose:
            print(f"  [{index+1}] {elapsed*1000:.0f}ms  result={result}")
        return elapsed
    except Exception as e:
        elapsed = time.perf_counter() - t0
        print(f"  [{index+1}] {elapsed*1000:.0f}ms  ERROR: {e}")
        raise


def main_reuse_connection(count: int, verbose: bool) -> None:
    """연결 재사용 — 단일 클라이언트로 N회 호출."""
    print(f"연결 재사용 모드: {count}회 호출")
    t_connect = time.perf_counter()
    with RpcClient(
        url=URL,
        token=TOKEN or None,
        vehicle_id="v001",
        transport="mqtt",
    ) as client:
        t_connect_elapsed = time.perf_counter() - t_connect
        print(f"연결: {t_connect_elapsed*1000:.0f}ms\n호출:")

        times: list[float] = []
        for i in range(count):
            elapsed = run_single_call(client, i, verbose)
            times.append(elapsed)

    _print_summary(times, t_connect_elapsed)


def main_reconnect_each(count: int, verbose: bool) -> None:
    """매 호출마다 새 연결 — rpc_call_mqtt 연속 실행과 동일."""
    print(f"매 연결 모드: {count}회 호출 (각 호출마다 connect/disconnect)")

    times: list[float] = []
    for i in range(count):
        t0 = time.perf_counter()
        with RpcClient(
            url=URL,
            token=TOKEN or None,
            vehicle_id="v001",
            transport="mqtt",
        ) as client:
            try:
                result = client.call(
                    "RemoteUDS",
                    {"action": "readDTC", "params": {"source": 1}},
                )
                elapsed = time.perf_counter() - t0
                times.append(elapsed)
                if verbose:
                    print(f"  [{i+1}] {elapsed*1000:.0f}ms  result={result}")
            except Exception as e:
                elapsed = time.perf_counter() - t0
                print(f"  [{i+1}] {elapsed*1000:.0f}ms  ERROR: {e}")
                raise

    _print_summary(times, connect_time=0.0)


def _print_summary(
    times: list[float],
    connect_time: float = 0.0,
) -> None:
    """호출별 소요 시간 요약 출력."""
    if not times:
        return
    total = sum(times)
    avg = total / len(times)
    min_t = min(times)
    max_t = max(times)
    slow = [i for i, t in enumerate(times) if t > 1.0]  # 1초 초과
    print(f"\n--- 요약 ---")
    if connect_time > 0:
        print(f"연결: {connect_time*1000:.0f}ms")
    print(f"호출: {len(times)}회, 총 {total*1000:.0f}ms, 평균 {avg*1000:.0f}ms")
    print(f"최소 {min_t*1000:.0f}ms, 최대 {max_t*1000:.0f}ms")
    if slow:
        print(f"1초 초과 호출: {[s+1 for s in slow]} (지연 의심)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RPC 연속 호출 — 구조적 지연 분석"
    )
    parser.add_argument(
        "-n",
        "--count",
        type=int,
        default=10,
        help="호출 횟수 (기본: 10)",
    )
    parser.add_argument(
        "-r",
        "--reconnect",
        action="store_true",
        help="매 호출마다 새 연결 (연결 재사용 비활성화)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="호출별 상세 출력",
    )
    args = parser.parse_args()

    if args.reconnect:
        main_reconnect_each(args.count, args.verbose)
    else:
        main_reuse_connection(args.count, args.verbose)


if __name__ == "__main__":
    main()
