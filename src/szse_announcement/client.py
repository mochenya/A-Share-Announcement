from __future__ import annotations

import json
import random
import sys
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from time import sleep
from typing import Any, TypeVar

if __package__ in (None, ""):
    # 允许 `uv run src/szse_announcement/client.py` 直接跑查询烟测。
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from announcement_common.http import (
    VerifyTypes,
    build_headers_with_user_agent,
    create_http_client,
    retry_delay_seconds,
    should_retry_status,
)
from announcement_common.models import AnnouncementSource
from szse_announcement.config import (
    DEFAULT_LIMITS,
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT,
    DEFAULT_USER_AGENT,
)
from szse_announcement.models import (
    AnnouncementQueryResponse,
    AnnouncementQueryResult,
    BusinessAnnouncement,
    SZSEAnnouncementQueryResponse,
    SZSEAnnouncementRecord,
    build_announcement_id,
)
from szse_announcement.pdf import (
    AnnouncementWithPdf,
    _download_pdf_with_client,
    build_pdf_url as build_announcement_pdf_url,
)

QUERY_URL = "https://www.szse.cn/api/disc/announcement/annList"
REFERER_URL = "https://www.szse.cn/disclosure/listed/notice/index.html"
CHANNEL_CODE = "listedNotice_disc"
PAGE_SIZE = 50
INTER_PAGE_DELAY_SECONDS = 0.2
CHINA_TIMEZONE = timezone(timedelta(hours=8), name="Asia/Shanghai")
DEFAULT_HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,zh-TW;q=0.6",
    "Content-Type": "application/json; charset=UTF-8",
    "Origin": "https://www.szse.cn",
    "Referer": REFERER_URL,
    "User-Agent": DEFAULT_USER_AGENT,
    "X-Request-Type": "ajax",
    "X-Requested-With": "XMLHttpRequest",
}
PDF_HEADERS = {
    "Accept": "application/pdf,application/octet-stream,*/*",
    "Referer": REFERER_URL,
    "User-Agent": DEFAULT_USER_AGENT,
}
T = TypeVar("T")


class SZSEAnnouncementError(Exception):
    pass


class SZSEUnexpectedResponseError(SZSEAnnouncementError):
    pass


