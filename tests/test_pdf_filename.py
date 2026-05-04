from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from announcement_common.models import AnnouncementSource, BusinessAnnouncement
from cninfo_announcement.client import CNInfoError
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
from szse_announcement.models import SZSEAnnouncementRecord
from szse_announcement.pdf import _derive_pdf_filename as derive_szse_pdf_filename
from szse_announcement.pdf import (
    _download_pdf_with_client as download_szse_pdf_with_client,
)

CNINFO_PDF_BYTES = b"%PDF-1.7\ncninfo\n%%EOF\n"
SSE_PDF_BYTES = b"%PDF-1.7\nsse\n%%EOF\n"
SZSE_PDF_BYTES = b"%PDF-1.7\nszse\n%%EOF\n"


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


def test_szse_pdf_filename_accepts_standard_and_raw_models() -> None:
    standard = BusinessAnnouncement(
        source=AnnouncementSource.SZSE,
        announcement_id="1225269298",
        announcement_title="公告测试",
        adjunct_url="/disc/disk03/finalpage/2026-04-30/test.PDF",
    )
    raw = SZSEAnnouncementRecord(
        annId=1225269298,
        title="公告测试",
        attachPath="/disc/disk03/finalpage/2026-04-30/test.PDF",
    )

    assert derive_szse_pdf_filename(standard) == "1225269298 - 公告测试.pdf"
    assert derive_szse_pdf_filename(raw) == "1225269298 - 公告测试.pdf"


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
            content=CNINFO_PDF_BYTES,
            headers={"content-type": "application/pdf"},
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        path = download_cninfo_pdf_with_client(client, announcement, save_dir=tmp_path)

    assert path == tmp_path / "1225275820 - 公告测试.pdf"
    assert path.read_bytes() == CNINFO_PDF_BYTES
    assert requested_urls == [
        "https://static.cninfo.com.cn/finalpage/2026-05-03/1225275820.PDF"
    ]


def test_cninfo_pdf_download_retries_rate_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    announcement = AnnouncementRecord(
        announcementId="1225275820",
        announcementTitle="公告测试",
        adjunctUrl="finalpage/2026-05-03/1225275820.PDF",
    )
    responses = [
        httpx.Response(429, headers={"Retry-After": "2"}),
        httpx.Response(
            200,
            content=CNINFO_PDF_BYTES,
            headers={"content-type": "application/pdf"},
        ),
    ]
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        response = responses.pop(0)
        response.request = request
        return response

    monkeypatch.setattr("cninfo_announcement.pdf.sleep", delays.append)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        path = download_cninfo_pdf_with_client(
            client,
            announcement,
            save_dir=tmp_path,
            retries=1,
        )

    assert path.read_bytes() == CNINFO_PDF_BYTES
    assert delays == [2.0]


