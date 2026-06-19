# A-Share Announcement

Typed Python clients for querying A-share announcements from CNInfo, Shanghai
Stock Exchange, and Shenzhen Stock Exchange.

这个仓库把巨潮资讯、上交所、深交所的公告查询和 PDF 下载能力整理成三个独立
provider 包，并提供统一的业务字段模型，方便后续做公告同步、筛选、摘要、归档
或投递。

[![Python](https://img.shields.io/badge/python-3.14%2B-blue.svg)](https://www.python.org/)
[![Typed](https://img.shields.io/badge/typed-py.typed-brightgreen.svg)](https://peps.python.org/pep-0561/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## Features

- 支持巨潮资讯 `cninfo`、上交所 `sse`、深交所 `szse` 三个公告源。
- 查询结果统一转换为 `BusinessAnnouncement`，同时保留上游原始响应。
- 支持公告 PDF URL 构建和下载，下载前校验真实 PDF 内容，避免保存 HTML 错误页。
- 内置重试、`Retry-After`、连接池、超时、User-Agent 和交易所分页处理。
- 全包 typed，基于 Pydantic v2 模型解析上游响应。
- 测试以 mock 响应为主，不依赖真实交易所请求。

## Packages

| Package | Source | Main client | Notes |
| --- | --- | --- | --- |
| `cninfo_announcement` | 巨潮资讯 | `CNInfoClient` | 支持 A 股、北交所、港股公告查询 |
| `sse_announcement` | 上海证券交易所 | `SSEAnnouncementClient` | 支持长日期关键词查询拆窗、正文/附件选择 |
| `szse_announcement` | 深圳证券交易所 | `SZSEAnnouncementClient` | 支持深交所公告列表查询和 PDF 下载 |
| `announcement_common` | Shared | - | HTTP、PDF、文件名、统一模型等公共逻辑 |

## Installation

当前项目使用 `uv` 管理依赖：

```bash
uv sync --dev
```

作为包安装时，需要 Python 3.14 或更高版本：

```bash
uv pip install .
```

## Quick Start

### CNInfo

```python
from cninfo_announcement import query_announcements, download_pdf

result = query_announcements(
    "sz",
    searchkey="回购",
    start_date="2026-01-01",
    end_date="2026-01-31",
)

for item in result.items:
    print(item.sec_code, item.sec_name, item.announcement_title)

if result.items:
    path = download_pdf(result.items[0], save_dir="data/cninfo_pdf")
    print(path)
```

`CNInfo` 的 `market` 支持：

| Value | Market |
| --- | --- |
| `"sh"` | 沪市 |
| `"sz"` | 深市 |
| `"bj"` | 北交所 |
| `"hk"` | 港股 |

按证券代码查询时，巨潮会先通过 `topSearch` 把纯代码解析为 `code,orgId`：

```python
from cninfo_announcement import CNInfoClient

with CNInfoClient(retries=2) as client:
    result = client.query_announcements(
        "sz",
        stock="000001",
        searchkey="年度报告",
        start_date="2026-01-01",
        end_date="2026-12-31",
    )
```

### SSE

```python
from sse_announcement import query_announcements, download_pdf

result = query_announcements(
    searchkey="股权激励",
    start_date="2026-01-01",
    end_date="2026-03-31",
    limit=20,
)

print(result.response.total_announcement, result.response.has_more)

if result.items:
    path = download_pdf(result.items[0], save_dir="data/sse_pdf")
    print(path)
```

上交所关键词全市场查询存在日期跨度限制，客户端会自动拆分 90 天窗口。默认只返回
公告正文 PDF；如需同时保留附件：

```python
from sse_announcement import SSEAnnouncementClient

with SSEAnnouncementClient() as client:
    result = client.query_announcements(
        searchkey="发行",
        start_date="2026-01-01",
        end_date="2026-01-31",
        include_attachments=True,
    )
```

### SZSE

```python
from szse_announcement import query_announcements, download_pdf

result = query_announcements(
    searchkey="增持",
    start_date="2026-04-01",
    end_date="2026-04-30",
    stock="300010",
    limit=10,
)

for item in result.items:
    print(item.announcement_time, item.announcement_title)

if result.items:
    path = download_pdf(result.items[0], save_dir="data/szse_pdf")
    print(path)
```

## Unified Result Model

三个 provider 的查询结果都返回同一类结构：

```python
result.source              # AnnouncementSource.CNINFO / SSE / SZSE
result.items               # list[BusinessAnnouncement]
result.response            # 标准响应，包含 announcements/raw_responses/has_more
```

`BusinessAnnouncement` 的核心字段：

| Field | Description |
| --- | --- |
| `source` | 公告源 |
| `sec_code` / `sec_name` | 证券代码和简称 |
| `org_id` | 上游机构或派生公司标识 |
| `announcement_id` | 稳定公告 ID |
| `announcement_title` | 公告标题 |
| `announcement_time` | 毫秒时间戳 |
| `adjunct_url` | PDF 相对路径 |
| `page_column` | 上游栏目 |

原始公告对象和原始响应会保留在 `result.response.announcements` 和
`result.response.raw_responses` 中，方便排查上游字段变化。

## PDF Handling

每个 provider 都提供：

```python
build_pdf_url(announcement)
download_pdf(announcement, save_dir="data/pdf")
```

下载逻辑会：

- 用上游相对路径构建静态 PDF 地址。
- 根据公告 ID 和标题生成安全文件名。
- 如果目标文件已存在且是完整 PDF，则直接复用。
- 如果本地旧文件是 HTML 错误页或损坏 PDF，则删除后重新下载。
- 下载响应必须满足 PDF magic header 和尾部 `%%EOF` 校验才会写入。

## Configuration

配置可以通过 `.env` 或环境变量控制。可参考 [.env.example](.env.example)。

常用变量：

| Prefix | Examples |
| --- | --- |
| `CNINFO_` | `CNINFO_TIMEOUT`, `CNINFO_RETRIES`, `CNINFO_USER_AGENT` |
| `SSE_` | `SSE_READ_TIMEOUT`, `SSE_RETRIES`, `SSE_INTER_PAGE_DELAY_SECONDS` |
| `SZSE_` | `SZSE_READ_TIMEOUT`, `SZSE_RETRIES`, `SZSE_USER_AGENT` |

也可以在初始化 client 时覆盖：

```python
from sse_announcement import SSEAnnouncementClient

with SSEAnnouncementClient(
    timeout=30,
    retries=3,
    user_agent="Mozilla/5.0 Custom",
) as client:
    result = client.query_announcements(
        searchkey="回购",
        start_date="2026-01-01",
        end_date="2026-01-31",
    )
```

## Development

```bash
uv sync --dev
uv run pytest
uv run ruff check src tests
uv build
```

常用聚焦测试：

```bash
uv run pytest tests/test_sse_client.py
uv run pytest tests/test_pdf_filename.py
```

## Project Layout

```text
src/
  announcement_common/   # shared HTTP, PDF, filename, env, model helpers
  cninfo_announcement/   # CNInfo query and PDF support
  sse_announcement/      # SSE query and PDF support
  szse_announcement/     # SZSE query and PDF support
tests/
  test_*                 # pytest tests with mocked exchange responses
```

## Notes

- 交易所接口可能限流、风控或返回 HTML 挑战页；生产任务建议设置合理的分页间隔、
  重试次数和 User-Agent。
- 不要提交 cookies、下载的 PDF、本地 `.env` 或任何凭据。
- 默认 headers 和 retry 策略保持保守，避免对上游接口造成过高请求压力。

## License

MIT License. Copyright (c) 2026 mochenya
<74086519+mochenya@users.noreply.github.com>.

See [LICENSE](LICENSE).
