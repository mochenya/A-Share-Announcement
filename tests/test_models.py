from __future__ import annotations

import pytest

from cninfo_announcement.models import CNInfoAnnouncementQueryResponse
from sse_announcement.models import (
    SSEBulletinFile,
    SSEBulletinQueryResponse,
    build_announcement_id as build_sse_announcement_id,
)
from szse_announcement.models import (
    SZSEAnnouncementRecord,
    SZSEAnnouncementQueryResponse,
    build_announcement_id as build_szse_announcement_id,
)


def test_cninfo_query_response_normalizes_null_lists() -> None:
    response = CNInfoAnnouncementQueryResponse.model_validate(
        {
            "classifiedAnnouncements": None,
            "announcements": None,
            "categoryList": None,
        }
    )

    assert response.classifiedAnnouncements == []
    assert response.announcements == []
    assert response.categoryList == []


def test_sse_query_response_normalizes_null_result() -> None:
    response = SSEBulletinQueryResponse.model_validate({"result": None})

    assert response.result == []


def test_sse_query_response_wraps_single_file_result_items() -> None:
    response = SSEBulletinQueryResponse.model_validate(
        {
            "result": [
                {
                    "TITLE": "公告测试",
                    "URL": "/disclosure/listedinfo/announcement/c/600000_20260102_ABCD.pdf",
                }
            ]
        }
    )

    assert len(response.result) == 1
    assert len(response.result[0]) == 1
    assert response.result[0][0].TITLE == "公告测试"


def test_sse_query_response_rejects_non_list_result() -> None:
    with pytest.raises(TypeError, match="result must be a list"):
        SSEBulletinQueryResponse.model_validate({"result": {"URL": "test.pdf"}})


def test_sse_build_announcement_id_uses_pdf_stem_without_underscores() -> None:
    item = SSEBulletinFile(
        URL="/disclosure/listedinfo/announcement/c/600000_20260102_ABCD.pdf"
    )

    assert build_sse_announcement_id(item) == "sse60000020260102ABCD"


def test_sse_build_announcement_id_rejects_missing_url() -> None:
    with pytest.raises(ValueError, match="SSE bulletin is missing URL"):
        build_sse_announcement_id(SSEBulletinFile())


def test_szse_announcement_record_normalizes_security_lists() -> None:
    response = SZSEAnnouncementRecord.model_validate(
        {
            "secCode": ["300010", None, 1],
            "secName": "豆神教育",
        }
    )

    assert response.secCode == ["300010", "1"]
    assert response.secName == ["豆神教育"]


def test_szse_announcement_record_normalizes_null_security_lists() -> None:
    response = SZSEAnnouncementRecord.model_validate(
        {
            "secCode": None,
            "secName": None,
        }
    )

    assert response.secCode == []
    assert response.secName == []


def test_szse_query_response_normalizes_null_data() -> None:
    response = SZSEAnnouncementQueryResponse.model_validate({"data": None})

    assert response.data == []


def test_szse_build_announcement_id_prefers_ann_id() -> None:
    item = SZSEAnnouncementRecord(
        annId=1225269298,
        id="fallback-id",
        attachPath="/disc/disk03/finalpage/2026-04-30/fallback.PDF",
    )

    assert build_szse_announcement_id(item) == "1225269298"


def test_szse_build_announcement_id_falls_back_to_id() -> None:
    item = SZSEAnnouncementRecord(
        id="ab2cb73f-cb7c-4a2b-aca1-861161862193",
        attachPath="/disc/disk03/finalpage/2026-04-30/fallback.PDF",
    )

    assert build_szse_announcement_id(item) == "ab2cb73f-cb7c-4a2b-aca1-861161862193"


def test_szse_build_announcement_id_falls_back_to_attach_path_stem() -> None:
    item = SZSEAnnouncementRecord(
        attachPath="/disc/disk03/finalpage/2026-04-30/1225269298.PDF"
    )

    assert build_szse_announcement_id(item) == "1225269298"


def test_szse_build_announcement_id_rejects_missing_identity_fields() -> None:
    with pytest.raises(
        ValueError,
        match="SZSE announcement is missing annId, id, and attachPath",
    ):
        build_szse_announcement_id(SZSEAnnouncementRecord())
