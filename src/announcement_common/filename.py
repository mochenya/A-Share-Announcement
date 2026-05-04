from __future__ import annotations

import re

INVALID_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
WHITESPACE_RE = re.compile(r"\s+")
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}
MAX_FILENAME_STEM_LENGTH = 80


def build_pdf_filename(
    *,
    announcement_id: str | None,
    announcement_title: str | None,
    fallback_stem: str | None,
) -> str:
    sanitized_id = sanitize_filename_part(announcement_id)
    sanitized_title = sanitize_filename_part(announcement_title)

    if sanitized_id and sanitized_title:
        stem = f"{sanitized_id} - {sanitized_title}"
    else:
        stem = sanitized_id or sanitized_title or sanitize_filename_part(fallback_stem)
    if not stem:
        stem = "announcement"

    # 公告标题经常很长，Windows 路径长度和 Telegram 文件名展示都不适合无限制
    # 保留；截断 stem 但固定保留 .pdf 后缀。
    stem = stem[:MAX_FILENAME_STEM_LENGTH].rstrip(" .") or "announcement"
    if stem.upper() in WINDOWS_RESERVED_NAMES:
        # Windows 保留名即使带扩展名也可能无法正常创建，追加下划线规避。
        stem = f"{stem}_"
    return f"{stem}.pdf"


def sanitize_filename_part(value: str | None) -> str | None:
    if value is None:
        return None
    # 上游标题可能含斜杠、冒号、换行等字符；统一替换为空格，既避免非法路径，
    # 也保留足够的人可读信息用于本地排查和 Telegram 文件展示。
    sanitized = INVALID_FILENAME_CHARS_RE.sub(" ", value).strip(" .")
    sanitized = WHITESPACE_RE.sub(" ", sanitized)
    return sanitized or None
