from __future__ import annotations

from datetime import date
from typing import Any

import httpx
import pytest

from announcement_common.models import AnnouncementSource
from sse_announcement.client import (
    QUERY_URL,
    SSEAnnouncementClient,
    SSEUnexpectedResponseError,
)
from sse_announcement.models import SSEBulletinFile, SSEBulletinQueryResponse


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


def test_sse_query_rejects_reversed_date_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SSEAnnouncementClient(verify=False)

    def iter_window_responses(**_kwargs: Any) -> None:
        pytest.fail("SSE request should not be sent for an invalid date range")

    monkeypatch.setattr(client, "_iter_window_responses", iter_window_responses)

    try:
        with pytest.raises(ValueError, match="start_date cannot be after end_date"):
            client.query_announcements(
                searchkey="公告",
                start_date="2026-01-05",
                end_date="2026-01-02",
            )
    finally:
        client.close()


def test_sse_query_rejects_non_positive_limit() -> None:
    client = SSEAnnouncementClient(verify=False)
    try:
        with pytest.raises(ValueError, match="limit must be greater than 0"):
            client.query_announcements(
                searchkey="公告",
                start_date="2026-01-01",
                end_date="2026-01-02",
                limit=0,
            )
    finally:
        client.close()


def test_sse_keyword_only_query_splits_long_date_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SSEAnnouncementClient(verify=False)
    windows: list[tuple[date, date, str | None]] = []

    def iter_window_responses(
        *,
        searchkey: str,
        start_date: date,
        end_date: date,
        stock: str | None,
    ) -> list[SSEBulletinQueryResponse]:
        assert searchkey == "公告"
        windows.append((start_date, end_date, stock))
        return [
            SSEBulletinQueryResponse.model_validate(
                {
                    "pageHelp": {"pageNo": 1, "pageCount": 1},
                    "result": [],
                }
            )
        ]

    monkeypatch.setattr(client, "_iter_window_responses", iter_window_responses)
    try:
        result = client.query_announcements(
            searchkey="公告",
            start_date="2026-01-01",
            end_date="2026-04-15",
        )
    finally:
        client.close()

    assert windows == [
        (date(2026, 1, 1), date(2026, 3, 31), None),
        (date(2026, 4, 1), date(2026, 4, 15), None),
    ]
    assert result.response.total_announcement == 0


def test_sse_stock_query_does_not_split_long_date_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SSEAnnouncementClient(verify=False)
    windows: list[tuple[date, date, str | None]] = []

    def iter_window_responses(
        *,
        searchkey: str,
        start_date: date,
        end_date: date,
        stock: str | None,
    ) -> list[SSEBulletinQueryResponse]:
        assert searchkey == ""
        windows.append((start_date, end_date, stock))
        return [
            SSEBulletinQueryResponse.model_validate(
                {
                    "pageHelp": {"pageNo": 1, "pageCount": 1},
                    "result": [],
                }
            )
        ]

    monkeypatch.setattr(client, "_iter_window_responses", iter_window_responses)
    try:
        result = client.query_announcements(
            stock="600000",
            start_date="2026-01-01",
            end_date="2026-12-31",
        )
    finally:
        client.close()

    assert windows == [(date(2026, 1, 1), date(2026, 12, 31), "600000")]
    assert result.response.total_announcement == 0


def test_sse_limit_marks_more_data_in_later_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SSEAnnouncementClient(verify=False)
    requested_windows: list[tuple[date, date]] = []

    def iter_window_responses(
        *,
        searchkey: str,
        start_date: date,
        end_date: date,
        stock: str | None,
    ) -> list[SSEBulletinQueryResponse]:
        assert searchkey == "公告"
        assert stock is None
        requested_windows.append((start_date, end_date))
        return [
            SSEBulletinQueryResponse.model_validate(
                {
                    "pageHelp": {"pageNo": 1, "pageCount": 1},
                    "result": [
                        [
                            _main_file(
                                "/disclosure/listedinfo/announcement/c/test_1.pdf"
                            )
                        ]
                    ],
                }
            )
        ]

    monkeypatch.setattr(client, "_iter_window_responses", iter_window_responses)
    try:
        result = client.query_announcements(
            searchkey="公告",
            start_date="2026-01-01",
            end_date="2026-04-15",
            limit=1,
        )
    finally:
        client.close()

    assert requested_windows == [(date(2026, 1, 1), date(2026, 3, 31))]
    assert result.response.total_announcement == 1
    assert result.response.has_more is True