def test_cninfo_pdf_download_rejects_non_pdf_response(tmp_path: Path) -> None:
    announcement = AnnouncementRecord(
        announcementId="1225275820",
        announcementTitle="公告测试",
        adjunctUrl="finalpage/2026-05-03/1225275820.PDF",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"<html>not pdf</html>",
            headers={"content-type": "application/pdf"},
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(CNInfoError, match="did not return a PDF"):
            download_cninfo_pdf_with_client(client, announcement, save_dir=tmp_path)

    assert not (tmp_path / "1225275820 - 公告测试.pdf").exists()


def test_cninfo_pdf_download_rejects_truncated_pdf_response(tmp_path: Path) -> None:
    announcement = AnnouncementRecord(
        announcementId="1225275820",
        announcementTitle="公告测试",
        adjunctUrl="finalpage/2026-05-03/1225275820.PDF",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"%PDF-1.7\ntruncated",
            headers={"content-type": "application/pdf"},
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(CNInfoError, match="did not return a PDF"):
            download_cninfo_pdf_with_client(client, announcement, save_dir=tmp_path)

    assert not (tmp_path / "1225275820 - 公告测试.pdf").exists()


def test_cninfo_pdf_download_replaces_corrupt_existing_file(tmp_path: Path) -> None:
    announcement = AnnouncementRecord(
        announcementId="1225275820",
        announcementTitle="公告测试",
        adjunctUrl="finalpage/2026-05-03/1225275820.PDF",
    )
    target_path = tmp_path / "1225275820 - 公告测试.pdf"
    target_path.write_bytes(b"<html>old error</html>")
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(
            200,
            content=CNINFO_PDF_BYTES,
            headers={"content-type": "application/pdf"},
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        path = download_cninfo_pdf_with_client(client, announcement, save_dir=tmp_path)

    assert path == target_path
    assert path.read_bytes() == CNINFO_PDF_BYTES
    assert requests == 1
    assert not (tmp_path / "1225275820 - 公告测试.pdf.part").exists()


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
            content=SSE_PDF_BYTES,
            headers={"content-type": "application/pdf"},
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        path = download_sse_pdf_with_client(client, announcement, save_dir=tmp_path)

    assert path == tmp_path / "sse60000020260101ABCD - 公告测试.pdf"
    assert path.read_bytes() == SSE_PDF_BYTES
    assert requested_urls == [
        "https://static.sse.com.cn/disclosure/listedinfo/announcement/c/"
        "600000_20260101_ABCD.pdf"
    ]


def test_sse_pdf_download_retries_rate_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    announcement = SSEBulletinFile(
        TITLE="公告测试",
        URL="/disclosure/listedinfo/announcement/c/600000_20260101_ABCD.pdf",
    )
    responses = [
        httpx.Response(429, headers={"Retry-After": "3"}),
        httpx.Response(
            200,
            content=SSE_PDF_BYTES,
            headers={"content-type": "application/pdf"},
        ),
    ]
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        response = responses.pop(0)
        response.request = request
        return response

    monkeypatch.setattr("sse_announcement.client.sleep", delays.append)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        path = download_sse_pdf_with_client(
            client,
            announcement,
            save_dir=tmp_path,
            retries=1,
        )

    assert path.read_bytes() == SSE_PDF_BYTES
    assert delays == [3.0]


def test_sse_pdf_download_solves_challenge_before_writing(tmp_path: Path) -> None:
    announcement = SSEBulletinFile(
        TITLE="公告测试",
        URL="/disclosure/listedinfo/announcement/c/600000_20260101_ABCD.pdf",
    )
    challenge = "arg1='1111111111111111111111111111111111111111'"
    seen_cookies: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_cookies.append(request.headers.get("cookie"))
        if len(seen_cookies) == 1:
            return httpx.Response(
                200,
                text=challenge,
                headers={"content-type": "text/html"},
                request=request,
            )
        return httpx.Response(
            200,
            content=SSE_PDF_BYTES,
            headers={"content-type": "application/pdf"},
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        path = download_sse_pdf_with_client(
            client,
            announcement,
            save_dir=tmp_path,
            retries=0,
        )

    assert path.read_bytes() == SSE_PDF_BYTES
    assert seen_cookies[0] is None
    assert seen_cookies[1] is not None
    assert "acw_sc__v2=" in seen_cookies[1]


def test_sse_pdf_download_replaces_corrupt_existing_file(tmp_path: Path) -> None:
    announcement = SSEBulletinFile(
        TITLE="公告测试",
        URL="/disclosure/listedinfo/announcement/c/600000_20260101_ABCD.pdf",
    )
    target_path = tmp_path / "sse60000020260101ABCD - 公告测试.pdf"
    target_path.write_bytes(b"<html>old error</html>")
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(
            200,
            content=SSE_PDF_BYTES,
            headers={"content-type": "application/pdf"},
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        path = download_sse_pdf_with_client(client, announcement, save_dir=tmp_path)

    assert path == target_path
    assert path.read_bytes() == SSE_PDF_BYTES
    assert requests == 1
    assert not (tmp_path / "sse60000020260101ABCD - 公告测试.pdf.part").exists()


def test_szse_pdf_download_writes_pdf_file(tmp_path: Path) -> None:
    announcement = SZSEAnnouncementRecord(
        annId=1225269298,
        title="公告测试",
        attachPath="/disc/disk03/finalpage/2026-04-30/test.PDF",
    )
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(
            200,
            content=SZSE_PDF_BYTES,
            headers={"content-type": "application/pdf"},
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        path = download_szse_pdf_with_client(client, announcement, save_dir=tmp_path)

    assert path == tmp_path / "1225269298 - 公告测试.pdf"
    assert path.read_bytes() == SZSE_PDF_BYTES
    assert requested_urls == [
        "https://disc.static.szse.cn/download/disc/disk03/finalpage/2026-04-30/test.PDF"
    ]


def test_szse_pdf_download_retries_rate_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    announcement = SZSEAnnouncementRecord(
        annId=1225269298,
        title="公告测试",
        attachPath="/disc/disk03/finalpage/2026-04-30/test.PDF",
    )
    responses = [
        httpx.Response(429, headers={"Retry-After": "4"}),
        httpx.Response(
            200,
            content=SZSE_PDF_BYTES,
            headers={"content-type": "application/pdf"},
        ),
    ]
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        response = responses.pop(0)
        response.request = request
        return response

    monkeypatch.setattr("szse_announcement.pdf.sleep", delays.append)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        path = download_szse_pdf_with_client(
            client,
            announcement,
            save_dir=tmp_path,
            retries=1,
        )

    assert path.read_bytes() == SZSE_PDF_BYTES
    assert delays == [4.0]


def test_szse_pdf_download_replaces_corrupt_existing_file(tmp_path: Path) -> None:
    announcement = SZSEAnnouncementRecord(
        annId=1225269298,
        title="公告测试",
        attachPath="/disc/disk03/finalpage/2026-04-30/test.PDF",
    )
    target_path = tmp_path / "1225269298 - 公告测试.pdf"
    target_path.write_bytes(b"<html>old error</html>")
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(
            200,
            content=SZSE_PDF_BYTES,
            headers={"content-type": "application/pdf"},
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        path = download_szse_pdf_with_client(client, announcement, save_dir=tmp_path)

    assert path == target_path
    assert path.read_bytes() == SZSE_PDF_BYTES
    assert requests == 1
    assert not (tmp_path / "1225269298 - 公告测试.pdf.part").exists()
