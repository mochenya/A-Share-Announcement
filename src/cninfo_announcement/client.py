from __future__ import annotations

import re
import sys
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from time import sleep
from typing import Any, Literal, TypeVar

if __package__ in (None, ""):
    # 允许 `uv run path/to/client.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from announcement_common.http import (
    VerifyTypes,
    create_http_client,
    retry_delay_seconds,
    should_retry_status,
)
from announcement_common.models import AnnouncementSource
from cninfo_announcement.config import (
    DEFAULT_INTER_PAGE_DELAY_SECONDS,
    DEFAULT_LIMITS,
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT,
    DEFAULT_USER_AGENT,
)
from cninfo_announcement.models import (
    AnnouncementQueryResponse,
    AnnouncementQueryResult,
    AnnouncementRecord,
    BusinessAnnouncement,
    CNInfoAnnouncementQueryResponse,
    TopSearchResult,
)
from cninfo_announcement.pdf import (
    AnnouncementWithPdf,
    _download_pdf_with_client,
    build_pdf_url as build_announcement_pdf_url,
)

Market = Literal["sh", "sz", "bj", "hk"]

ANNOUNCEMENT_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
TOP_SEARCH_URL = "https://www.cninfo.com.cn/new/information/topSearch/query"
DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin": "https://www.cninfo.com.cn",
    "Referer": "https://www.cninfo.com.cn/",
    "User-Agent": DEFAULT_USER_AGENT,
    "X-Requested-With": "XMLHttpRequest",
}
TAG_RE = re.compile(r"</?em>")
# 公告查询接口的市场映射：A 股统一走 szse，再由 plate 区分板块；港股单独走 hke。
MARKET_COLUMN_MAP: dict[Market, tuple[str, str]] = {
    "sh": ("szse", "sh"),
    "sz": ("szse", "sz"),
    "bj": ("szse", "bj"),
    "hk": ("hke", ""),
}
# stock 代码解析走 topSearch，A 股需要用 szsh，港股用 hke。
# 这里不要和公告查询的 column/plate 混用：topSearch 是另一套上游约定。
TOP_SEARCH_PLATE_MAP: dict[Market, str] = {
    "sh": "szsh",
    "sz": "szsh",
    "bj": "szsh",
    "hk": "hke",
}
T = TypeVar("T")


class CNInfoError(Exception):
    pass


