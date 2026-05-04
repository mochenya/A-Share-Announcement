from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from announcement_common.models import AnnouncementSource
from sse_announcement.client import QUERY_URL, SSEAnnouncementClient
from sse_announcement.models import SSEBulletinQueryResponse


def _main_file(url: str, title: str = "公告测试") -> dict[str, Any]:
    return {
        "ORG_BULLETIN_ID": "BULLETIN-1",
        "ORG_FILE_TYPE": 0,
        "SECURITY_CODE": "600000",
        "SECURITY_NAME": "浦发银行",
        "SSEDATE": "2026-01-02",
        "TITLE": title,
        "URL": url,
    }


@pytest.mark.parametrize(
    ("searchkey", "stock", "expected_title", "expected_stock"),
    [
        (None, "600000", "", "600000"),
        ("公告", None, "公告", None),
        ("公告", "600000", "公告", "600000"),
    ],
)
def test_sse_core_search_combinations(
    monkeypatch: pytest.MonkeyPatch,
    searchkey: str | None,
    stock: str | None,
    expected_title: str,
    expected_stock: str | None,
) -> None:
    client = SSEAnnouncementClient(verify=False)
    captured_params: list[dict[str, str]] = []

    def get_with_retry(
        url: str,
        *,
        params: dict[str, str],
        parse: Any,
    ) -> SSEBulletinQueryResponse:
        assert url == QUERY_URL
        captured_params.append(params)
        return parse(
            {
                "pageHelp": {"pageNo": 1, "pageCount": 1, "total": 1},
                "result": [
                    [
                        _main_file(
                            "/disclosure/listedinfo/announcement/c/600000_20260102_ABCD.pdf"
                        )
                    ]
                ],
            }
        )

    monkeypatch.setattr(client, "_get_with_retry", get_with_retry)

    try:
        result = client.query_announcements(
            searchkey=searchkey,
            stock=stock,
            start_date=date(2026, 1, 1),
            end_date="2026-01-05",
        )
    finally:
        client.close()

    expected_params = {
        "START_DATE": "2026-01-01",
        "END_DATE": "2026-01-05",
        "TITLE": expected_title,
        "isPagination": "true",
        "pageHelp.pageNo": "1",
        "pageHelp.pageSize": "100",
        "pageHelp.beginPage": "1",
        "pageHelp.cacheSize": "1",
    }
    if expected_stock is not None:
        expected_params["SECURITY_CODE"] = expected_stock

    assert captured_params == [expected_params]
    assert result.source == AnnouncementSource.SSE
    assert result.response.total_announcement == 1
    assert result.items[0].announcement_id == "sse60000020260102ABCD"
    assert result.items[0].announcement_title == "公告测试"
    assert result.items[0].adjunct_url.endswith("600000_20260102_ABCD.pdf")


def test_sse_query_rejects_empty_search_conditions() -> None:
    client = SSEAnnouncementClient(verify=False)
    try:
        with pytest.raises(
            ValueError, match="searchkey and stock cannot both be empty"
        ):
            client.query_announcements(
                searchkey=" ",
                stock=" ",
                start_date="2026-01-01",
                end_date="2026-01-05",
            )
    finally:
        client.close()


def test_sse_limit_uses_incremental_deduplication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SSEAnnouncementClient(verify=False)
    responses = [
        SSEBulletinQueryResponse.model_validate(
            {
                "pageHelp": {"pageNo": 1, "pageCount": 2},
                "result": [
                    [_main_file("/disclosure/listedinfo/announcement/c/test_1.pdf")],
                    [_main_file("/disclosure/listedinfo/announcement/c/test_1.pdf")],
                    [_main_file("/disclosure/listedinfo/announcement/c/test_2.pdf")],
                    [_main_file("/disclosure/listedinfo/announcement/c/test_3.pdf")],
                ],
            }
        )
    ]

    def iter_window_responses(**_kwargs: Any) -> list[SSEBulletinQueryResponse]:
        return responses

    monkeypatch.setattr(client, "_iter_window_responses", iter_window_responses)
    try:
        result = client.query_announcements(
            searchkey="公告",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 2),
            limit=2,
        )
    finally:
        client.close()

    assert result.response.total_announcement == 2
    assert result.response.has_more is True
    assert [item.announcement_id for item in result.items] == [
        "ssetest1",
        "ssetest2",
    ]
