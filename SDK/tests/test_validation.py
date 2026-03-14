"""
입력 검증 단위 테스트.
"""

import pytest

from wss_mqtt_client.validation import validate_topic


def test_validate_topic_ok() -> None:
    """정상 토픽은 통과."""
    validate_topic("test/topic")
    validate_topic("tgu/device_001/response")
    validate_topic("a" * 512)


def test_validate_topic_empty() -> None:
    """빈 문자열 거부."""
    with pytest.raises(ValueError, match="빈 문자열"):
        validate_topic("")
    with pytest.raises(ValueError, match="빈 문자열"):
        validate_topic("   ")


def test_validate_topic_wildcard_plus() -> None:
    """+ 와일드카드 거부."""
    with pytest.raises(ValueError, match="와일드카드"):
        validate_topic("sensor/+/temperature")


def test_validate_topic_wildcard_hash() -> None:
    """# 와일드카드 거부."""
    with pytest.raises(ValueError, match="와일드카드"):
        validate_topic("sensor/#")


def test_validate_topic_length_exceeded() -> None:
    """길이 초과 거부."""
    with pytest.raises(ValueError, match="길이 초과"):
        validate_topic("a" * 513)
    with pytest.raises(ValueError, match="513 > 512"):
        validate_topic("a" * 513)


def test_validate_topic_custom_max_len() -> None:
    """커스텀 max_len 적용."""
    validate_topic("a" * 100, max_len=100)
    with pytest.raises(ValueError):
        validate_topic("a" * 101, max_len=100)


def test_validate_topic_nul() -> None:
    """NUL 문자 거부."""
    with pytest.raises(ValueError, match="NUL"):
        validate_topic("topic\x00/suffix")


def test_validate_topic_not_str() -> None:
    """문자열이 아니면 거부."""
    with pytest.raises(ValueError, match="문자열"):
        validate_topic(123)  # type: ignore[arg-type]
