"""
maas-client-sdk: MQTT 5.0 기반 MaaS RPC 클라이언트 SDK.

기본 인터페이스(동기):
    from maas_client import MaasClient

고급 인터페이스(비동기):
    from maas_client import MaasClientAsync
"""

from .auth import HttpTokenSource, TokenSource, TokenProvider
from .client import MaasClient
from .client_async import MaasClientAsync
from .models import RpcResponse, StreamEvent, Message
from .exceptions import (
    MaasError,
    ConnectionError,
    RpcTimeoutError,
    RpcServerError,
    NotAuthorizedError,
    ServerBusyError,
    StreamInterruptedError,
)
from . import topics

__all__ = [
    "HttpTokenSource",
    "TokenSource",
    "TokenProvider",
    "MaasClient",
    "MaasClientAsync",
    "RpcResponse",
    "StreamEvent",
    "Message",
    "MaasError",
    "ConnectionError",
    "RpcTimeoutError",
    "RpcServerError",
    "NotAuthorizedError",
    "ServerBusyError",
    "StreamInterruptedError",
    "topics",
]

__version__ = "1.0.0"
