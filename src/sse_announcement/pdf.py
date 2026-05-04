from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urljoin

if __package__ in (None, ""):
    # 允许 `uv run path/to/pdf.py` 这类包内文件直跑烟测找到 sibling package。
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from announcement_common.filename import build_pdf_filename
from announcement_common.pdf import is_existing_pdf, write_pdf_atomic
from sse_announcement.config import DEFAULT_RETRIES
from sse_announcement.models import (
    BusinessAnnouncement,
    SSEBulletinFile,
    build_announcement_id,
)

PDF_BASE_URL = "https://static.sse.com.cn/"

AnnouncementWithPdf = BusinessAnnouncement | SSEBulletinFile


def build_pdf_url(announcement: AnnouncementWithPdf) -> str:
    return _build_pdf_url_from_adjunct_url(_get_adjunct_url(announcement))


def download_pdf(
    announcement: AnnouncementWithPdf,
    *,
    save_dir: str | Path | None = None,
) -> Path:
    from sse_announcement.client import SSEAnnouncementClient

    with SSEAnnouncementClient() as client:
        return client.download_pdf(announcement, save_dir=save_dir)


def _download_pdf_with_client(
    client: httpx.Client,
    announcement: AnnouncementWithPdf,
    *,
    save_dir: str | Path | None = None,
    retries: int = DEFAULT_RETRIES,
) -> Path:
    from sse_announcement.client import _get_pdf_response

    target_dir = _resolve_save_dir(save_dir)
    target_path = target_dir / _derive_pdf_filename(announcement)
    if target_path.is_file():
        if is_existing_pdf(target_path):
            # workflow 重试时会反复进入下载阶段；本地已有 PDF 就直接复用，避免重复
            # 触发上交所 static 域名的 challenge 和限流。
            return target_path
        # 旧版本可能把挑战页或 HTML 错误页保存成 .pdf；损坏文件不应继续复用。
        target_path.unlink()

    response = _get_pdf_response(client, build_pdf_url(announcement), retries=retries)
    write_pdf_atomic(target_path, response.content)
    return target_path


def _resolve_save_dir(save_dir: str | Path | None) -> Path:
    if save_dir is None:
        return _default_pdf_dir()
    return Path(save_dir)


def _default_pdf_dir() -> Path:
    # 默认目录只服务库的单独使用场景；业务 workflow 建议显式传 save_dir，避免安装
    # 到 site-packages 后把 PDF 写进虚拟环境目录。
    return Path(__file__).resolve().parents[2] / "data" / "sse_pdf"


def _build_pdf_url_from_adjunct_url(adjunct_url: str) -> str:
    # SSE 返回的是相对路径；用 urljoin 处理前导斜杠，避免手拼 URL 时出现双斜杠
    # 或漏斜杠。
    return urljoin(PDF_BASE_URL, adjunct_url.lstrip("/"))


def _derive_pdf_filename(announcement: AnnouncementWithPdf) -> str:
    return build_pdf_filename(
        announcement_id=_get_announcement_id(announcement),
        announcement_title=_get_announcement_title(announcement),
        fallback_stem=Path(_get_adjunct_url(announcement)).stem,
    )


def _get_adjunct_url(announcement: AnnouncementWithPdf) -> str:
    if isinstance(announcement, BusinessAnnouncement):
        adjunct_url = announcement.adjunct_url
    else:
        adjunct_url = announcement.URL
    normalized = (adjunct_url or "").strip()
    if not normalized:
        raise ValueError("announcement adjunctUrl is required")
    return normalized


def _get_announcement_id(announcement: AnnouncementWithPdf) -> str | None:
    if isinstance(announcement, BusinessAnnouncement):
        return announcement.announcement_id
    return build_announcement_id(announcement)


def _get_announcement_title(announcement: AnnouncementWithPdf) -> str | None:
    if isinstance(announcement, BusinessAnnouncement):
        return announcement.announcement_title
    return announcement.TITLE


if __name__ == "__main__":
    from sse_announcement.client import query_announcements

    today = date.today()
    start = today - timedelta(days=7)
    result = query_announcements(
        searchkey="股权激励",
        start_date=start,
        end_date=today,
        limit=1,
    )
    if not result.items:
        raise SystemExit("No SSE announcements found")

    announcement = result.items[0]
    path = download_pdf(announcement)
    print(path)
