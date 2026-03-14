"""
입력 검증 유틸리티.

토픽 형식 등 클라이언트 진입점 검증을 담당한다.
"""


def validate_topic(topic: str, *, max_len: int = 512) -> None:
    """
    토픽 형식 검증.

    MQTT 토픽 이름 규격 및 API 사양에 따른 검증을 수행한다.

    Args:
        topic: 검증할 토픽 문자열
        max_len: 최대 허용 길이 (기본 512)

    Raises:
        ValueError: 검증 실패 시
    """
    if not isinstance(topic, str):
        raise ValueError("토픽은 문자열이어야 합니다")
    if not topic or not topic.strip():
        raise ValueError("토픽은 빈 문자열일 수 없습니다")
    if len(topic) > max_len:
        raise ValueError(f"토픽 길이 초과: {len(topic)} > {max_len}")
    if "+" in topic or "#" in topic:
        raise ValueError("토픽 이름에 와일드카드(+, #) 사용 불가")
    if "\x00" in topic:
        raise ValueError("토픽에 NUL 문자 포함 불가")
