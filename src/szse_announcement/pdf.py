from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urljoin

if __package__ in (None, ""):
    # 允许 `uv run src/szse_announcement/pdf.py` 直接跑下载烟测。
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from announcement_common.filename import build_pdf_filename
from szse_announcement.models import (
    BusinessAnnouncement,
    SZSEAnnouncementRecord,
    build_announcement_id,
)

PDF_BASE_URL = "https://disc.static.szse.cn/download/"

AnnouncementWithPdf = BusinessAnnouncement | SZSEAnnouncementRecord


def build_pdf_url(announcement: AnnouncementWithPdf) -> str:
    return _build_pdf_url_from_attach_path(_get_attach_path(announcement))


def download_pdf(
    announcement: AnnouncementWithPdf,
    *,
    save_dir: str | Path | None = None,
) -> Path:
    from szse_announcement.client import SZSEAnnouncementClient

    with SZSEAnnouncementClient() as client:
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
        # workflow 重试时直接复用本地文件，避免重复打到深交所静态文件服务。
        return target_path

    from szse_announcement.client import SZSEUnexpectedResponseError, _build_pdf_headers

    response = client.get(
        build_pdf_url(announcement),
        headers=_build_pdf_headers(client),
        follow_redirects=True,
    )
    response.raise_for_status()
    if not _is_pdf_response(response):
        content_type = response.headers.get("content-type")
        raise SZSEUnexpectedResponseError(
            f"SZSE PDF request did not return a PDF: {content_type}"
        )

    target_dir.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(response.content)
    return target_path


def _resolve_save_dir(save_dir: str | Path | None) -> Path:
    if save_dir is None:
        return _default_pdf_dir()
    return Path(save_dir)


def _default_pdf_dir() -> Path:
    # 默认目录只服务库的单独使用场景；业务 workflow 建议显式传 save_dir。
    return Path(__file__).resolve().parents[2] / "data" / "szse_pdf"


def _build_pdf_url_from_attach_path(attach_path: str) -> str:
    # 实测 attachPath 是 /disc/disk03/...；download 前缀和静态直链都可用。
    return urljoin(PDF_BASE_URL, attach_path.lstrip("/"))


def _derive_pdf_filename(announcement: AnnouncementWithPdf) -> str:
    return build_pdf_filename(
        announcement_id=_get_announcement_id(announcement),
        announcement_title=_get_announcement_title(announcement),
        fallback_stem=Path(_get_attach_path(announcement)).stem,
    )


def _get_attach_path(announcement: AnnouncementWithPdf) -> str:
    if isinstance(announcement, BusinessAnnouncement):
        attach_path = announcement.adjunct_url
    else:
        attach_path = announcement.attachPath
    normalized = (attach_path or "").strip()
    if not normalized:
        raise ValueError("announcement attachPath is required")
    return normalized


def _get_announcement_id(announcement: AnnouncementWithPdf) -> str | None:
    if isinstance(announcement, BusinessAnnouncement):
        return announcement.announcement_id
    return build_announcement_id(announcement)


def _get_announcement_title(announcement: AnnouncementWithPdf) -> str | None:
    if isinstance(announcement, BusinessAnnouncement):
        return announcement.announcement_title
    return announcement.title


def _is_pdf_response(response: httpx.Response) -> bool:
    content_type = response.headers.get("content-type", "")
    return response.status_code == 200 and (
        response.content.startswith(b"%PDF-")
        or content_type.startswith("application/pdf")
    )


if __name__ == "__main__":
    from szse_announcement.client import query_announcements

    today = date.today()
    start = today - timedelta(days=7)
    result = query_announcements(
        searchkey="增持",
        start_date=start,
        end_date=today,
        limit=1,
    )
    if not result.items:
        raise SystemExit("No SZSE announcements found")

    announcement = result.items[0]
    path = download_pdf(announcement)
    print(path)