class CNInfoClient:
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
        )
        self.retries = retries

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> CNInfoClient:
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.close()

    def query_announcements(
        self,
        market: Market,
        *,
        searchkey: str | None = None,
        stock: str | None = None,
        start_date: date | str,
        end_date: date | str,
    ) -> AnnouncementQueryResult:
        normalized_searchkey = (searchkey or "").strip()
        normalized_stock = (stock or "").strip()
        if not normalized_searchkey and not normalized_stock:
            raise ValueError("searchkey and stock cannot both be empty")

        start = self._parse_date(start_date)
        end = self._parse_date(end_date)
        if start > end:
            raise ValueError("start_date cannot be after end_date")

        resolved_stock = (
            self._resolve_stock(market, normalized_stock) if normalized_stock else ""
        )
        page_num = 1
        all_announcements: list[AnnouncementRecord] = []
        raw_responses: list[CNInfoAnnouncementQueryResponse] = []

        while True:
            payload = self._build_announcement_payload(
                market=market,
                searchkey=normalized_searchkey,
                stock=resolved_stock,
                start_date=start,
                end_date=end,
                page_num=page_num,
            )
            response = self._post_with_retry(
                ANNOUNCEMENT_URL,
                data=payload,
                parse=lambda raw: CNInfoAnnouncementQueryResponse.model_validate(raw),
            )
            raw_responses.append(response)
            all_announcements.extend(response.announcements)
            if not response.hasMore:
                break
            # 实测 totalpages 可能偏小，分页是否结束以 hasMore 为准；
            # 这里也兼容上游偶发返回空页的情况，避免死循环。
            if not response.announcements:
                break
            if (
                response.totalAnnouncement
                and len(all_announcements) >= response.totalAnnouncement
            ):
                break
            sleep(DEFAULT_INTER_PAGE_DELAY_SECONDS)
            page_num += 1

        if not raw_responses:
            raise CNInfoError("CNInfo query returned no response")

        items = [self._to_business_announcement(item) for item in all_announcements]
        standard_response = AnnouncementQueryResponse(
            source=AnnouncementSource.CNINFO,
            total_announcement=len(all_announcements),
            announcements=all_announcements,
            raw_responses=raw_responses,
            has_more=False,
        )
        return AnnouncementQueryResult(
            source=AnnouncementSource.CNINFO,
            response=standard_response,
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
            retries=self.retries,
        )

    def _build_announcement_payload(
        self,
        *,
        market: Market,
        searchkey: str,
        stock: str,
        start_date: date | str,
        end_date: date | str,
        page_num: int,
    ) -> dict[str, str]:
        column, plate = MARKET_COLUMN_MAP[market]
        return {
            "pageNum": str(page_num),
            "pageSize": "30",
            "column": column,
            "tabName": "fulltext",
            "plate": plate,
            "stock": stock,
            "searchkey": searchkey,
            "secid": "",
            "category": "",
            "trade": "",
            "seDate": self._format_date_range(start_date, end_date),
            "sortName": "",
            "sortType": "",
            "isHLtitle": "true",
        }

    def _resolve_stock(self, market: Market, stock: str) -> str:
        # 巨潮公告接口里的 stock 不是纯代码，而是 code,orgId。
        # 直接把纯代码塞进查询会命中不到记录，所以必须先走 topSearch 解析。
        if not stock:
            return ""
        if "," in stock:
            return stock
        results = self._post_with_retry(
            TOP_SEARCH_URL,
            data={
                "keyWord": stock,
                "maxNum": "10",
                "plate": TOP_SEARCH_PLATE_MAP[market],
            },
            parse=lambda raw: [TopSearchResult.model_validate(item) for item in raw],
        )
        exact_matches = [item for item in results if item.code == stock]
        if not exact_matches:
            raise CNInfoError(f"Unable to resolve stock code: {stock}")
        org_ids = {item.orgId for item in exact_matches}
        if len(org_ids) != 1:
            raise CNInfoError(f"Stock code resolved ambiguously: {stock}")
        match = exact_matches[0]
        return f"{match.code},{match.orgId}"

    def _post_with_retry(
        self,
        url: str,
        *,
        data: dict[str, str],
        parse: Callable[[Any], T],
    ) -> T:
        attempts = self.retries + 1
        last_error: Exception | None = None
        retry_after: str | None = None
        for attempt in range(attempts):
            retry_after = None
            try:
                response = self._client.post(url, data=data)
                if should_retry_status(response.status_code):
                    retry_after = response.headers.get("Retry-After")
                    raise CNInfoError(
                        f"CNInfo request failed with status {response.status_code}"
                    )
                response.raise_for_status()
                return parse(response.json())
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
            except CNInfoError as exc:
                if attempt == attempts - 1:
                    raise
                last_error = exc
            except httpx.HTTPStatusError:
                raise
            if attempt < attempts - 1:
                sleep(retry_delay_seconds(attempt, retry_after))
        if last_error is None:
            raise CNInfoError("CNInfo request failed")
        raise CNInfoError("CNInfo request failed after retries") from last_error

    def _to_business_announcement(
        self, item: AnnouncementRecord
    ) -> BusinessAnnouncement:
        return BusinessAnnouncement(
            source=AnnouncementSource.CNINFO,
            sec_code=item.secCode,
            sec_name=item.secName,
            org_id=item.orgId,
            announcement_id=item.announcementId,
            announcement_title=self._strip_highlight_tags(item.announcementTitle),
            announcement_time=item.announcementTime,
            adjunct_url=item.adjunctUrl,
            page_column=item.pageColumn,
        )

    def _format_date_range(self, start_date: date | str, end_date: date | str) -> str:
        return f"{self._format_date(start_date)}~{self._format_date(end_date)}"

    def _format_date(self, value: date | str) -> str:
        if isinstance(value, date):
            return value.isoformat()
        return value

    def _parse_date(self, value: date | str) -> date:
        if isinstance(value, date):
            return value
        return date.fromisoformat(value)

    def _strip_highlight_tags(self, value: str | None) -> str | None:
        # 只去掉标题中的 <em> 高亮标签，不做其他 HTML 清洗。
        # 上游其他文本有时会包含业务可见信息，过度清洗会误伤原始标题语义。
        if value is None:
            return None
        return TAG_RE.sub("", value)


def query_announcements(
    market: Market,
    *,
    searchkey: str | None = None,
    stock: str | None = None,
    start_date: date | str,
    end_date: date | str,
) -> AnnouncementQueryResult:
    with CNInfoClient() as client:
        return client.query_announcements(
            market,
            searchkey=searchkey,
            stock=stock,
            start_date=start_date,
            end_date=end_date,
        )


if __name__ == "__main__":
    today = date.today()
    start = today - timedelta(days=7)
    result = query_announcements(
        "hk",
        searchkey="增持",
        start_date=start,
        end_date=today,
    )
    print(f"total_announcement={result.response.total_announcement}")
    if result.items:
        for item in result.items:
            print(item.model_dump())
