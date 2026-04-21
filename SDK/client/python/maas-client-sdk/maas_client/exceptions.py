"""
maas-client-sdk 예외 정의.
"""


class MaasError(Exception):
    """maas-client-sdk 기본 예외."""


class ConnectionError(MaasError):
    """MQTT 연결 실패 또는 연결 끊김."""


class RpcTimeoutError(MaasError):
    """RPC 응답 타임아웃."""

    def __init__(self, service: str, action: str, timeout: float) -> None:
        super().__init__(
            f"RPC 타임아웃: service={service}, action={action}, timeout={timeout}s"
        )
        self.service = service
        self.action = action
        self.timeout = timeout


class RpcServerError(MaasError):
    """서버가 오류 reason_code를 반환한 경우."""

    def __init__(self, reason_code: int, error_detail: str = "") -> None:
        super().__init__(
            f"서버 오류: reason_code={reason_code:#04x}, detail={error_detail}"
        )
        self.reason_code = reason_code
        self.error_detail = error_detail


class NotAuthorizedError(RpcServerError):
    """권한 없음 (reason_code=0x87)."""

    def __init__(self, error_detail: str = "") -> None:
        super().__init__(0x87, error_detail)


class ServerBusyError(RpcServerError):
    """독점 세션 점유 중 (reason_code=0x8A)."""

    def __init__(self, error_detail: str = "") -> None:
        super().__init__(0x8A, error_detail)


class StreamInterruptedError(MaasError):
    """스트리밍 중 연결 끊김 또는 서버 중단."""


class PayloadError(MaasError):
    """페이로드 직렬화/역직렬화 오류."""
