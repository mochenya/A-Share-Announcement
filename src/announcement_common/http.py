from __future__ import annotations

import ssl
from collections.abc import Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from ssl import SSLContext
from typing import Any

import httpx
import truststore

VerifyTypes = bool | str | SSLContext
RETRY_BASE_DELAY_SECONDS = 0.5
RETRY_MAX_DELAY_SECONDS = 4.0
RETRY_AFTER_MAX_DELAY_SECONDS = 60.0


def default_verify_context() -> SSLContext:
    # Windows/公司代理环境里系统证书可能已受信，但 certifi 不认识；默认跟随系统证书。
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def retry_delay_seconds(attempt: int, retry_after: str | None = None) -> float:
    retry_after_delay = parse_retry_after_seconds(retry_after)
    if retry_after_delay is not None:
        return retry_after_delay
    return min(RETRY_BASE_DELAY_SECONDS * (2**attempt), RETRY_MAX_DELAY_SECONDS)


def parse_retry_after_seconds(value: str | None) -> float | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    try:
        delay = float(normalized)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(normalized)
        except TypeError, ValueError:
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        delay = (retry_at - datetime.now(UTC)).total_seconds()
    # Retry-After 是上游明确要求的冷却时间；做上限保护，避免单次请求意外挂住过久。
    return min(max(delay, 0.0), RETRY_AFTER_MAX_DELAY_SECONDS)


def should_retry_status(status_code: int) -> bool:
    return status_code == 429 or status_code >= 500


def normalize_user_agent(value: str | None, default: str) -> str:
    return (value or default).strip() or default


def normalize_timeout(
    timeout: float | httpx.Timeout | None,
    default: httpx.Timeout,
) -> httpx.Timeout:
    if timeout is None:
        return default
    if isinstance(timeout, int | float):
        return httpx.Timeout(timeout)
    return timeout


def build_headers_with_user_agent(
    default_headers: Mapping[str, str],
    *,
    user_agent: str | None,
    default_user_agent: str,
) -> dict[str, str]:
    headers = dict(default_headers)
    headers["User-Agent"] = normalize_user_agent(user_agent, default_user_agent)
    return headers


def create_http_client(
    *,
    timeout: float | httpx.Timeout | None,
    default_timeout: httpx.Timeout,
    limits: httpx.Limits | None,
    default_limits: httpx.Limits,
    verify: VerifyTypes | None,
    default_headers: Mapping[str, str],
    user_agent: str | None,
    default_user_agent: str,
    **client_options: Any,
) -> tuple[httpx.Client, httpx.Timeout, httpx.Limits, str]:
    normalized_timeout = normalize_timeout(timeout, default_timeout)
    normalized_limits = limits or default_limits
    normalized_user_agent = normalize_user_agent(user_agent, default_user_agent)
    if verify is None:
        verify = default_verify_context()

    client = httpx.Client(
        timeout=normalized_timeout,
        limits=normalized_limits,
        headers=build_headers_with_user_agent(
            default_headers,
            user_agent=normalized_user_agent,
            default_user_agent=default_user_agent,
        ),
        verify=verify,
        **client_options,
    )
    return client, normalized_timeout, normalized_limits, normalized_user_agent
