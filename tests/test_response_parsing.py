from __future__ import annotations

import httpx
import pytest

from sse_announcement.client import (
    SSERateLimitError,
    SSEUnexpectedResponseError,
    _decode_query_json as decode_sse_query_json,
)
from szse_announcement.client import (
    SZSEUnexpectedResponseError,
    _decode_query_json as decode_szse_query_json,
)


def test_sse_decode_query_json_returns_normal_json() -> None:
    response = httpx.Response(200, json={"ok": True})

    assert decode_sse_query_json(response) == {"ok": True}


def test_sse_decode_query_json_rejects_wrapped_error_response() -> None:
    response = httpx.Response(200, text='({"error":"rate limited"})')

    with pytest.raises(SSERateLimitError, match="rate limited"):
        decode_sse_query_json(response)


def test_sse_decode_query_json_rejects_wrapped_error_type_response() -> None:
    response = httpx.Response(200, text='({"errorType":"challenge"})')

    with pytest.raises(SSERateLimitError, match="challenge"):
        decode_sse_query_json(response)


def test_sse_decode_query_json_rejects_wrapped_non_json_response() -> None:
    response = httpx.Response(200, text="(not-json)")

    with pytest.raises(SSEUnexpectedResponseError, match="wrapped non-JSON data"):
        decode_sse_query_json(response)


def test_sse_decode_query_json_rejects_plain_non_json_response() -> None:
    response = httpx.Response(200, text="<html>challenge</html>")

    with pytest.raises(SSEUnexpectedResponseError, match="non-JSON data"):
        decode_sse_query_json(response)


def test_szse_decode_query_json_returns_normal_json() -> None:
    response = httpx.Response(200, json={"ok": True})

    assert decode_szse_query_json(response) == {"ok": True}


def test_szse_decode_query_json_rejects_plain_non_json_response() -> None:
    response = httpx.Response(200, text="<html>challenge</html>")

    with pytest.raises(SZSEUnexpectedResponseError, match="non-JSON data"):
        decode_szse_query_json(response)
