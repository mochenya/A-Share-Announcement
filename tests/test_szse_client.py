from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from announcement_common.models import AnnouncementSource
from szse_announcement.client import QUERY_URL, SZSEAnnouncementClient
from szse_announcement.models import SZSEAnnouncementQueryResponse


def _announcement(
    ann_id: int | str = 1225269298,
    title: str = "豆神教育：关于公司董事、高级管理人员增持公司股份的公告",
    publish_time: str = "2026-04-30 18:49:39",
) -> dict[str, Any]:
    return {
        "id": "ab2cb73f-cb7c-4a2b-aca1-861161862193",
        "annId": ann_id,
        "title": title,
        "publishTime": publish_time,
        "attachPath": "/disc/disk03/finalpage/2026-04-30/test.PDF",
        "attachFormat": "PDF",
        "attachSize": 88,
        "secCode": ["300010"],
        "secName": ["豆神教育"],
    }


@pytest.mark.parametrize(
    ("searchkey", "stock", "expected_payload"),
    [
        (
            None,
            "300010",
            {
                "seDate": ["2026-04-22", "2026-05-04"],
                "channelCode": ["listedNotice_disc"],
                "pageSize": 50,
                "pageNum": 1,
                "stock": ["300010"],
            },
        ),
        (
            "增持",
            None,
            {
                "seDate": ["2026-04-22", "2026-05-04"],
                "channelCode": ["listedNotice_disc"],
                "pageSize": 50,
                "pageNum": 1,
                "searchKey": ["增持"],
            },
        ),
        (
            "增持",
            "300010",
            {
                "seDate": ["2026-04-22", "2026-05-04"],
                "channelCode": ["listedNotice_disc"],
                "pageSize": 50,
                "pageNum": 1,
                "searchKey": ["增持"],
                "stock": ["300010"],
            },
        ),
    ],
)
def test_szse_core_search_combinations(
    monkeypatch: pytest.MonkeyPatch,
    searchkey: str | None,
    stock: str | None,
    expected_payload: dict[str, Any],
) -> None:
    client = SZSEAnnouncementClient(verify=False)
    captured_payloads: list[dict[str, Any]] = []

    def post_with_retry(
        url: str,
        *,
        data: dict[str, Any],
        parse: Any,
    ) -> SZSEAnnouncementQueryResponse:
        assert url == QUERY_URL
        captured_payloads.append(data)
        return parse({"announceCount": 1, "data": [_announcement()]})

    monkeypatch.setattr(client, "_post_with_retry", post_with_retry)

    try:
        result = client.query_announcements(
            searchkey=searchkey,
            stock=stock,
            start_date=date(2026, 4, 22),
            end_date="2026-05-04",
        )
    finally:
        client.close()

    assert captured_payloads == [expected_payload]
    assert result.source == AnnouncementSource.SZSE
    assert result.response.total_announcement == 1
    assert result.response.has_more is False
    assert result.items[0].announcement_id == "1225269298"
    assert (
        result.items[0].announcement_title
        == "豆神教育：关于公司董事、高级管理人员增持公司股份的公告"
    )
    assert result.items[0].announcement_time == 1777546179000
    assert result.items[0].sec_code == "300010"
    assert result.items[0].sec_name == "豆神教育"
    assert result.items[0].org_id == "szse300010"
    assert result.items[0].adjunct_url == "/disc/disk03/finalpage/2026-04-30/test.PDF"


def test_szse_query_rejects_empty_search_conditions() -> None:
    client = SZSEAnnouncementClient(verify=False)
    try:
        with pytest.raises(
            ValueError, match="searchkey and stock cannot both be empty"
        ):
            client.query_announcements(
                searchkey=" ",
                stock=" ",
                start_date="2026-04-22",
                end_date="2026-05-04",
            )
    finally:
        client.close()


def test_szse_query_rejects_reversed_date_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SZSEAnnouncementClient(verify=False)

    def post_with_retry(**_kwargs: Any) -> None:
        pytest.fail("SZSE request should not be sent for an invalid date range")

    monkeypatch.setattr(client, "_post_with_retry", post_with_retry)

    try:
        with pytest.raises(ValueError, match="start_date cannot be after end_date"):
            client.query_announcements(
                searchkey="增持",
                start_date="2026-05-04",
                end_date="2026-04-22",
            )
    finally:
        client.close()


def test_szse_limit_marks_current_page_truncation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SZSEAnnouncementClient(verify=False)

    def post_with_retry(
        _url: str,
        *,
        data: dict[str, Any],
        parse: Any,
    ) -> SZSEAnnouncementQueryResponse:
        assert data["pageNum"] == 1
        return parse(
            {
                "announceCount": 3,
                "data": [
                    _announcement(ann_id=1, title="公告一"),
                    _announcement(ann_id=2, title="公告二"),
                    _announcement(ann_id=3, title="公告三"),
                ],
            }
        )

    monkeypatch.setattr(client, "_post_with_retry", post_with_retry)
    try:
        result = client.query_announcements(
            searchkey="公告",
            start_date="2026-04-22",
            end_date="2026-05-04",
            limit=2,
        )
    finally:
        client.close()

    assert result.response.total_announcement == 2
    assert result.response.has_more is True
    assert [item.announcement_id for item in result.items] == ["1", "2"]