class SZSEAnnouncementClient:
    def __init__(
        self,
        *,
        timeout: float | httpx.Timeout | None = None,
        limits: httpx.Limits | None = None,
        retries: int = DEFAULT_RETRIES,
        verify: VerifyTypes | None = None,
        user_agent: str | None = None,
    ) -> None:
        self._client, self.timeout, self.limits, self.user_agent = create_http_client(
            timeout=timeout,
            default_timeout=DEFAULT_TIMEOUT,
            limits=limits,
            default_limits=DEFAULT_LIMITS,
            verify=verify,
            default_headers=DEFAULT_HEADERS,
            user_agent=user_agent,
            default_user_agent=DEFAULT_USER_AGENT,
            follow_redirects=True,
        )
        self.retries = retries

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> SZSEAnnouncementClient:
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.close()

    def query_announcements(
        self,
        *,
        searchkey: str | None = None,
        start_date: date | str,
        end_date: date | str,
        stock: str | None = None,
        limit: int | None = None,
    ) -> AnnouncementQueryResult:
        normalized_searchkey = (searchkey or "").strip()
        normalized_stock = (stock or "").strip()
        if not normalized_searchkey and not normalized_stock:
            raise ValueError("searchkey and stock cannot both be empty")
        if limit is not None and limit <= 0:
            raise ValueError("limit must be greater than 0")

        start = self._parse_date(start_date)
        end = self._parse_date(end_date)
        if start > end:
            raise ValueError("start_date cannot be after end_date")

        page_num = 1
        raw_responses: list[SZSEAnnouncementQueryResponse] = []
        announcements: list[SZSEAnnouncementRecord] = []
        seen_ids: set[str] = set()
        has_more = False

        while True:
            response = self._post_with_retry(
                QUERY_URL,
                data=self._build_query_payload(
                    searchkey=normalized_searchkey,
                    stock=normalized_stock,
                    start_date=start,
                    end_date=end,
                    page_num=page_num,
                ),
                parse=lambda raw: SZSEAnnouncementQueryResponse.model_validate(raw),
            )
            raw_responses.append(response)
            page_selected_count = 0
            for item in response.data:
                announcement_id = build_announcement_id(item)
                if announcement_id in seen_ids:
                    continue
                seen_ids.add(announcement_id)
                announcements.append(item)
                page_selected_count += 1
                if limit is not None and len(announcements) >= limit:
                    break

            has_more = response.announceCount > page_num * PAGE_SIZE
            if limit is not None and len(announcements) >= limit:
                # limit 命中时如果当前页或后续页还有数据，要明确告诉调用方结果被截断了。
                has_more = has_more or page_selected_count < len(response.data)
                break
            if not has_more or not response.data:
                break
            sleep(INTER_PAGE_DELAY_SECONDS)
            page_num += 1

        if limit is not None:
            announcements = announcements[:limit]
        items = [self._to_business_announcement(item) for item in announcements]
        return AnnouncementQueryResult(
            source=AnnouncementSource.SZSE,
            response=AnnouncementQueryResponse(
                source=AnnouncementSource.SZSE,
                total_announcement=len(announcements),
                announcements=announcements,
                raw_responses=raw_responses,
                has_more=has_more,
            ),
            items=items,
        )

    def build_pdf_url(self, announcement: AnnouncementWithPdf) -> str:
        return build_announcement_pdf_url(announcement)

    def download_pdf(
        self,
        announcement: AnnouncementWithPdf,
        *,
        save_dir: str | Path | None = None,
    ) -> Path:
        return _download_pdf_with_client(
            self._client,
            announcement,
            save_dir=save_dir,
        )

    def _build_query_payload(
        self,
        *,
        searchkey: str,
        stock: str,
        start_date: date,
        end_date: date,
        page_num: int,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "seDate": [start_date.isoformat(), end_date.isoformat()],
            "channelCode": [CHANNEL_CODE],
            "pageSize": PAGE_SIZE,
            "pageNum": page_num,
        }
        if searchkey:
            payload["searchKey"] = [searchkey]
        if stock:
            payload["stock"] = [stock]
        return payload

    def _post_with_retry(
        self,
        url: str,
        *,
        data: dict[str, Any],
        parse: Callable[[Any], T],
    ) -> T:
        attempts = self.retries + 1
        last_error: Exception | None = None
        retry_after: str | None = None
        for attempt in range(attempts):
            retry_after = None
            try:
                response = self._client.post(
                    url,
                    params={"random": f"{random.random():.16f}"},
                    content=json.dumps(data, ensure_ascii=False).encode("utf-8"),
                )
                if should_retry_status(response.status_code):
                    retry_after = response.headers.get("Retry-After")
                    raise SZSEAnnouncementError(
                        f"SZSE request failed with status {response.status_code}"
                    )
                response.raise_for_status()
                return parse(_decode_query_json(response))
            except (
                httpx.TimeoutException,
                httpx.NetworkError,
                httpx.ProtocolError,
            ) as exc:
                last_error = exc
            except SZSEAnnouncementError as exc:
                last_error = exc
            if attempt < attempts - 1:
                sleep(retry_delay_seconds(attempt, retry_after))
        if last_error is None:
            raise SZSEAnnouncementError("SZSE request failed")
        raise SZSEAnnouncementError("SZSE request failed after retries") from last_error

    def _to_business_announcement(
        self,
        item: SZSEAnnouncementRecord,
    ) -> BusinessAnnouncement:
        return BusinessAnnouncement(
            source=AnnouncementSource.SZSE,
            sec_code=",".join(item.secCode) or None,
            sec_name=",".join(item.secName) or None,
            org_id=_build_org_id(item),
            announcement_id=build_announcement_id(item),
            announcement_title=item.title,
            announcement_time=_szse_datetime_to_timestamp_ms(item.publishTime),
            adjunct_url=item.attachPath,
            page_column=CHANNEL_CODE,
        )

    def _parse_date(self, value: date | str) -> date:
        if isinstance(value, date):
            return value
        return date.fromisoformat(value)


def query_announcements(
    *,
    searchkey: str | None = None,
    start_date: date | str,
    end_date: date | str,
    stock: str | None = None,
    limit: int | None = None,
) -> AnnouncementQueryResult:
    with SZSEAnnouncementClient() as client:
        return client.query_announcements(
            searchkey=searchkey,
            start_date=start_date,
            end_date=end_date,
            stock=stock,
            limit=limit,
        )


def _decode_query_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise SZSEUnexpectedResponseError("SZSE returned non-JSON data") from exc


def _build_pdf_headers(client: httpx.Client) -> dict[str, str]:
    return build_headers_with_user_agent(
        PDF_HEADERS,
        user_agent=client.headers.get("User-Agent"),
        default_user_agent=DEFAULT_USER_AGENT,
    )


def _build_org_id(item: SZSEAnnouncementRecord) -> str | None:
    # 深交所响应里的 id 是公告记录 UUID，不是公司 ID；接口没有返回公司 orgId。
    # 这里用官方源前缀 + 主证券代码派生稳定业务标识，避免把公告 ID 误当公司标识。
    if not item.secCode:
        return None
    return f"szse{item.secCode[0]}"


def _szse_datetime_to_timestamp_ms(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        # 深交所返回的是无时区的中国市场发布时间，需按 UTC+8 转为 epoch ms。
        announcement_datetime = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=CHINA_TIMEZONE
        )
    except ValueError:
        announcement_datetime = datetime.combine(
            date.fromisoformat(value),
            datetime.min.time(),
            tzinfo=CHINA_TIMEZONE,
        )
    return int(announcement_datetime.timestamp() * 1000)


if __name__ == "__main__":
    today = date.today()
    start = today - timedelta(days=7)
    result = query_announcements(
        searchkey="增持",
        start_date=start,
        end_date=today,
        limit=10,
    )
    print(f"total_announcement={result.response.total_announcement}")
    if result.items:
        for item in result.items:
            print(item.model_dump())
