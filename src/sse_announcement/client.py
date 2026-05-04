from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from time import sleep
from typing import Any, TypeVar

if __package__ in (None, ""):
    # 允许 `uv run path/to/client.py`
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
from announcement_common.pdf import is_pdf_response
from sse_announcement.config import (
    DEFAULT_LIMITS,
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT,
    DEFAULT_USER_AGENT,
)
from sse_announcement.models import (
    AnnouncementQueryResponse,
    AnnouncementQueryResult,
    BusinessAnnouncement,
    SSEBulletinFile,
    SSEBulletinQueryResponse,
    build_announcement_id,
)
from sse_announcement.pdf import (
    AnnouncementWithPdf,
    _download_pdf_with_client,
    build_pdf_url as build_announcement_pdf_url,
)

QUERY_URL = "https://query.sse.com.cn/security/stock/queryCompanyBulletinNew.do"
# 上交所查询接口会校验 Referer/User-Agent；缺少这些浏览器头时容易返回空数据
# 或挑战页，所以这里固定使用网页端同源请求头。这个约定最好保持稳定，
# 否则本地烟测可能过、线上回抓却失败。
DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.sse.com.cn/",
    "User-Agent": DEFAULT_USER_AGENT,
}
# PDF 走 static.sse.com.cn，Accept 单独偏向二进制，避免服务端按普通页面返回。
PDF_HEADERS = {
    "Accept": "application/pdf,application/octet-stream,*/*",
    "Referer": "https://www.sse.com.cn/",
    "User-Agent": DEFAULT_USER_AGENT,
}
MAX_KEYWORD_ONLY_DAYS = 90
PAGE_SIZE = 100
# static.sse.com.cn 的 PDF 偶尔先返回一段 JavaScript 挑战页，需要从 arg1
# 计算 acw_sc__v2 cookie 后再取 PDF。下面的位置表和 mask 来自网页端算法。
# 这段逻辑保持纯 Python，是为了避免引入浏览器自动化或 JS 执行依赖。
ACW_COOKIE_RE = re.compile(r"arg1='([^']+)'")
ACW_POSITIONS = [
    0xF,
    0x23,
    0x1D,
    0x18,
    0x21,
    0x10,
    0x1,
    0x26,
    0xA,
    0x9,
    0x13,
    0x1F,
    0x28,
    0x1B,
    0x16,
    0x17,
    0x19,
    0xD,
    0x6,
    0xB,
    0x27,
    0x12,
    0x14,
    0x8,
    0xE,
    0x15,
    0x20,
    0x1A,
    0x2,
    0x1E,
    0x7,
    0x4,
    0x11,
    0x5,
    0x3,
    0x1C,
    0x22,
    0x25,
    0xC,
    0x24,
]
ACW_MASK = "3000176000856006061501533003690027800375"
T = TypeVar("T")


class SSEAnnouncementError(Exception):
    pass


class SSERateLimitError(SSEAnnouncementError):
    pass


class SSEChallengeError(SSEAnnouncementError):
    pass


class SSEUnexpectedResponseError(SSEAnnouncementError):
    pass


