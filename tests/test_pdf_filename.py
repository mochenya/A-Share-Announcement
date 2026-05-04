from __future__ import annotations

from pathlib import Path

import httpx

from announcement_common.models import AnnouncementSource, BusinessAnnouncement
from cninfo_announcement.models import AnnouncementRecord
from cninfo_announcement.pdf import (
    _derive_pdf_filename as derive_cninfo_pdf_filename,
)
from cninfo_announcement.pdf import (
    _download_pdf_with_client as download_cninfo_pdf_with_client,
)
from sse_announcement.models import SSEBulletinFile
from sse_announcement.pdf import _derive_pdf_filename as derive_sse_pdf_filename
from sse_announcement.pdf import (
    _download_pdf_with_client as download_sse_pdf_with_client,
)


def test_cninfo_pdf_filename_accepts_standard_and_raw_models() -> None:
    standard = BusinessAnnouncement(
        source=AnnouncementSource.CNINFO,
        announcement_id="1225275820",
        announcement_title="<em>公告</em>测试",
        adjunct_url="finalpage/2026-05-03/1225275820.PDF",
    )
    raw = AnnouncementRecord(
        announcementId="1225275820",
        announcementTitle="<em>公告</em>测试",
        adjunctUrl="finalpage/2026-05-03/1225275820.PDF",
    )

    assert derive_cninfo_pdf_filename(standard) == "1225275820 - 公告测试.pdf"
    assert derive_cninfo_pdf_filename(raw) == "1225275820 - 公告测试.pdf"


def test_sse_pdf_filename_accepts_standard_and_raw_models() -> None:
    standard = BusinessAnnouncement(
        source=AnnouncementSource.SSE,
        announcement_id="sse60000020260101ABCD",
        announcement_title="公告测试",
        adjunct_url="/disclosure/listedinfo/announcement/c/600000_20260101_ABCD.pdf",
    )
    raw = SSEBulletinFile(
        TITLE="公告测试",
        URL="/disclosure/listedinfo/announcement/c/600000_20260101_ABCD.pdf",
    )

    assert derive_sse_pdf_filename(standard) == "sse60000020260101ABCD - 公告测试.pdf"
    assert derive_sse_pdf_filename(raw) == "sse60000020260101ABCD - 公告测试.pdf"


def test_cninfo_pdf_download_writes_pdf_file(tmp_path: Path) -> None:
    announcement = AnnouncementRecord(
        announcementId="1225275820",
        announcementTitle="<em>公告</em>测试",
        adjunctUrl="finalpage/2026-05-03/1225275820.PDF",
    )
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(
            200,
            content=b"%PDF-cninfo",
            headers={"content-type": "application/pdf"},
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        path = download_cninfo_pdf_with_client(client, announcement, save_dir=tmp_path)

    assert path == tmp_path / "1225275820 - 公告测试.pdf"
    assert path.read_bytes() == b"%PDF-cninfo"
    assert requested_urls == [
        "https://static.cninfo.com.cn/finalpage/2026-05-03/1225275820.PDF"
    ]


def test_sse_pdf_download_writes_pdf_file(tmp_path: Path) -> None:
    announcement = SSEBulletinFile(
        TITLE="公告测试",
        URL="/disclosure/listedinfo/announcement/c/600000_20260101_ABCD.pdf",
    )
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(
            200,
            content=b"%PDF-sse",
            headers={"content-type": "application/pdf"},
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        path = download_sse_pdf_with_client(client, announcement, save_dir=tmp_path)

    assert path == tmp_path / "sse60000020260101ABCD - 公告测试.pdf"
    assert path.read_bytes() == b"%PDF-sse"
    assert requested_urls == [
        "https://static.sse.com.cn/disclosure/listedinfo/announcement/c/"
        "600000_20260101_ABCD.pdf"
    ]
