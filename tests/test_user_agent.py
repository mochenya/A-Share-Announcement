from __future__ import annotations

import os
import subprocess
import sys

from cninfo_announcement.client import (
    DEFAULT_HEADERS as CNINFO_DEFAULT_HEADERS,
)
from cninfo_announcement.client import CNInfoClient
from cninfo_announcement.config import DEFAULT_USER_AGENT as CNINFO_DEFAULT_USER_AGENT
from sse_announcement.client import (
    DEFAULT_HEADERS as SSE_DEFAULT_HEADERS,
)
from sse_announcement.client import SSEAnnouncementClient, _build_pdf_headers
from sse_announcement.config import DEFAULT_USER_AGENT as SSE_DEFAULT_USER_AGENT
from szse_announcement.client import (
    DEFAULT_HEADERS as SZSE_DEFAULT_HEADERS,
)
from szse_announcement.client import SZSEAnnouncementClient
from szse_announcement.client import _build_pdf_headers as build_szse_pdf_headers
from szse_announcement.config import DEFAULT_USER_AGENT as SZSE_DEFAULT_USER_AGENT


def test_cninfo_user_agent_parameter_overrides_default() -> None:
    client = CNInfoClient(verify=False, user_agent="CustomCNInfo/1.0")
    try:
        assert client.user_agent == "CustomCNInfo/1.0"
        assert client._client.headers["User-Agent"] == "CustomCNInfo/1.0"
        assert CNINFO_DEFAULT_HEADERS["User-Agent"] == CNINFO_DEFAULT_USER_AGENT
    finally:
        client.close()


def test_cninfo_blank_user_agent_parameter_falls_back_to_default() -> None:
    client = CNInfoClient(verify=False, user_agent="   ")
    try:
        assert client.user_agent == CNINFO_DEFAULT_USER_AGENT
        assert client._client.headers["User-Agent"] == CNINFO_DEFAULT_USER_AGENT
    finally:
        client.close()


def test_sse_user_agent_parameter_applies_to_query_and_pdf_headers() -> None:
    client = SSEAnnouncementClient(verify=False, user_agent="CustomSSE/1.0")
    try:
        assert client.user_agent == "CustomSSE/1.0"
        assert client._client.headers["User-Agent"] == "CustomSSE/1.0"
        assert _build_pdf_headers(client._client)["User-Agent"] == "CustomSSE/1.0"
        assert SSE_DEFAULT_HEADERS["User-Agent"] == SSE_DEFAULT_USER_AGENT
    finally:
        client.close()


def test_szse_user_agent_parameter_applies_to_query_and_pdf_headers() -> None:
    client = SZSEAnnouncementClient(verify=False, user_agent="CustomSZSE/1.0")
    try:
        assert client.user_agent == "CustomSZSE/1.0"
        assert client._client.headers["User-Agent"] == "CustomSZSE/1.0"
        assert build_szse_pdf_headers(client._client)["User-Agent"] == "CustomSZSE/1.0"
        assert SZSE_DEFAULT_HEADERS["User-Agent"] == SZSE_DEFAULT_USER_AGENT
    finally:
        client.close()


def test_user_agent_env_overrides_defaults_on_import() -> None:
    env = os.environ.copy()
    env["CNINFO_USER_AGENT"] = "EnvCNInfo/1.0"
    env["SSE_USER_AGENT"] = "EnvSSE/1.0"
    env["SZSE_USER_AGENT"] = "EnvSZSE/1.0"
    code = """
from cninfo_announcement.client import CNInfoClient
from sse_announcement.client import SSEAnnouncementClient, _build_pdf_headers
from szse_announcement.client import SZSEAnnouncementClient, _build_pdf_headers as build_szse_pdf_headers

cninfo = CNInfoClient(verify=False)
sse = SSEAnnouncementClient(verify=False)
szse = SZSEAnnouncementClient(verify=False)
try:
    print(cninfo._client.headers["User-Agent"])
    print(sse._client.headers["User-Agent"])
    print(_build_pdf_headers(sse._client)["User-Agent"])
    print(szse._client.headers["User-Agent"])
    print(build_szse_pdf_headers(szse._client)["User-Agent"])
finally:
    cninfo.close()
    sse.close()
    szse.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.stdout.splitlines() == [
        "EnvCNInfo/1.0",
        "EnvSSE/1.0",
        "EnvSSE/1.0",
        "EnvSZSE/1.0",
        "EnvSZSE/1.0",
    ]