class SSEAnnouncementClient:
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

    def __enter__(self) -> SSEAnnouncementClient:
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
        include_attachments: bool = False,
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

        raw_responses: list[SSEBulletinQueryResponse] = []
        selected_files: list[SSEBulletinFile] = []
        seen_ids: set[str] = set()
        truncated = False
        # 关键词全市场查询必须先拆窗：上交所超过跨度后不会显式报错，只会返回空页。
        # 这里把窗口列表实体化，是为了 limit 早停时还能判断后面是否还有未查窗口，
        # 从而正确标记 hasMore。
        windows = list(
            self._iter_query_windows(
                start,
                end,
                keyword_only=not normalized_stock,
            )
        )
        for window_index, (chunk_start, chunk_end) in enumerate(windows):
            for response in self._iter_window_responses(
                searchkey=normalized_searchkey,
                start_date=chunk_start,
                end_date=chunk_end,
                stock=normalized_stock or None,
            ):
                raw_responses.append(response)
                for group in response.result:
                    for item in self._select_group_files(
                        group,
                        include_attachments=include_attachments,
                    ):
                        announcement_id = build_announcement_id(item)
                        if announcement_id in seen_ids:
                            continue
                        seen_ids.add(announcement_id)
                        selected_files.append(item)
                if limit is None:
                    continue
                if len(selected_files) < limit:
                    continue
                # 正式 workflow 里“回购”这类宽关键词可能一次命中上千条。limit 达到
                # 后就停止继续请求，控制同步/LLM/投递成本；同时保留 hasMore，避免
                # 调用方把截断结果误判成完整结果。
                truncated = (
                    self._response_has_more_pages(response)
                    or window_index < len(windows) - 1
                )
                break
            if truncated:
                break

        has_more = truncated or (limit is not None and len(selected_files) > limit)
        if limit is not None:
            selected_files = selected_files[:limit]
        items = [self._to_business_announcement(item) for item in selected_files]
        return AnnouncementQueryResult(
            source=AnnouncementSource.SSE,
            response=AnnouncementQueryResponse(
                source=AnnouncementSource.SSE,
                total_announcement=len(selected_files),
                announcements=selected_files,
                raw_responses=raw_responses,
                has_more=has_more,
            ),
            items=items,
        )

    def _iter_window_responses(
        self,
        *,
        searchkey: str,
        start_date: date,
        end_date: date,
        stock: str | None,
    ):
        page_no = 1
        while True:
            params = self._build_query_params(
                searchkey=searchkey,
                start_date=start_date,
                end_date=end_date,
                stock=stock,
                page_no=page_no,
            )
            response = self._get_with_retry(
                QUERY_URL,
                params=params,
                parse=lambda raw: SSEBulletinQueryResponse.model_validate(raw),
            )
            yield response
            # pageHelp.total 只适合做诊断，不适合作为翻页终止条件；后续如果加客户端
            # 过滤或上游字段口径变化，按 total 反推容易漏页。实测网页端契约是
            # pageNo/pageCount，所以这里跟随页码。
            if not self._response_has_more_pages(response):
                break
            page_no += 1

    def _response_has_more_pages(self, response: SSEBulletinQueryResponse) -> bool:
        page_count = response.pageHelp.pageCount or 0
        return bool(response.result) and response.pageHelp.pageNo < page_count

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

    def _build_query_params(
        self,
        *,
        searchkey: str,
        start_date: date,
        end_date: date,
        stock: str | None,
        page_no: int,
    ) -> dict[str, str]:
        params = {
            "START_DATE": start_date.isoformat(),
            "END_DATE": end_date.isoformat(),
            "TITLE": searchkey,
            "isPagination": "true",
            "pageHelp.pageNo": str(page_no),
            "pageHelp.pageSize": str(PAGE_SIZE),
            "pageHelp.beginPage": str(page_no),
            "pageHelp.cacheSize": "1",
        }
        if stock:
            params["SECURITY_CODE"] = stock
        return params

    def _get_with_retry(
        self,
        url: str,
        *,
        params: dict[str, str],
        parse: Callable[[Any], T],
    ) -> T:
        attempts = self.retries + 1
        last_error: Exception | None = None
        retry_after: str | None = None
        for attempt in range(attempts):
            retry_after = None
            try:
                response = self._client.get(url, params=params)
                if should_retry_status(response.status_code):
                    retry_after = response.headers.get("Retry-After")
                    raise SSERateLimitError(
                        f"SSE request failed with status {response.status_code}"
                    )
                response.raise_for_status()
                return parse(_decode_query_json(response))
            except (
                httpx.TimeoutException,
                httpx.NetworkError,
                httpx.ProtocolError,
            ) as exc:
                last_error = exc
            except SSERateLimitError as exc:
                last_error = exc
            if attempt < attempts - 1:
                sleep(retry_delay_seconds(attempt, retry_after))
        if last_error is None:
            raise SSEAnnouncementError("SSE request failed")
        raise SSEAnnouncementError("SSE request failed after retries") from last_error

    def _iter_query_windows(
        self,
        start_date: date,
        end_date: date,
        *,
        keyword_only: bool,
    ):
        if not keyword_only:
            yield start_date, end_date
            return

        current_start = start_date
        while current_start <= end_date:
            # 这里的日期范围首尾都包含，所以要减 1 天；否则 2 月 1 日到 5 月 1 日
            # 会被算成 91 个自然日，刚好踩到上交所关键词查询的隐藏限制。
            current_end = min(
                current_start + timedelta(days=MAX_KEYWORD_ONLY_DAYS - 1),
                end_date,
            )
            yield current_start, current_end
            current_start = current_end + timedelta(days=1)

    def _select_group_files(
        self,
        group: list[SSEBulletinFile],
        *,
        include_attachments: bool,
    ) -> list[SSEBulletinFile]:
        if include_attachments:
            return list(group)
        # 上交所把正文和附件放在同一个 ORG_BULLETIN_ID 分组里。workflow 默认只处理
        # 正文 PDF；如果正文不是唯一的，说明上游结构变了，宁可抛错也不要误把附件
        # 送去摘要。
        main_files = [item for item in group if item.ORG_FILE_TYPE == 0]
        if len(main_files) != 1:
            raise SSEUnexpectedResponseError(
                "SSE bulletin group did not contain exactly one main file"
            )
        return main_files

    def _to_business_announcement(self, item: SSEBulletinFile) -> BusinessAnnouncement:
        return BusinessAnnouncement(
            source=AnnouncementSource.SSE,
            sec_code=item.SECURITY_CODE,
            sec_name=item.SECURITY_NAME,
            org_id=item.ORG_BULLETIN_ID,
            announcement_id=build_announcement_id(item),
            announcement_title=item.TITLE,
            announcement_time=_sse_date_to_timestamp_ms(item.SSEDATE),
            adjunct_url=item.URL,
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
    include_attachments: bool = False,
    limit: int | None = None,
) -> AnnouncementQueryResult:
    with SSEAnnouncementClient() as client:
        return client.query_announcements(
            searchkey=searchkey,
            start_date=start_date,
            end_date=end_date,
            stock=stock,
            include_attachments=include_attachments,
            limit=limit,
        )


