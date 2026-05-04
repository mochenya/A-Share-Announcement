from __future__ import annotations

import httpx

from announcement_common.env import get_float_env, get_int_env, get_str_env

BUILTIN_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)
DEFAULT_USER_AGENT = get_str_env("CNINFO_USER_AGENT", BUILTIN_USER_AGENT)

_default_timeout = get_float_env("CNINFO_TIMEOUT", 10.0)
DEFAULT_TIMEOUT = httpx.Timeout(
    connect=get_float_env("CNINFO_CONNECT_TIMEOUT", _default_timeout),
    read=get_float_env("CNINFO_READ_TIMEOUT", _default_timeout),
    write=get_float_env("CNINFO_WRITE_TIMEOUT", _default_timeout),
    pool=get_float_env("CNINFO_POOL_TIMEOUT", _default_timeout),
)
DEFAULT_LIMITS = httpx.Limits(
    max_connections=get_int_env("CNINFO_MAX_CONNECTIONS", 100),
    max_keepalive_connections=get_int_env("CNINFO_MAX_KEEPALIVE_CONNECTIONS", 20),
    keepalive_expiry=get_float_env("CNINFO_KEEPALIVE_EXPIRY", 5.0),
)
DEFAULT_RETRIES = get_int_env("CNINFO_RETRIES", 2)
