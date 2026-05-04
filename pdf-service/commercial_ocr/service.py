from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Any

import fitz

from commercial_ocr.adapters import CommercialOCRProvider, provider_registry
from commercial_ocr.types import CommercialOCRExecution, ProviderOCRRequest, ProviderOCRResult
from models import PageContent, Region, TextBlock


logger = logging.getLogger(__name__)

LOCAL_PARSER_PROVIDER = "local_parser"
DEFAULT_PRIMARY_PROVIDER = LOCAL_PARSER_PROVIDER


def commercial_ocr_enabled() -> bool:
    return _env_flag("COMMERCIAL_OCR_ENABLED", default=False)


def primary_provider_name() -> str:
    return str(os.getenv("PDF_PARSE_PRIMARY_PROVIDER") or DEFAULT_PRIMARY_PROVIDER).strip() or DEFAULT_PRIMARY_PROVIDER


def fallback_provider_names() -> list[str]:
    raw = str(os.getenv("PDF_PARSE_FALLBACK_PROVIDERS") or LOCAL_PARSER_PROVIDER).strip()
    return [item.strip() for item in raw.split(",") if item.strip()]


def provider_trace_enabled() -> bool:
    return _env_flag("OCR_PROVIDER_TRACE_ENABLED", default=False)


def build_provider_request(
    extractor: Any,
    *,
    total_pages: int,
    debug_dir: str | None,
) -> ProviderOCRRequest:
    pdf_path = str(getattr(extractor, "pdf_path", "") or "")
    source_document_id = source_document_id_for_path(pdf_path)
    task_id = task_id_from_debug_dir(debug_dir) or source_document_id
    return ProviderOCRRequest(
        extractor=extractor,
        pdf_path=pdf_path,
        source_document_id=source_document_id,
        task_id=task_id,
        page_numbers=list(range(1, total_pages + 1)),
        debug_dir=debug_dir,
        trace_enabled=provider_trace_enabled(),
    )


def run_commercial_ocr_pipeline(
    extractor: Any,
    *,
    total_pages: int,
    debug_dir: str | None = None,
) -> CommercialOCRExecution:
    primary = primary_provider_name()
    execution = CommercialOCRExecution(requested_primary_provider=primary)
    if not commercial_ocr_enabled() and primary != LOCAL_PARSER_PROVIDER:
        execution.warnings.append("commercial_ocr_disabled")
        execution.should_use_local_parser = True
        execution.attempted_providers.append({"provider": primary, "status": "skipped_disabled"})
        return execution

    request = build_provider_request(extractor, total_pages=total_pages, debug_dir=debug_dir)
    order = _dedupe_order([primary, *fallback_provider_names()])
    providers = provider_registry()

    for provider_name in order:
        if provider_name == LOCAL_PARSER_PROVIDER:
            execution.should_use_local_parser = True
            execution.attempted_providers.append({"provider": provider_name, "status": "selected_local_parser"})
            if execution.provider_result is None:
                execution.effective_provider = provider_name
            return execution

        provider = providers.get(provider_name)
        if provider is None:
            execution.attempted_providers.append(
                {
                    "provider": provider_name,
                    "status": "skipped_unknown_provider",
                }
            )
            execution.warnings.append(f"unknown_provider:{provider_name}")
            continue

        available, missing = provider.is_available()
        if not available:
            execution.attempted_providers.append(
                {
                    "provider": provider_name,
                    "status": "skipped_unavailable",
                    "reasons": missing,
                }
            )
            execution.warnings.extend(missing)
            continue

        result = provider.analyze_document(request)
        execution.attempted_providers.append(
            {
                "provider": provider_name,
                "status": result.provider_status,
                "raw_response_ref": result.raw_response_ref,
                "provider_error": result.provider_error,
                "warnings": result.warnings,
            }
        )
        if result.provider_status == "ok" and result.page_results:
            execution.provider_result = result
            execution.effective_provider = provider_name
            execution.fallback_used = provider_name != primary
            result.fallback_used = execution.fallback_used
            return execution
        execution.warnings.extend(result.warnings)

    execution.should_use_local_parser = True
    if execution.effective_provider is None:
        execution.effective_provider = LOCAL_PARSER_PROVIDER
    return execution


