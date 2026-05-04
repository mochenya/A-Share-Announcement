from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from announcement_common.models import (
    AnnouncementSource as AnnouncementSource,
    BusinessAnnouncement as BusinessAnnouncement,
    StandardAnnouncementQueryResponse,
    StandardAnnouncementQueryResult,
)


# 保留巨潮原始字段名，方便完整响应 model 直接映射上游返回结构。
class AnnouncementRecord(BaseModel):
    """巨潮接口 `announcements` 数组中的单条公告对象。"""

    model_config = ConfigDict(extra="ignore")

    id: str | None = None  # 公告记录 ID，实测通常为 null。
    secCode: str | None = None  # 证券代码。
    secName: str | None = None  # 证券简称。
    orgId: str | None = None  # 巨潮内部证券/机构标识，stock 查询拼装时会用到。
    announcementId: str | None = None  # 公告唯一 ID。
    announcementTitle: str | None = None  # 原始公告标题，可能包含 <em> 高亮标签。
    announcementTime: int | None = None  # 公告时间，毫秒时间戳。
    adjunctUrl: str | None = None  # 附件相对路径，通常指向 PDF。
    adjunctSize: int | None = None  # 附件大小。
    adjunctType: str | None = None  # 附件类型，如 PDF。
    storageTime: str | None = None  # 存储时间，实测通常为 null。
    columnId: str | None = None  # 巨潮栏目 ID 组合串。
    pageColumn: str | None = None  # 页面栏目代码，如 SZCY、HKZB。
    announcementType: str | None = None  # 公告类型 ID 组合串。
    associateAnnouncement: str | None = None  # 关联公告信息，实测通常为 null。
    important: str | None = None  # 是否重要公告，实测通常为 null。
    batchNum: str | None = None  # 批次号，实测通常为 null。
    announcementContent: str | None = None  # 公告正文摘要，当前接口实测常为空字符串。
    orgName: str | None = None  # 机构名称，实测通常为 null。
    tileSecName: str | None = None  # 标题中展示用证券简称。
    shortTitle: str | None = None  # 短标题，可能包含 <em> 高亮标签。
    announcementTypeName: str | None = None  # 公告类型名称，实测通常为 null。
    secNameList: list[Any] | None = None  # 证券名称列表，实测通常为 null。


class CNInfoAnnouncementQueryResponse(BaseModel):
    """巨潮公告查询接口的完整响应对象。"""

    model_config = ConfigDict(extra="ignore")

    classifiedAnnouncements: list[Any] | None = (
        None  # 按分类聚合的公告结构，当前场景未使用。
    )
    totalSecurities: int = 0  # 命中的证券数量。
    totalAnnouncement: int = 0  # 命中的公告总数。
    totalRecordNum: int = 0  # 命中的记录总数。
    announcements: list[AnnouncementRecord] = Field(
        default_factory=list
    )  # 当前页公告列表。
    categoryList: list[Any] | None = None  # 分类列表，当前场景未使用。
    hasMore: bool = False  # 是否还有下一页数据。
    totalpages: int = 0  # 总页数。

    @field_validator(
        "classifiedAnnouncements", "announcements", "categoryList", mode="before"
    )
    @classmethod
    def _normalize_list_fields(cls, value: Any) -> Any:
        # 巨潮无结果时可能返回 null，这里统一折叠为空列表。
        if value is None:
            return []
        return value


AnnouncementQueryResponse = StandardAnnouncementQueryResponse[
    AnnouncementRecord,
    CNInfoAnnouncementQueryResponse,
]
AnnouncementQueryResult = StandardAnnouncementQueryResult[AnnouncementQueryResponse]


# topSearch 结果只用于把简化 stock 代码解析成 code,orgId。
class TopSearchResult(BaseModel):
    """巨潮 topSearch 接口返回的单条证券搜索结果对象。"""

    model_config = ConfigDict(extra="ignore")

    code: str  # 证券代码。
    orgId: str  # 巨潮内部证券/机构标识。
    pinyin: str | None = None  # 拼音缩写。
    sjstsBond: str | None = None  # 是否债券相关标识。
    category: str | None = None  # 证券类别，如 A 股、港股。
    type: str | None = None  # 搜索结果类型。
    delisted: str | None = None  # 是否已退市。
    zwjc: str | None = None  # 中文简称。