def _decode_query_json(response: httpx.Response) -> Any:
    text = response.text.strip()
    if text.startswith("("):
        # 被风控或参数异常命中时，接口可能返回 "(...)" 包裹的错误对象，而不是正常
        # JSON。这里先识别这种形态，避免 Pydantic 抛出和真实原因无关的字段错误。
        try:
            payload = json.loads(text.strip("()"))
        except json.JSONDecodeError as exc:
            raise SSEUnexpectedResponseError(
                "SSE returned wrapped non-JSON data"
            ) from exc
        error = payload.get("error") or payload.get("errorType") or payload
        raise SSERateLimitError(f"SSE returned an error response: {error}")
    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise SSEUnexpectedResponseError("SSE returned non-JSON data") from exc


def _get_pdf_response(
    client: httpx.Client,
    url: str,
    *,
    retries: int = DEFAULT_RETRIES,
) -> httpx.Response:
    attempts = retries + 1
    last_error: Exception | None = None
    retry_after: str | None = None
    for attempt in range(attempts):
        retry_after = None
        try:
            return _get_pdf_response_once(client, url)
        except (
            httpx.TimeoutException,
            httpx.NetworkError,
            httpx.ProtocolError,
        ) as exc:
            last_error = exc
        except SSERateLimitError as exc:
            retry_after = _extract_retry_after(exc)
            last_error = exc
        if attempt < attempts - 1:
            sleep(retry_delay_seconds(attempt, retry_after))
    if last_error is None:
        raise SSEAnnouncementError("SSE PDF request failed")
    raise SSEAnnouncementError("SSE PDF request failed after retries") from last_error


