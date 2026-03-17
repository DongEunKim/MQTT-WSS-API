"""
RPC 토픽 패턴 생성 유틸.

WMT/WMO 토픽 규격에 따른 요청/응답 토픽 문자열을 생성한다.
참조: docs/TOPIC_AND_ACL_SPEC.md, docs/RPC_DESIGN.md

토픽 패턴:
  요청: WMT/{service}/{thing_name}/{oem}/{asset}/request
  응답: WMO/{service}/{thing_name}/{oem}/{asset}/{client_id}/response
"""


def _validate_segment(name: str, value: str) -> None:
    """세그먼트 검증: 빈 문자열, / 포함 불가."""
    if not value or not value.strip():
        raise ValueError(f"{name}는 빈 문자열일 수 없습니다")
    if "/" in value:
        raise ValueError(f"{name}에 '/'를 포함할 수 없습니다")


def build_request_topic(
    service: str,
    thing_name: str,
    oem: str,
    asset: str,
) -> str:
    """
    RPC 요청 토픽 생성.

    Args:
        service: 엣지 서버가 제공하는 서비스 식별자 (예: RemoteUDS, VISS)
        thing_name: 엣지 서버의 IoT Thing 이름
        oem: 엣지 서버의 소속 조직/제조사
        asset: 장비 식별자 (VIN, 시리얼 번호 등)

    Returns:
        WMT/{service}/{thing_name}/{oem}/{asset}/request 형식의 토픽 문자열

    Raises:
        ValueError: 인자가 유효하지 않은 경우
    """
    _validate_segment("service", service)
    _validate_segment("thing_name", thing_name)
    _validate_segment("oem", oem)
    _validate_segment("asset", asset)
    return f"WMT/{service}/{thing_name}/{oem}/{asset}/request"


def build_response_topic(
    service: str,
    thing_name: str,
    oem: str,
    asset: str,
    client_id: str,
) -> str:
    """
    RPC 응답 토픽 생성.

    Args:
        service: 엣지 서버가 제공하는 서비스 식별자
        thing_name: 엣지 서버의 IoT Thing 이름
        oem: 엣지 서버의 소속 조직/제조사
        asset: 장비 식별자
        client_id: 클라이언트 식별자 (응답 수신용)

    Returns:
        WMO/{service}/{thing_name}/{oem}/{asset}/{client_id}/response 형식의 토픽 문자열

    Raises:
        ValueError: 인자가 유효하지 않은 경우
    """
    _validate_segment("service", service)
    _validate_segment("thing_name", thing_name)
    _validate_segment("oem", oem)
    _validate_segment("asset", asset)
    _validate_segment("client_id", client_id)
    return f"WMO/{service}/{thing_name}/{oem}/{asset}/{client_id}/response"