def provider_result_to_page_contents(
    extractor: Any,
    result: ProviderOCRResult,
) -> list[PageContent]:
    page_contents: list[PageContent] = []
    for page_result in result.page_results:
        ordered_blocks = sorted(
            page_result.blocks,
            key=lambda block: (block.reading_order, block.bbox[1] if len(block.bbox) >= 2 else 0.0),
        )
        text_blocks = [
            TextBlock(
                bbox=block.bbox or [0.0, float(index * 14), 1000.0, float(index * 14 + 10)],
                text=_to_page_text(block.text, block.block_type),
            )
            for index, block in enumerate(ordered_blocks, start=1)
            if block.text.strip()
        ]
        regions = [
            region
            for block in ordered_blocks
            if block.block_type in {"table", "figure", "chart"}
            for region in [_region_for_block(extractor, page_result.page_no - 1, block)]
            if region is not None
        ]
        page_text = "\n".join(block.text for block in text_blocks if block.text.strip())
        page_contents.append(
            PageContent(
                page_num=page_result.page_no,
                text=page_text,
                blocks=text_blocks,
                regions=regions,
            )
        )
    return page_contents


def execution_summary(execution: CommercialOCRExecution | None) -> dict[str, Any] | None:
    if execution is None:
        return None
    provider_result = execution.provider_result
    return {
        "requested_primary_provider": execution.requested_primary_provider,
        "effective_provider": execution.effective_provider,
        "fallback_used": execution.fallback_used,
        "should_use_local_parser": execution.should_use_local_parser,
        "attempted_providers": execution.attempted_providers,
        "warnings": execution.warnings,
        "provider_result": provider_result.to_dict() if provider_result else None,
    }


def source_document_id_for_path(pdf_path: str) -> str:
    path = Path(pdf_path)
    stat = path.stat() if path.exists() else None
    signature = f"{path.name}:{getattr(stat, 'st_size', 0)}:{int(getattr(stat, 'st_mtime', 0) or 0)}"
    return hashlib.sha1(signature.encode("utf-8")).hexdigest()[:16]


def task_id_from_debug_dir(debug_dir: str | None) -> str | None:
    if not debug_dir:
        return None
    parts = Path(debug_dir).parts
    if "pdf-ai-preaudit" in parts:
        index = parts.index("pdf-ai-preaudit")
        if index + 1 < len(parts):
            task_id = str(parts[index + 1]).strip()
            if task_id:
                return task_id
    return Path(debug_dir).name.strip() or None


def _dedupe_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _env_flag(name: str, *, default: bool) -> bool:
    value = str(os.getenv(name) or "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def _to_page_text(text: str, block_type: str) -> str:
    normalized = text.strip()
    if not normalized:
        return ""
    prefixes = {
        "answer": "答案：",
        "analysis": "解析：",
    }
    prefix = prefixes.get(block_type)
    if prefix and not normalized.startswith(prefix):
        return f"{prefix}{normalized}"
    return normalized


def _region_for_block(extractor: Any, page_index: int, block: Any) -> Region | None:
    if len(block.bbox) != 4:
        return None
    try:
        rect = fitz.Rect(*block.bbox)
        page_rect = extractor.doc[page_index].rect
        clipped = fitz.Rect(
            max(rect.x0, page_rect.x0),
            max(rect.y0, page_rect.y0),
            min(rect.x1, page_rect.x1),
            min(rect.y1, page_rect.y1),
        )
        if clipped.width <= 0 or clipped.height <= 0:
            return None
        return Region(
            type=block.block_type,
            bbox=[float(clipped.x0), float(clipped.y0), float(clipped.x1), float(clipped.y1)],
            base64=extractor.get_region_screenshot(page_index, clipped),
            page=page_index + 1,
        )
    except Exception as exc:  # pragma: no cover - defensive only
        logger.warning("Failed to build OCR region for page=%s block=%s reason=%s", page_index + 1, block.block_id, exc)
        return None
