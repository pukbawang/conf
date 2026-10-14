"""Best-effort plain-text extraction from downloaded file bytes.

Returns None for formats we don't know how to read — callers fall back to
generating records from just the filename and mime type in that case.
"""

from __future__ import annotations

import io

from pypdf import PdfReader

from . import config


def extract_text(content: bytes, mime_type: str) -> str | None:
    if mime_type.startswith("text/"):
        text = content.decode("utf-8", errors="ignore")
    elif mime_type == "application/pdf":
        text = _extract_pdf(content)
    else:
        return None

    text = text.strip()
    if not text:
        return None
    return text[: config.MAX_EXTRACT_CHARS]


def _extract_pdf(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages)
