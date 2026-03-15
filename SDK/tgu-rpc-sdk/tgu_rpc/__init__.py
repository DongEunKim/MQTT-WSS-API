"""
TGU RPC SDK.

TGU(Telematics Gateway Unit) 서비스/API 명세 기반 RPC 클라이언트.
wss-mqtt-client 위에 구축됨.

기본: TguRpcClient (동기). 고급: TguRpcClientAsync (비동기).
"""

from .client import TguRpcClient
from .client_async import TguRpcClientAsync
from .exceptions import RpcError, RpcTimeoutError, TguRpcError
from .topics import (
    build_request_topic,
    build_response_topic,
    build_stream_topic,
)

__all__ = [
    "TguRpcClient",
    "TguRpcClientAsync",
    "build_request_topic",
    "build_response_topic",
    "build_stream_topic",
    "TguRpcError",
    "RpcError",
    "RpcTimeoutError",
]
