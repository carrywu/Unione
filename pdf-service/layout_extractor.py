from __future__ import annotations

from typing import Any

from markdown_extractor import extract_pdf_to_markdown


def extract_layout_to_markdown(pdf_path: str, output_dir: str) -> dict[str, Any]:
    """Extract a PDF into the internal layout payload using the self-built parser."""
    payload = extract_pdf_to_markdown(pdf_path, output_dir)
    payload.setdefault("extractor", "self_pymupdf")
    return payload
