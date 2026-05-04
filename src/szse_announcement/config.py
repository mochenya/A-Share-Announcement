from __future__ import annotations

import httpx

from announcement_common.env import (
    get_float_env,
    get_int_env,
    get_optional_float_env,
    get_str_env,
)

BUILTIN_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)
DEFAULT_USER_AGENT = get_str_env("SZSE_USER_AGENT", BUILTIN_USER_AGENT)

_default_timeout = get_optional_float_env("SZSE_TIMEOUT")
DEFAULT_TIMEOUT = httpx.Timeout(
    connect=get_float_env(
        "SZSE_CONNECT_TIMEOUT",
        _default_timeout if _default_timeout is not None else 10.0,
    ),
    read=get_float_env(
        "SZSE_READ_TIMEOUT",
        _default_timeout if _default_timeout is not None else 30.0,
    ),
    write=get_float_env(
        "SZSE_WRITE_TIMEOUT",
        _default_timeout if _default_timeout is not None else 10.0,
    ),
    pool=get_float_env(
        "SZSE_POOL_TIMEOUT",
        _default_timeout if _default_timeout is not None else 10.0,
    ),
)
DEFAULT_LIMITS = httpx.Limits(
    max_connections=get_int_env("SZSE_MAX_CONNECTIONS", 10),
    max_keepalive_connections=get_int_env("SZSE_MAX_KEEPALIVE_CONNECTIONS", 5),
    keepalive_expiry=get_float_env("SZSE_KEEPALIVE_EXPIRY", 30.0),
)
DEFAULT_RETRIES = get_int_env("SZSE_RETRIES", 2)
