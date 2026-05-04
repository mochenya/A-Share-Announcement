from __future__ import annotations

from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

TAnnouncement = TypeVar("TAnnouncement")
TRawResponse = TypeVar("TRawResponse")
TResponse = TypeVar("TResponse")


class AnnouncementSource(StrEnum):
    CNINFO = "cninfo"
    SSE = "sse"
    SZSE = "szse"


class BusinessAnnouncement(BaseModel):
    """公告源统一后的业务字段对象。"""

    model_config = ConfigDict(validate_by_name=True, validate_by_alias=True)

    source: AnnouncementSource  # 公告源标识。
    sec_code: str | None = Field(default=None, alias="secCode")  # 证券代码。
    sec_name: str | None = Field(default=None, alias="secName")  # 证券简称。
    org_id: str | None = Field(default=None, alias="orgId")  # 上游机构或公告分组标识。
    announcement_id: str | None = Field(
        default=None,
        alias="announcementId",
    )  # 稳定公告 ID，可由上游字段或文件路径派生。
    announcement_title: str | None = Field(
        default=None,
        alias="announcementTitle",
    )  # 业务侧标题。
    announcement_time: int | None = Field(
        default=None,
        alias="announcementTime",
    )  # 公告时间，毫秒时间戳。
    adjunct_url: str | None = Field(default=None, alias="adjunctUrl")  # PDF 相对路径。
    page_column: str | None = Field(
        default=None,
        alias="pageColumn",
    )  # 上游页面栏目；没有对应字段的公告源保持为空。


class StandardAnnouncementQueryResponse(
    BaseModel,
    Generic[TAnnouncement, TRawResponse],
):
    """公告源统一后的标准查询响应。"""

    model_config = ConfigDict(validate_by_name=True, validate_by_alias=True)

    source: AnnouncementSource
    total_announcement: int = Field(default=0, alias="totalAnnouncement")
    announcements: list[TAnnouncement] = Field(default_factory=list)
    raw_responses: list[TRawResponse] = Field(
        default_factory=list, alias="rawResponses"
    )
    has_more: bool = Field(default=False, alias="hasMore")


class StandardAnnouncementQueryResult(BaseModel, Generic[TResponse]):
    """公告源统一后的标准查询结果。"""

    source: AnnouncementSource
    response: TResponse
    items: list[BusinessAnnouncement]
