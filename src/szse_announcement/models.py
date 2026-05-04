from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from announcement_common.models import (
    AnnouncementSource as AnnouncementSource,
    BusinessAnnouncement as BusinessAnnouncement,
    StandardAnnouncementQueryResponse,
    StandardAnnouncementQueryResult,
)


class SZSEAnnouncementRecord(BaseModel):
    """深交所公告查询接口 `data` 数组中的单条公告。"""

    # 保留深交所原始字段名，方便排查接口变化；标准业务字段在 client 中统一转换。
    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    annId: int | str | None = None
    title: str | None = None
    content: str | None = None
    publishTime: str | None = None
    attachPath: str | None = None
    attachFormat: str | None = None
    attachSize: int | None = None
    secCode: list[str] = Field(default_factory=list)
    secName: list[str] = Field(default_factory=list)
    bondType: str | None = None
    bigIndustryCode: str | None = None
    bigCategoryId: str | None = None
    smallCategoryId: str | None = None
    channelCode: str | None = None

    @field_validator("secCode", "secName", mode="before")
    @classmethod
    def _normalize_string_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [str(item) for item in value if item is not None]
        return [str(value)]


class SZSEAnnouncementQueryResponse(BaseModel):
    """深交所公告查询接口的原始响应。"""

    model_config = ConfigDict(extra="ignore")

    announceCount: int = 0
    data: list[SZSEAnnouncementRecord] = Field(default_factory=list)

    @field_validator("data", mode="before")
    @classmethod
    def _normalize_data(cls, value: Any) -> list[Any]:
        # 深交所无结果时返回空数组；这里兼容 null，避免接口偶发空值打断查询链路。
        if value is None:
            return []
        return value


def build_announcement_id(item: SZSEAnnouncementRecord) -> str:
    if item.annId is not None:
        return str(item.annId)
    if item.id:
        return item.id
    url_stem = Path((item.attachPath or "").strip()).stem
    if url_stem:
        return url_stem
    raise ValueError("SZSE announcement is missing annId, id, and attachPath")


AnnouncementQueryResponse = StandardAnnouncementQueryResponse[
    SZSEAnnouncementRecord,
    SZSEAnnouncementQueryResponse,
]
AnnouncementQueryResult = StandardAnnouncementQueryResult[AnnouncementQueryResponse]
