"""
TGU RPC SDK 예외 정의.
"""

from typing import Any, Optional


class TguRpcError(Exception):
    """TGU RPC SDK 기본 예외."""

    pass


class RpcError(TguRpcError):
    """
    TGU 응답에 error 필드가 있을 때 발생.

    Attributes:
        code: 에러 코드 (문자열)
        message: 에러 메시지
        raw: 원본 error 객체
    """

    def __init__(
        self,
        error: Any,
        message: Optional[str] = None,
    ) -> None:
        self.raw = error
        if isinstance(error, dict):
            self.code = error.get("code", "")
            self.message = error.get("message", str(error))
        else:
            self.code = ""
            self.message = str(error)
        if message is None:
            message = f"RPC error: code={self.code}, message={self.message}"
        super().__init__(message)


class RpcTimeoutError(TguRpcError):
    """RPC call 타임아웃 시 발생."""

    def __init__(self, service: str, request_id: str, timeout: float) -> None:
        self.service = service
        self.request_id = request_id
        self.timeout = timeout
        super().__init__(
            f"RPC timeout: service={service}, request_id={request_id} (timeout={timeout}s)"
        )
