from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urljoin

if __package__ in (None, ""):
    # 允许 `uv run path/to/pdf.py` 这类包内文件直跑烟测找到 sibling package。
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from announcement_common.filename import build_pdf_filename
from cninfo_announcement.models import AnnouncementRecord, BusinessAnnouncement

PDF_BASE_URL = "https://static.cninfo.com.cn/"
TAG_RE = re.compile(r"</?em>")

AnnouncementWithPdf = BusinessAnnouncement | AnnouncementRecord


def build_pdf_url(announcement: AnnouncementWithPdf) -> str:
    return _build_pdf_url_from_adjunct_url(_get_adjunct_url(announcement))


def download_pdf(
    announcement: AnnouncementWithPdf,
    *,
    save_dir: str | Path | None = None,
) -> Path:
    from cninfo_announcement.client import CNInfoClient

    with CNInfoClient() as client:
        return client.download_pdf(announcement, save_dir=save_dir)


def _download_pdf_with_client(
    client: httpx.Client,
    announcement: AnnouncementWithPdf,
    *,
    save_dir: str | Path | None = None,
) -> Path:
    target_dir = _resolve_save_dir(save_dir)
    target_path = target_dir / _derive_pdf_filename(announcement)
    if target_path.is_file():
        # workflow 重试时会反复进入下载阶段；本地已有 PDF 直接复用，避免重复请求
        # 巨潮静态文件服务。
        return target_path

    response = client.get(build_pdf_url(announcement), follow_redirects=True)
    response.raise_for_status()

    target_dir.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(response.content)
    return target_path


def _resolve_save_dir(save_dir: str | Path | None) -> Path:
    if save_dir is None:
        return _default_pdf_dir()
    return Path(save_dir)


def _default_pdf_dir() -> Path:
    # 默认目录只服务库的单独使用场景；业务 workflow 建议显式传 save_dir，避免安装
    # 到 site-packages 后把 PDF 写进虚拟环境目录。
    return Path(__file__).resolve().parents[2] / "data" / "cninfo_pdf"


def _build_pdf_url_from_adjunct_url(adjunct_url: str) -> str:
    # 巨潮返回 adjunctUrl 是相对路径；用 urljoin 处理前导斜杠，避免手拼 URL 时
    # 出现双斜杠或漏斜杠。
    return urljoin(PDF_BASE_URL, adjunct_url.lstrip("/"))


def _derive_pdf_filename(announcement: AnnouncementWithPdf) -> str:
    return build_pdf_filename(
        announcement_id=_get_announcement_id(announcement),
        announcement_title=_strip_highlight_tags(_get_announcement_title(announcement)),
        fallback_stem=Path(_get_adjunct_url(announcement)).stem,
    )


def _get_adjunct_url(announcement: AnnouncementWithPdf) -> str:
    if isinstance(announcement, BusinessAnnouncement):
        adjunct_url = announcement.adjunct_url
    else:
        adjunct_url = announcement.adjunctUrl
    adjunct_url = (adjunct_url or "").strip()
    if not adjunct_url:
        raise ValueError("announcement adjunctUrl is required")
    return adjunct_url


def _get_announcement_id(announcement: AnnouncementWithPdf) -> str | None:
    if isinstance(announcement, BusinessAnnouncement):
        return announcement.announcement_id
    return announcement.announcementId


def _get_announcement_title(announcement: AnnouncementWithPdf) -> str | None:
    if isinstance(announcement, BusinessAnnouncement):
        return announcement.announcement_title
    return announcement.announcementTitle


def _strip_highlight_tags(value: str | None) -> str | None:
    if value is None:
        return None
    return TAG_RE.sub("", value)


if __name__ == "__main__":
    from cninfo_announcement.client import query_announcements

    today = date.today()
    start = today - timedelta(days=7)
    result = query_announcements(
        "hk",
        searchkey="增持",
        start_date=start,
        end_date=today,
    )
    if not result.items:
        raise SystemExit("No CNInfo announcements found")

    announcement = result.items[0]
    path = download_pdf(announcement)
    print(path)