def test_sse_select_group_files_can_include_attachments() -> None:
    client = SSEAnnouncementClient(verify=False)
    main = SSEBulletinFile(ORG_FILE_TYPE=0, URL="/main.pdf")
    attachment = SSEBulletinFile(ORG_FILE_TYPE=1, URL="/attachment.pdf")
    try:
        assert client._select_group_files(
            [main, attachment],
            include_attachments=True,
        ) == [main, attachment]
    finally:
        client.close()


def test_sse_select_group_files_rejects_missing_main_file() -> None:
    client = SSEAnnouncementClient(verify=False)
    try:
        with pytest.raises(
            SSEUnexpectedResponseError,
            match="did not contain exactly one main file",
        ):
            client._select_group_files(
                [SSEBulletinFile(ORG_FILE_TYPE=1, URL="/attachment.pdf")],
                include_attachments=False,
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


def test_sse_query_sleeps_between_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SSEAnnouncementClient(verify=False)
    pages: list[str] = []
    delays: list[float] = []
    responses = [
        SSEBulletinQueryResponse.model_validate(
            {
                "pageHelp": {"pageNo": 1, "pageCount": 2, "total": 2},
                "result": [
                    [_main_file("/disclosure/listedinfo/announcement/c/test_1.pdf")]
                ],
            }
        ),
        SSEBulletinQueryResponse.model_validate(
            {
                "pageHelp": {"pageNo": 2, "pageCount": 2, "total": 2},
                "result": [
                    [_main_file("/disclosure/listedinfo/announcement/c/test_2.pdf")]
                ],
            }
        ),
    ]

    def get_with_retry(
        url: str,
        *,
        params: dict[str, str],
        parse: Any,
    ) -> SSEBulletinQueryResponse:
        assert url == QUERY_URL
        pages.append(params["pageHelp.pageNo"])
        return responses.pop(0)

    monkeypatch.setattr(client, "_get_with_retry", get_with_retry)
    monkeypatch.setattr("sse_announcement.client.sleep", delays.append)
    monkeypatch.setattr(
        "sse_announcement.client.DEFAULT_INTER_PAGE_DELAY_SECONDS",
        0.2,
    )

    try:
        result = client.query_announcements(
            searchkey="test",
            start_date="2026-01-01",
            end_date="2026-01-02",
        )
    finally:
        client.close()

    assert pages == ["1", "2"]
    assert delays == [0.2]
    assert result.response.total_announcement == 2


def test_sse_retry_respects_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SSEAnnouncementClient(verify=False, retries=1)
    responses = [
        httpx.Response(
            429,
            headers={"Retry-After": "3"},
            request=httpx.Request("GET", QUERY_URL),
        ),
        httpx.Response(
            200,
            json={"ok": True},
            request=httpx.Request("GET", QUERY_URL),
        ),
    ]
    delays: list[float] = []

    def get(_url: str, *, params: dict[str, str]) -> httpx.Response:
        assert params == {"pageHelp.pageNo": "1"}
        return responses.pop(0)

    monkeypatch.setattr(client._client, "get", get)
    monkeypatch.setattr("sse_announcement.client.sleep", delays.append)

    try:
        result = client._get_with_retry(
            QUERY_URL,
            params={"pageHelp.pageNo": "1"},
            parse=lambda raw: raw,
        )
    finally:
        client.close()

    assert result == {"ok": True}
    assert delays == [3.0]
