from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from commercial_ocr.types import NormalizedOCRBlock, ProviderOCRResult, ProviderPageResult


DEFAULT_PROVIDER_FIXTURES = {
    "mock_commercial_ocr": "baidu_paper_cut_edu_single_page_normalized.json",
    "mock_tencent_question_split": "tencent_question_split_single_page_normalized.json",
    "mock_tencent_question_split_layout": "tencent_question_split_layout_single_page_normalized.json",
}


def fixture_root() -> Path:
    override = str(os.getenv("COMMERCIAL_OCR_FIXTURE_ROOT") or "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "commercial_ocr"


def fixture_path(name: str) -> Path:
    return fixture_root() / name


def load_fixture(name: str) -> dict[str, Any]:
    path = fixture_path(name)
    return json.loads(path.read_text(encoding="utf-8"))


def provider_result_from_fixture(
    provider_name: str,
    *,
    source_document_id: str,
    task_id: str,
    fixture_name: str | None = None,
    provider_status: str | None = None,
    provider_error: dict[str, Any] | None = None,
    provider_latency_ms: int | None = None,
    fallback_used: bool = False,
) -> ProviderOCRResult:
    payload = load_fixture(fixture_name or DEFAULT_PROVIDER_FIXTURES[provider_name])
    page_results = [
        ProviderPageResult(
            page_no=int(page.get("page_no") or 0),
            blocks=[_block_from_payload(block) for block in page.get("blocks") or []],
            figures=list(page.get("figures") or []),
            tables=list(page.get("tables") or []),
            raw=dict(page.get("raw") or {}),
            warnings=[str(item) for item in page.get("warnings") or [] if str(item).strip()],
        )
        for page in payload.get("page_results") or []
    ]
    return ProviderOCRResult(
        provider_name=str(provider_name or payload.get("provider_name") or "mock_commercial_ocr"),
        provider_version=str(payload.get("provider_version") or "fixture-v1"),
        source_document_id=source_document_id,
        task_id=task_id,
        page_results=page_results,
        raw_response_ref=payload.get("raw_response_ref"),
        provider_latency_ms=int(provider_latency_ms if provider_latency_ms is not None else payload.get("provider_latency_ms") or 0),
        provider_status=str(provider_status or payload.get("provider_status") or "ok"),
        provider_error=provider_error if provider_error is not None else payload.get("provider_error"),
        fallback_used=fallback_used,
        warnings=[str(item) for item in payload.get("warnings") or [] if str(item).strip()],
    )


def _block_from_payload(payload: dict[str, Any]) -> NormalizedOCRBlock:
    return NormalizedOCRBlock(
        block_id=str(payload.get("block_id") or ""),
        provider_ref=str(payload.get("provider_ref") or ""),
        page_no=int(payload.get("page_no") or 0),
        text=str(payload.get("text") or ""),
        bbox=[float(item) for item in payload.get("bbox") or []],
        block_type=str(payload.get("block_type") or "unknown"),
        confidence=float(payload["confidence"]) if payload.get("confidence") is not None else None,
        reading_order=int(payload.get("reading_order") or 0),
        parent_block_id=payload.get("parent_block_id"),
        raw=dict(payload.get("raw") or {}),
        warnings=[str(item) for item in payload.get("warnings") or [] if str(item).strip()],
    )
