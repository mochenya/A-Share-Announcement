from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def get_float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    # 配置值写错时直接失败，避免线上静默回退默认值后继续用错误的超时参数运行。
    return float(raw_value)


def get_optional_float_env(name: str) -> float | None:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return None
    return float(raw_value)


def get_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    # 和 float 配置保持同样策略：尽早暴露错误，比隐藏配置问题更容易排查。
    return int(raw_value)


def get_str_env(name: str, default: str) -> str:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    return raw_value.strip()
