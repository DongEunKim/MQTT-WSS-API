"""
RPC 토픽 패턴 생성 유틸.

WMT/WMO 토픽 규격에 따른 요청/응답 토픽 문자열을 생성한다.
참조: docs/TOPIC_AND_ACL_SPEC.md, docs/RPC_DESIGN.md
"""


def _validate_segment(name: str, value: str) -> None:
    """세그먼트 검증: 빈 문자열, / 포함 불가."""
    if not value or not value.strip():
        raise ValueError(f"{name}는 빈 문자열일 수 없습니다")
    if "/" in value:
        raise ValueError(f"{name}에 '/'를 포함할 수 없습니다")


def build_request_topic(service: str, vehicle_id: str) -> str:
    """
    RPC 요청 토픽 생성.

    Args:
        service: 서비스 식별자 (예: RemoteUDS, VISS)
        vehicle_id: 차량 식별자

    Returns:
        WMT/{service}/{vehicle_id}/request 형식의 토픽 문자열

    Raises:
        ValueError: service 또는 vehicle_id가 유효하지 않은 경우
    """
    _validate_segment("service", service)
    _validate_segment("vehicle_id", vehicle_id)
    return f"WMT/{service}/{vehicle_id}/request"


def build_response_topic(service: str, vehicle_id: str, client_id: str) -> str:
    """
    RPC 응답 토픽 생성.

    Args:
        service: 서비스 식별자
        vehicle_id: 차량 식별자
        client_id: 클라이언트 식별자 (응답 수신용)

    Returns:
        WMO/{service}/{vehicle_id}/{client_id}/response 형식의 토픽 문자열

    Raises:
        ValueError: 인자가 유효하지 않은 경우
    """
    _validate_segment("service", service)
    _validate_segment("vehicle_id", vehicle_id)
    _validate_segment("client_id", client_id)
    return f"WMO/{service}/{vehicle_id}/{client_id}/response"


def build_stream_topic(
    service: str, vehicle_id: str, client_id: str, api: str
) -> str:
    """
    스트림 수신 토픽 생성 (subscribe_stream용).

    Args:
        service: 서비스 식별자 (예: RemoteDashboard)
        vehicle_id: 차량 식별자
        client_id: 클라이언트 식별자
        api: 스트림 API 식별자 (예: vehicleSpeed, rpm)

    Returns:
        WMO/{service}/{vehicle_id}/{client_id}/stream/{api} 형식

    Raises:
        ValueError: 인자가 유효하지 않은 경우
    """
    _validate_segment("service", service)
    _validate_segment("vehicle_id", vehicle_id)
    _validate_segment("client_id", client_id)
    _validate_segment("api", api)
    return f"WMO/{service}/{vehicle_id}/{client_id}/stream/{api}"
