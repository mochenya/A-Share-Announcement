from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from announcement_common.models import AnnouncementSource
from cninfo_announcement.client import ANNOUNCEMENT_URL, TOP_SEARCH_URL, CNInfoClient
from cninfo_announcement.models import CNInfoAnnouncementQueryResponse


@pytest.mark.parametrize(
    ("searchkey", "stock", "expected_searchkey", "expected_stock"),
    [
        (None, "000001", "", "000001,gssz0000001"),
        ("公告", None, "公告", ""),
        ("公告", "000001", "公告", "000001,gssz0000001"),
    ],
)
def test_cninfo_core_search_combinations(
    monkeypatch: pytest.MonkeyPatch,
    searchkey: str | None,
    stock: str | None,
    expected_searchkey: str,
    expected_stock: str,
) -> None:
    client = CNInfoClient(verify=False)
    captured_payloads: list[dict[str, str]] = []

    def post_with_retry(
        url: str,
        *,
        data: dict[str, str],
        parse: Any,
    ) -> CNInfoAnnouncementQueryResponse:
        if url == TOP_SEARCH_URL:
            assert data == {"keyWord": "000001", "maxNum": "10", "plate": "szsh"}
            return parse([{"code": "000001", "orgId": "gssz0000001"}])

        assert url == ANNOUNCEMENT_URL
        captured_payloads.append(data)
        return parse(
            {
                "totalAnnouncement": 1,
                "announcements": [
                    {
                        "secCode": stock or "000002",
                        "secName": "测试公司",
                        "orgId": "gssz0000001",
                        "announcementId": "1225275820",
                        "announcementTitle": "<em>公告</em>测试",
                        "announcementTime": 1777651200000,
                        "adjunctUrl": "finalpage/2026-05-01/1225275820.PDF",
                        "pageColumn": "SZSE",
                    }
                ],
                "hasMore": False,
            }
        )

    monkeypatch.setattr(client, "_post_with_retry", post_with_retry)

    try:
        result = client.query_announcements(
            "sz",
            searchkey=searchkey,
            stock=stock,
            start_date=date(2026, 1, 2),
            end_date="2026-01-05",
        )
    finally:
        client.close()

    assert captured_payloads == [
        {
            "pageNum": "1",
            "pageSize": "30",
            "column": "szse",
            "tabName": "fulltext",
            "plate": "sz",
            "stock": expected_stock,
            "searchkey": expected_searchkey,
            "secid": "",
            "category": "",
            "trade": "",
            "seDate": "2026-01-02~2026-01-05",
            "sortName": "",
            "sortType": "",
            "isHLtitle": "true",
        }
    ]
    assert result.source == AnnouncementSource.CNINFO
    assert result.response.total_announcement == 1
    assert result.items[0].announcement_title == "公告测试"
    assert result.items[0].adjunct_url == "finalpage/2026-05-01/1225275820.PDF"


def test_cninfo_query_rejects_empty_search_conditions() -> None:
    client = CNInfoClient(verify=False)
    try:
        with pytest.raises(
            ValueError, match="searchkey and stock cannot both be empty"
        ):
            client.query_announcements(
                "sz",
                searchkey=" ",
                stock=" ",
                start_date="2026-01-01",
                end_date="2026-01-05",
            )
    finally:
        client.close()


def test_cninfo_query_rejects_reversed_date_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = CNInfoClient(verify=False)

    def post_with_retry(**_kwargs: Any) -> None:
        pytest.fail("CNInfo request should not be sent for an invalid date range")

    monkeypatch.setattr(client, "_post_with_retry", post_with_retry)

    try:
        with pytest.raises(ValueError, match="start_date cannot be after end_date"):
            client.query_announcements(
                "sz",
                searchkey="公告",
                start_date="2026-01-05",
                end_date="2026-01-02",
            )
    finally:
        client.close()
