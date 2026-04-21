"""
maas-server-sdk: MQTT 5.0 기반 MaaS RPC 서비스 서버 SDK.

Example::

    from maas_server import MaasServer, RpcContext

    server = MaasServer(
        thing_type="CGU",
        service_name="viss",
        vin="VIN-123456",
        endpoint="xxxx.iot.amazonaws.com",
    )

    @server.action("get")
    def get_data(ctx: RpcContext):
        return {"value": 42}

    server.run()
"""

from .server import MaasServer
from .context import RpcContext
from .exceptions import (
    MaasServerError,
    ConnectionError,
    SessionBusyError,
    HandlerError,
    HardwareFaultError,
    NotAuthorizedError,
    PayloadError,
)
from . import topics

__all__ = [
    "MaasServer",
    "RpcContext",
    "MaasServerError",
    "ConnectionError",
    "SessionBusyError",
    "HandlerError",
    "HardwareFaultError",
    "NotAuthorizedError",
    "PayloadError",
    "topics",
]

__version__ = "1.0.0"
