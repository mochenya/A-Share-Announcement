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


class SSEPageHelp(BaseModel):
    """上交所公告查询接口的分页元数据。"""

    # 上交所响应字段会随页面功能增加而变化，客户端只固定 workflow 需要的字段；
    # extra=ignore 可以避免上游新增字段时把查询链路打断。
    model_config = ConfigDict(extra="ignore")

    total: int = 0
    pageCount: int | None = None
    pageNo: int = 1
    pageSize: int = 10


class SSEBulletinFile(BaseModel):
    """上交所接口 `result` 分组中的单个正文或附件文件。"""

    # 字段名保持上交所原始大写格式，便于和抓包响应一一对应；转换成 workflow
    # 业务字段的逻辑集中放在 client._to_business_announcement。
    model_config = ConfigDict(extra="ignore")

    BULLETIN_TYPE_DESC: str | None = None  # 公告类型描述，如股东会、其他。
    BULLETIN_YEAR: str | None = None  # 公告年份。
    IS_HOLDER_DISCLOSE: str | None = None  # 是否持有人披露相关标识。
    ORG_BULLETIN_ID: str | None = None  # 上游公告分组 ID，正文和附件通常共享。
    ORG_FILE_TYPE: int | None = None  # 文件类型，0 通常为正文，1 通常为附件。
    SECURITY_CODE: str | None = None  # 证券代码。
    SECURITY_NAME: str | None = None  # 证券简称。
    SSEDATE: str | None = None  # 公告日期，格式为 YYYY-MM-DD。
    TITLE: str | None = None  # 文件标题。
    URL: str | None = None  # PDF 相对路径。


def build_announcement_id(item: SSEBulletinFile) -> str:
    url_stem = Path((item.URL or "").strip()).stem
    if not url_stem:
        raise ValueError("SSE bulletin is missing URL")
    # SSE 没有官方公告 ID；PDF 文件名是实际资源身份，去掉分隔符后生成短而稳定的业务 ID。
    return f"sse{url_stem.replace('_', '')}"


class SSEBulletinQueryResponse(BaseModel):
    """上交所公告查询接口的官方响应模型。"""

    # 这是官方响应，不是对外标准响应；标准响应由下面的 AnnouncementQueryResponse
    # 类型别名绑定到 announcement_common.StandardAnnouncementQueryResponse。
    model_config = ConfigDict(extra="ignore")

    START_DATE: str | None = None  # 查询开始日期。
    END_DATE: str | None = None  # 查询结束日期。
    SECURITY_CODE: str | None = None  # 查询条件中的证券代码。
    TITLE: str | None = None  # 查询条件中的标题关键词。
    keyWord: str | None = None  # 上游保留字段，实测常为空。
    pageHelp: SSEPageHelp = Field(default_factory=SSEPageHelp)
    result: list[list[SSEBulletinFile]] = Field(default_factory=list)

    @field_validator("result", mode="before")
    @classmethod
    def _normalize_result(cls, value: Any) -> list[list[Any]]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise TypeError("result must be a list")
        normalized: list[list[Any]] = []
        for item in value:
            # 实测 result 通常是“公告分组列表”，每组里有正文和附件；这里兼容偶发
            # 的单对象形态，统一成 list[list[file]]，让后续选择正文/附件的逻辑只
            # 处理一种结构。
            if isinstance(item, list):
                normalized.append(item)
            else:
                normalized.append([item])
        return normalized


# 对外查询结果使用公共标准响应；官方响应保留在 response.raw_responses 中。
AnnouncementQueryResponse = StandardAnnouncementQueryResponse[
    SSEBulletinFile,
    SSEBulletinQueryResponse,
]
AnnouncementQueryResult = StandardAnnouncementQueryResult[AnnouncementQueryResponse]