def _get_pdf_response_once(client: httpx.Client, url: str) -> httpx.Response:
    response = client.get(url, headers=_build_pdf_headers(client))
    if is_pdf_response(response):
        return response
    _raise_for_retryable_pdf_status(response)
    # PDF 首次请求可能返回挑战页；解出 acw_sc__v2 后必须用同一个 client 保留
    # cookie 再请求一次。
    _solve_acw_challenge(client, response)
    response = client.get(url, headers=_build_pdf_headers(client))
    if is_pdf_response(response):
        return response
    _raise_for_retryable_pdf_status(response)
    content_type = response.headers.get("content-type")
    raise SSEUnexpectedResponseError(
        f"SSE PDF request did not return a PDF: {content_type}"
    )


def _is_pdf_response(response: httpx.Response) -> bool:
    return is_pdf_response(response)


def _raise_for_retryable_pdf_status(response: httpx.Response) -> None:
    if not should_retry_status(response.status_code):
        response.raise_for_status()
        return
    error = SSERateLimitError(
        f"SSE PDF request failed with status {response.status_code}"
    )
    error.retry_after = response.headers.get("Retry-After")
    raise error


def _extract_retry_after(error: SSERateLimitError) -> str | None:
    return getattr(error, "retry_after", None)


def _build_pdf_headers(client: httpx.Client) -> dict[str, str]:
    return build_headers_with_user_agent(
        PDF_HEADERS,
        user_agent=client.headers.get("User-Agent"),
        default_user_agent=DEFAULT_USER_AGENT,
    )


def _solve_acw_challenge(client: httpx.Client, response: httpx.Response) -> None:
    match = ACW_COOKIE_RE.search(response.text)
    if match is None:
        raise SSEChallengeError("SSE PDF challenge did not include arg1")
    cookie_value = _calculate_acw_sc_v2(match.group(1))
    client.cookies.set("acw_sc__v2", cookie_value, domain=".sse.com.cn", path="/")
    client.cookies.set(
        "acw_sc__v2",
        cookie_value,
        domain="static.sse.com.cn",
        path="/",
    )


def _calculate_acw_sc_v2(arg1: str) -> str:
    output = [""] * len(ACW_POSITIONS)
    for index, char in enumerate(arg1):
        for output_index, position in enumerate(ACW_POSITIONS):
            if position == index + 1:
                output[output_index] = char
    arg2 = "".join(output)
    cookie_value = ""
    for index in range(0, min(len(arg2), len(ACW_MASK)), 2):
        # 网页端算法是按字节做十六进制异或；这里保持同样的字符串运算，避免引入
        # JavaScript 执行依赖。
        value = int(arg2[index : index + 2], 16) ^ int(
            ACW_MASK[index : index + 2],
            16,
        )
        cookie_value += f"{value:02x}"
    return cookie_value


def _sse_date_to_timestamp_ms(value: str | None) -> int | None:
    if value is None:
        return None
    announcement_date = date.fromisoformat(value)
    # SSE 只返回公告日期，没有具体发布时间；统一落到 UTC 零点，保持和
    # BusinessAnnouncement 的毫秒时间戳字段兼容。
    timestamp = datetime.combine(
        announcement_date,
        datetime.min.time(),
        tzinfo=UTC,
    ).timestamp()
    return int(timestamp * 1000)


if __name__ == "__main__":
    today = date.today()
    start = today - timedelta(days=7)
    result = query_announcements(
        searchkey="减持",
        start_date=start,
        end_date=today,
        limit=10,
    )
    print(f"total_announcement={result.response.total_announcement}")
    if result.items:
        for item in result.items:
            print(item.model_dump())
