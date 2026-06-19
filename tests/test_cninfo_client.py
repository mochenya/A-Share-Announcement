from __future__ import annotations

from datetime import date
from typing import Any

import httpx
import pytest

from announcement_common.models import AnnouncementSource
from cninfo_announcement.client import (
    ANNOUNCEMENT_URL,
    TOP_SEARCH_URL,
    CNInfoClient,
    CNInfoError,
)
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


def test_cninfo_resolve_stock_keeps_pre_resolved_stock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = CNInfoClient(verify=False)

    def post_with_retry(**_kwargs: Any) -> None:
        pytest.fail("CNInfo topSearch should not be called for resolved stock")

    monkeypatch.setattr(client, "_post_with_retry", post_with_retry)

    try:
        assert client._resolve_stock("sz", "000001,gssz0000001") == (
            "000001,gssz0000001"
        )
    finally:
        client.close()


def test_cninfo_resolve_stock_rejects_missing_exact_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = CNInfoClient(verify=False)

    def post_with_retry(
        url: str,
        *,
        data: dict[str, str],
        parse: Any,
    ) -> list[Any]:
        assert url == TOP_SEARCH_URL
        assert data == {"keyWord": "000001", "maxNum": "10", "plate": "szsh"}
        return parse([{"code": "000002", "orgId": "gssz0000002"}])

    monkeypatch.setattr(client, "_post_with_retry", post_with_retry)

    try:
        with pytest.raises(CNInfoError, match="Unable to resolve stock code: 000001"):
            client._resolve_stock("sz", "000001")
    finally:
        client.close()


def test_cninfo_resolve_stock_rejects_ambiguous_org_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = CNInfoClient(verify=False)

    def post_with_retry(
        url: str,
        *,
        data: dict[str, str],
        parse: Any,
    ) -> list[Any]:
        assert url == TOP_SEARCH_URL
        assert data == {"keyWord": "000001", "maxNum": "10", "plate": "szsh"}
        return parse(
            [
                {"code": "000001", "orgId": "gssz0000001"},
                {"code": "000001", "orgId": "gssz0000001-alt"},
            ]
        )

    monkeypatch.setattr(client, "_post_with_retry", post_with_retry)

    try:
        with pytest.raises(CNInfoError, match="Stock code resolved ambiguously: 000001"):
            client._resolve_stock("sz", "000001")
    finally:
        client.close()


def test_cninfo_query_sleeps_between_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = CNInfoClient(verify=False)
    pages: list[str] = []
    delays: list[float] = []

    def post_with_retry(
        url: str,
        *,
        data: dict[str, str],
        parse: Any,
    ) -> CNInfoAnnouncementQueryResponse:
        assert url == ANNOUNCEMENT_URL
        pages.append(data["pageNum"])
        return parse(
            {
                "totalAnnouncement": 2,
                "announcements": [
                    {
                        "secCode": "000001",
                        "secName": "Ping An Bank",
                        "orgId": "gssz0000001",
                        "announcementId": f"ann-{data['pageNum']}",
                        "announcementTitle": "test",
                        "announcementTime": 1777651200000,
                        "adjunctUrl": f"finalpage/test-{data['pageNum']}.PDF",
                        "pageColumn": "SZSE",
                    }
                ],
                "hasMore": data["pageNum"] == "1",
            }
        )

    monkeypatch.setattr(client, "_post_with_retry", post_with_retry)
    monkeypatch.setattr("cninfo_announcement.client.sleep", delays.append)
    monkeypatch.setattr(
        "cninfo_announcement.client.DEFAULT_INTER_PAGE_DELAY_SECONDS",
        0.2,
    )

    try:
        result = client.query_announcements(
            "sz",
            searchkey="test",
            start_date="2026-01-01",
            end_date="2026-01-02",
        )
    finally:
        client.close()

    assert pages == ["1", "2"]
    assert delays == [0.2]
    assert result.response.total_announcement == 2


def test_cninfo_retry_respects_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = CNInfoClient(verify=False, retries=1)
    responses = [
        httpx.Response(
            429,
            headers={"Retry-After": "2"},
            request=httpx.Request("POST", ANNOUNCEMENT_URL),
        ),
        httpx.Response(
            200,
            json={"ok": True},
            request=httpx.Request("POST", ANNOUNCEMENT_URL),
        ),
    ]
    delays: list[float] = []

    def post(_url: str, *, data: dict[str, str]) -> httpx.Response:
        assert data == {"pageNum": "1"}
        return responses.pop(0)

    monkeypatch.setattr(client._client, "post", post)
    monkeypatch.setattr("cninfo_announcement.client.sleep", delays.append)

    try:
        result = client._post_with_retry(
            ANNOUNCEMENT_URL,
            data={"pageNum": "1"},
            parse=lambda raw: raw,
        )
    finally:
        client.close()

    assert result == {"ok": True}
    assert delays == [2.0]
