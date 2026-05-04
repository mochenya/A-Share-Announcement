from __future__ import annotations

from announcement_common.http import (
    parse_retry_after_seconds,
    retry_delay_seconds,
    should_retry_status,
)


def test_retry_delay_respects_numeric_retry_after() -> None:
    assert retry_delay_seconds(0, "2") == 2.0


def test_retry_delay_falls_back_to_exponential_backoff() -> None:
    assert retry_delay_seconds(0) == 0.5
    assert retry_delay_seconds(10, "not-a-date") == 4.0


def test_parse_retry_after_clamps_negative_delay() -> None:
    assert parse_retry_after_seconds("-1") == 0.0


def test_parse_retry_after_clamps_large_delay() -> None:
    assert parse_retry_after_seconds("120") == 60.0


def test_should_retry_status_includes_rate_limit_and_server_errors() -> None:
    assert should_retry_status(429) is True
    assert should_retry_status(500) is True
    assert should_retry_status(404) is False
