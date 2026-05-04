from __future__ import annotations

from pathlib import Path

import httpx

from announcement_common.pdf import is_existing_pdf, is_pdf_content, is_pdf_response

VALID_PDF = b"%PDF-1.7\nbody\n%%EOF\n"


def test_is_pdf_content_accepts_eof_with_trailing_newline() -> None:
    assert is_pdf_content(VALID_PDF) is True


def test_is_pdf_content_rejects_truncated_pdf() -> None:
    assert is_pdf_content(b"%PDF-1.7\nbody") is False


def test_is_pdf_response_rejects_html_disguised_as_pdf() -> None:
    response = httpx.Response(
        200,
        content=b"<html>not pdf</html>",
        headers={"content-type": "application/pdf"},
    )

    assert is_pdf_response(response) is False


def test_is_existing_pdf_rejects_eof_outside_tail_window(tmp_path: Path) -> None:
    path = tmp_path / "large.pdf"
    path.write_bytes(b"%PDF-1.7\n%%EOF" + b"x" * 2049)

    assert is_existing_pdf(path) is False
