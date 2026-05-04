from __future__ import annotations

from pathlib import Path

import httpx

PDF_MAGIC = b"%PDF-"
PDF_EOF = b"%%EOF"
PDF_EOF_SEARCH_BYTES = 2048


def is_pdf_response(response: httpx.Response) -> bool:
    # Content-Type 可能被错误页沿用；下载落盘前必须用 PDF 结构特征确认内容。
    return response.status_code == 200 and is_pdf_content(response.content)


def is_pdf_content(content: bytes) -> bool:
    return content.startswith(PDF_MAGIC) and PDF_EOF in content[-PDF_EOF_SEARCH_BYTES:]


def is_existing_pdf(path: Path) -> bool:
    try:
        with path.open("rb") as file:
            if file.read(len(PDF_MAGIC)) != PDF_MAGIC:
                return False
            file.seek(0, 2)
            file_size = file.tell()
            file.seek(max(0, file_size - PDF_EOF_SEARCH_BYTES))
            return PDF_EOF in file.read()
    except OSError:
        return False


def write_pdf_atomic(target_path: Path, content: bytes) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = target_path.with_name(f"{target_path.name}.part")
    temporary_path.write_bytes(content)
    temporary_path.replace(target_path)
