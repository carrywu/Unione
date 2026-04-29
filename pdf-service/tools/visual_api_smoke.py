from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import parser_kernel.adapter as parser_adapter
from debug_writer import _jsonable
from extractor import PDFExtractor
from parser_kernel.adapter import (
    VISUAL_PAGE_DPI,
    VISUAL_PAGE_MAX_SIDE,
    parse_extractor_with_kernel,
)
from tools.visual_debug_exporter import export_visual_debug_images
from validator import validate_and_clean

ALLOWED_PAGE_LIMITS = {1, 2, 5}
MAX_SMOKE_PAGES = max(ALLOWED_PAGE_LIMITS)
REVIEW_MANIFEST_FIELDS = [
    "question_index",
    "question_id",
    "page_num",
    "accepted",
    "confidence",
    "crop_path",
    "overlay_path",
    "material_crop_path",
    "crop_context_mode",
    "linked_material_id",
    "linked_visual_count",
    "next_question_boundary",
    "context_bbox",
    "question_bbox",
    "material_bbox",
    "visual_bbox_list",
]


def run_visual_api_smoke(
    pdf_path: str,
    *,
    page_limit: int | None = None,
    pages: str | None = None,
    output_dir: str,
    retry_failed_pages_only: bool = False,
    force_visual: bool = True,
    no_cache: bool = False,
    refresh_cache: bool = False,
    cache_dir: str | None = None,
) -> dict[str, Any]:
    if pages is None and page_limit not in ALLOWED_PAGE_LIMITS:
        raise ValueError("visual API smoke only supports page_limit 1, 2, or 5")

    pdf = Path(pdf_path).expanduser().resolve()
    if not pdf.exists():
        raise FileNotFoundError(f"PDF does not exist: {pdf}")

    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    screenshot_dir = output / "page_screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    cache = VisualPageCache(
        pdf_path=pdf,
        cache_root=Path(cache_dir).expanduser().resolve()
        if cache_dir
        else ROOT / "tmp" / "visual-api-smoke" / "cache",
        dpi=VISUAL_PAGE_DPI,
        max_side=VISUAL_PAGE_MAX_SIDE,
        no_cache=no_cache,
        refresh_cache=refresh_cache,
    )

    extractor = PDFExtractor(str(pdf))
    try:
        page_spec = pages if pages is not None else str(page_limit)
        page_indexes = parse_page_spec(page_spec, total_pages=extractor.total_pages)
        _validate_smoke_page_count(page_indexes, page_spec=page_spec)
        requested_page_indexes = list(page_indexes)
        retried_page_indexes: list[int] = []
        if retry_failed_pages_only:
            retried_page_indexes = cache.failed_page_indexes(page_indexes)
            cache.bypass_read_page_indexes.update(retried_page_indexes)
        window_extractor = PageWindowExtractor(extractor, page_indexes, force_visual=force_visual)
        actual_page_limit = len(page_indexes)
        _write_page_screenshots(extractor, screenshot_dir, page_indexes)
        original_parse_page_visual = parser_adapter.ai_client.parse_page_visual
        # TODO: This smoke-only monkeypatch is process-global. Avoid concurrent
        # in-process smoke runs until parser exposes an injectable visual client.
        parser_adapter.ai_client.parse_page_visual = cache.wrap_parse_page_visual(
            window_extractor=window_extractor,
            original_parse_page_visual=original_parse_page_visual,
        )
        try:
            parsed = parse_extractor_with_kernel(
                window_extractor,
                page_limit=actual_page_limit,
                debug_dir=str(output),
                retry_failed_pages_only=False,
            )
        finally:
            parser_adapter.ai_client.parse_page_visual = original_parse_page_visual
        _remap_parsed_page_numbers(parsed, page_indexes)
    finally:
        extractor.close()

    debug_dir = output / "debug"
    visual_pages = _remap_visual_pages(_read_json(debug_dir / "visual_pages.json", []), page_indexes)
    cache.update_from_visual_pages(visual_pages)
    _enrich_visual_pages_with_cache(visual_pages, cache)
    _write_json(debug_dir / "visual_pages.json", visual_pages)
    raw_model_response = [
        {
            "page_num": page.get("page_num"),
            "raw_result": page.get("raw_result"),
        }
        for page in visual_pages
    ]
    cleaned = validate_and_clean(parsed.get("questions") or [], parsed.get("materials") or [])
    rejected_candidates = cleaned.get("rejected_candidates") or []
    summary = _build_summary(
        pdf=pdf,
        output=output,
        page_spec=str(page_spec),
        requested_page_indexes=requested_page_indexes,
        page_indexes=page_indexes,
        page_limit=actual_page_limit,
        parsed=parsed,
        visual_pages=visual_pages,
        cleaned=cleaned,
        rejected_candidates=rejected_candidates,
        cache=cache,
        retried_pages=retried_page_indexes,
    )

    _write_json(output / "raw_model_response.json", raw_model_response)
    _write_json(output / "rejected_candidates.json", rejected_candidates)
    _write_json(output / "page_parse_summary.json", summary)
    lineages = export_visual_debug_images(
        pdf_path=pdf,
        output_dir=output,
        visual_pages=visual_pages,
        questions=cleaned.get("questions") or [],
        materials=cleaned.get("materials") or [],
    )
    review_manifest = _build_review_manifest(output=output, lineages=lineages)
    smoke_summary = _build_smoke_summary(
        review_manifest=review_manifest,
        rejected_candidates=rejected_candidates,
        visual_pages=visual_pages,
        cache=cache,
        retried_pages=retried_page_indexes,
    )
    _write_json(output / "review_manifest.json", review_manifest)
    _write_review_manifest_csv(output / "review_manifest.csv", review_manifest)
    _write_json(output / "summary.json", smoke_summary)
    return summary


class PageWindowExtractor:
    def __init__(self, extractor: PDFExtractor, page_indexes: list[int], *, force_visual: bool):
        self.extractor = extractor
        self.page_indexes = page_indexes
        self.force_visual = force_visual
        self.total_pages = len(page_indexes)
        self.pdf_path = extractor.pdf_path
        if hasattr(extractor, "doc"):
            self.doc = PageWindowDocument(extractor.doc, page_indexes)
        self.current_visual_page_index: int | None = None

    def _original_page_index(self, page_num: int) -> int:
        return self.page_indexes[page_num]

    def get_page_text(self, page_num: int) -> str:
        if self.force_visual:
            return ""
        return self.extractor.get_page_text(self._original_page_index(page_num))

    def get_page_screenshot(self, page_num: int, dpi: int = 150, max_side: int | None = None) -> str:
        if dpi == VISUAL_PAGE_DPI and max_side == VISUAL_PAGE_MAX_SIDE:
            self.current_visual_page_index = self._original_page_index(page_num)
        return self.extractor.get_page_screenshot(self._original_page_index(page_num), dpi=dpi, max_side=max_side)

    def get_page_screenshot_size(self, page_num: int, dpi: int = 150, max_side: int | None = None):
        return self.extractor.get_page_screenshot_size(self._original_page_index(page_num), dpi=dpi, max_side=max_side)

    def get_region_screenshot(self, page_num: int, rect: Any, padding: int = 10) -> str:
        return self.extractor.get_region_screenshot(self._original_page_index(page_num), rect, padding=padding)


class PageWindowDocument:
    def __init__(self, doc: Any, page_indexes: list[int]):
        self.doc = doc
        self.page_indexes = page_indexes

    def __getitem__(self, page_num: int) -> Any:
        return self.doc[self.page_indexes[page_num]]

    def __len__(self) -> int:
        return len(self.page_indexes)


class VisualPageCache:
    def __init__(
        self,
        *,
        pdf_path: Path,
        cache_root: Path,
        dpi: int,
        max_side: int | None,
        no_cache: bool,
        refresh_cache: bool,
    ):
        self.pdf_path = pdf_path
        self.cache_root = cache_root
        self.dpi = dpi
        self.max_side = max_side
        self.no_cache = no_cache
        self.refresh_cache = refresh_cache
        self.pdf_hash = _sha256_file(pdf_path)
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.events: dict[int, dict[str, Any]] = {}
        self.cache_hits = 0
        self.cache_misses = 0
        self._call_counts: dict[int, int] = {}
        self.bypass_read_page_indexes: set[int] = set()

    def key_for_page(self, page_index: int) -> str:
        max_side = "none" if self.max_side is None else str(self.max_side)
        return f"{self.pdf_hash}_p{page_index}_dpi{self.dpi}_max{max_side}"

    def path_for_page(self, page_index: int) -> Path:
        return self.cache_root / self.pdf_hash / f"{self.key_for_page(page_index)}.json"

    def metadata_for_page(self, page_index: int) -> dict[str, Any]:
        event = self.events.get(page_index, {})
        return {
            "cache_hit": bool(event.get("cache_hit", False)),
            "cache_key": self.key_for_page(page_index),
            "cache_path": str(self.path_for_page(page_index)),
        }

    def wrap_parse_page_visual(self, *, window_extractor: PageWindowExtractor, original_parse_page_visual):
        def cached_parse(page_b64: str):
            page_index = window_extractor.current_visual_page_index
            if page_index is None:
                return original_parse_page_visual(page_b64)

            call_count = self._call_counts.get(page_index, 0)
            self._call_counts[page_index] = call_count + 1
            cache_path = self.path_for_page(page_index)
            if (
                call_count == 0
                and page_index not in self.bypass_read_page_indexes
                and not self.no_cache
                and not self.refresh_cache
                and cache_path.exists()
            ):
                payload = _read_json(cache_path, {})
                visual_result = payload.get("visual_result") if isinstance(payload, dict) else None
                if isinstance(visual_result, dict):
                    self.cache_hits += 1
                    self.events[page_index] = {
                        "cache_hit": True,
                        "cache_key": self.key_for_page(page_index),
                        "cache_path": str(cache_path),
                    }
                    return visual_result

            if call_count == 0:
                self.cache_misses += 1
            self.events[page_index] = {
                "cache_hit": False,
                "cache_key": self.key_for_page(page_index),
                "cache_path": str(cache_path),
            }
            visual_result = original_parse_page_visual(page_b64)
            self.write_visual_result(page_index=page_index, visual_result=visual_result, base64_size=len(page_b64))
            return visual_result

        return cached_parse

    def write_visual_result(
        self,
        *,
        page_index: int,
        visual_result: dict[str, Any],
        image_size: dict[str, Any] | None = None,
        base64_size: int | None = None,
        request_status: str | None = None,
    ) -> None:
        cache_path = self.path_for_page(page_index)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        normalized = {key: value for key, value in visual_result.items() if key != "raw_model_result"}
        payload = {
            "cache_key": self.key_for_page(page_index),
            "pdf_hash": self.pdf_hash,
            "page_index": page_index,
            "render_config": {"dpi": self.dpi, "max_side": self.max_side},
            "visual_raw_response": visual_result.get("raw_model_result", visual_result),
            "normalized_page_result": normalized,
            "warnings": list(visual_result.get("warnings") or []),
            "image_size": image_size,
            "base64_size": base64_size,
            "request_status": request_status or _request_status_for_visual_result(visual_result),
            "visual_result": visual_result,
        }
        _atomic_write_json(cache_path, payload)

    def update_from_visual_pages(self, visual_pages: list[dict[str, Any]]) -> None:
        for page in visual_pages:
            try:
                page_index = int(page.get("page_num")) - 1
            except (TypeError, ValueError):
                continue
            normalized = page.get("normalized_result") or {}
            raw_result = page.get("raw_result")
            visual_result = dict(normalized)
            if raw_result is not None:
                visual_result["raw_model_result"] = raw_result
            self.write_visual_result(
                page_index=page_index,
                visual_result=visual_result,
                image_size=page.get("image_size"),
                base64_size=page.get("base64_size"),
                request_status=page.get("request_status"),
            )
            self.events.setdefault(
                page_index,
                {
                    "cache_hit": False,
                    "cache_key": self.key_for_page(page_index),
                    "cache_path": str(self.path_for_page(page_index)),
                },
            )

    def failed_page_indexes(self, page_indexes: list[int]) -> list[int]:
        failed: list[int] = []
        for page_index in page_indexes:
            payload = _read_json(self.path_for_page(page_index), {})
            if isinstance(payload, dict) and _cache_payload_failed(payload):
                failed.append(page_index)
        return failed


def parse_page_spec(page_spec: str | int | None, *, total_pages: int) -> list[int]:
    if page_spec is None:
        page_spec = "5"
    spec = str(page_spec).strip()
    if not spec:
        raise ValueError("pages spec cannot be empty")
    if "," not in spec and "-" not in spec:
        count = int(spec)
        if count <= 0:
            raise ValueError("page count must be positive")
        return list(range(min(count, total_pages)))
    indexes: list[int] = []
    for part in (chunk.strip() for chunk in spec.split(",")):
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            if start < 0 or end < start:
                raise ValueError(f"invalid page range: {part}")
            indexes.extend(range(start, min(end, total_pages)))
        else:
            index = int(part)
            if index < 0:
                raise ValueError(f"invalid page index: {part}")
            if index < total_pages:
                indexes.append(index)
    deduped = list(dict.fromkeys(indexes))
    if not deduped:
        raise ValueError(f"pages spec selected no pages: {spec}")
    return deduped


def _validate_smoke_page_count(page_indexes: list[int], *, page_spec: str | int | None) -> None:
    if len(page_indexes) <= MAX_SMOKE_PAGES:
        return
    raise ValueError(
        f"visual API smoke selected {len(page_indexes)} pages from --pages={page_spec!r}; "
        f"maximum is {MAX_SMOKE_PAGES}. Please shrink --pages to 1, 2, or 5 pages."
    )


def _write_page_screenshots(extractor: PDFExtractor, screenshot_dir: Path, page_indexes: list[int]) -> None:
    for page_index in page_indexes:
        screenshot_b64 = extractor.get_page_screenshot(
            page_index,
            dpi=VISUAL_PAGE_DPI,
            max_side=VISUAL_PAGE_MAX_SIDE,
        )
        (screenshot_dir / f"page_{page_index + 1:03d}.png").write_bytes(base64.b64decode(screenshot_b64))


def _remap_parsed_page_numbers(parsed: dict[str, Any], page_indexes: list[int]) -> None:
    for question in parsed.get("questions") or []:
        for key in ("page_num", "source_page_start", "source_page_end"):
            if key in question:
                question[key] = _local_page_to_original(question.get(key), page_indexes)


def _remap_visual_pages(visual_pages: list[dict[str, Any]], page_indexes: list[int]) -> list[dict[str, Any]]:
    remapped: list[dict[str, Any]] = []
    for page in visual_pages:
        clone = dict(page)
        clone["page_num"] = _local_page_to_original(page.get("page_num"), page_indexes)
        remapped.append(clone)
    return remapped


def _local_page_to_original(value: Any, page_indexes: list[int]) -> Any:
    try:
        local_page_num = int(value)
    except (TypeError, ValueError):
        return value
    local_index = local_page_num - 1
    if 0 <= local_index < len(page_indexes):
        return page_indexes[local_index] + 1
    return value


def _build_summary(
    *,
    pdf: Path,
    output: Path,
    page_spec: str,
    requested_page_indexes: list[int],
    page_indexes: list[int],
    page_limit: int,
    parsed: dict[str, Any],
    visual_pages: list[dict[str, Any]],
    cleaned: dict[str, Any],
    rejected_candidates: list[dict[str, Any]],
    cache: VisualPageCache,
    retried_pages: list[int],
) -> dict[str, Any]:
    stats = parsed.get("stats") or {}
    normalized_question_candidates = sum(
        len(((page.get("normalized_result") or {}).get("questions") or []))
        for page in visual_pages
    )
    candidate_counts = {
        "visual_question_candidates": normalized_question_candidates,
        "kernel_question_candidates": int(stats.get("question_candidates_count") or len(parsed.get("questions") or [])),
        "accepted_questions": len(cleaned.get("questions") or []),
        "rejected_candidates": len(rejected_candidates),
    }
    return {
        "pdf": str(pdf),
        "output_dir": str(output),
        "debug_dir": str(output / "debug"),
        "page_spec": page_spec,
        "requested_page_indexes": requested_page_indexes,
        "page_indexes": page_indexes,
        "retried_pages": retried_pages,
        "cache_hits": cache.cache_hits,
        "cache_misses": cache.cache_misses,
        "timeout_pages": _timeout_pages(visual_pages),
        "failed_pages": _failed_pages(visual_pages),
        "page_limit": page_limit,
        "pages_attempted": len(visual_pages),
        "pages": [
            {
                "page_num": page.get("page_num"),
                "request_status": page.get("request_status"),
                "attempts": page.get("attempts"),
                "attempt_errors": page.get("attempt_errors") or [],
                "warnings": page.get("page_warnings") or [],
                "image_size": page.get("image_size"),
                "base64_size": page.get("base64_size"),
                "cache_hit": page.get("cache_hit", False),
                "cache_key": page.get("cache_key"),
                "cache_path": page.get("cache_path"),
                "raw_question_candidates": len(((page.get("raw_result") or {}).get("questions") or []))
                if isinstance(page.get("raw_result"), dict)
                else None,
                "normalized_question_candidates": len(((page.get("normalized_result") or {}).get("questions") or [])),
            }
            for page in visual_pages
        ],
        "candidate_counts": candidate_counts,
        "reject_reasons": _count_reject_reasons(rejected_candidates),
        "rejected_candidates": rejected_candidates,
        "questions_preview": [
            {
                "index": question.get("index"),
                "page_num": question.get("page_num"),
                "content_preview": (question.get("content") or "")[:160],
                "warnings": question.get("parse_warnings") or [],
            }
            for question in (cleaned.get("questions") or [])[:10]
        ],
    }


def _build_review_manifest(*, output: Path, lineages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    material_crop_by_id = {
        (item.get("page_num"), item.get("linked_material_id")): item
        for item in lineages
        if item.get("type") == "material_crop" and item.get("linked_material_id")
    }
    records: list[dict[str, Any]] = []
    for item in lineages:
        if item.get("type") != "question_crop":
            continue
        linked_material_id = item.get("linked_material_id")
        page_num = int(item.get("page_num") or 0)
        material_lineage = material_crop_by_id.get((page_num, linked_material_id))
        question_index = item.get("linked_question_id")
        records.append(
            {
                "question_index": question_index,
                "question_id": item.get("source_candidate_id"),
                "page_num": page_num,
                "accepted": True,
                "confidence": item.get("confidence"),
                "crop_path": _relative_path(output, item.get("file")),
                "overlay_path": _relative_path(output, output / "debug" / "overlays" / f"page_{page_num:03d}_overlay.png"),
                "material_crop_path": _relative_path(output, (material_lineage or {}).get("file")),
                "crop_context_mode": item.get("crop_context_mode"),
                "linked_material_id": linked_material_id,
                "linked_visual_count": item.get("linked_visual_count") or 0,
                "next_question_boundary": item.get("next_question_boundary"),
                "context_bbox": item.get("context_bbox"),
                "question_bbox": item.get("question_bbox") or item.get("raw_bbox"),
                "material_bbox": item.get("material_bbox"),
                "visual_bbox_list": item.get("visual_bbox_list") or [],
            }
        )
    return records


def _write_review_manifest_csv(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=REVIEW_MANIFEST_FIELDS)
        writer.writeheader()
        for record in records:
            row = {}
            for field in REVIEW_MANIFEST_FIELDS:
                value = record.get(field)
                if isinstance(value, list | dict):
                    row[field] = json.dumps(_jsonable(value), ensure_ascii=False)
                elif value is None:
                    row[field] = ""
                else:
                    row[field] = value
            writer.writerow(row)


def _build_smoke_summary(
    *,
    review_manifest: list[dict[str, Any]],
    rejected_candidates: list[dict[str, Any]],
    visual_pages: list[dict[str, Any]],
    cache: VisualPageCache,
    retried_pages: list[int],
) -> dict[str, Any]:
    page_heights = {
        int(page.get("page_num") or 0): int((page.get("image_size") or {}).get("height") or 0)
        for page in visual_pages
    }
    widths: list[float] = []
    heights: list[float] = []
    suspicious: list[dict[str, Any]] = []
    for record in review_manifest:
        bbox = record.get("context_bbox") or record.get("question_bbox") or []
        if isinstance(bbox, list) and len(bbox) == 4:
            width = float(bbox[2]) - float(bbox[0])
            height = float(bbox[3]) - float(bbox[1])
            widths.append(width)
            heights.append(height)
        else:
            width = 0.0
            height = 0.0
        reasons: list[str] = []
        page_height = page_heights.get(int(record.get("page_num") or 0), 0)
        if page_height and height > page_height * 0.7:
            reasons.append("crop_height_gt_page_70_percent")
        if width and width < 200:
            reasons.append("crop_width_lt_200")
        if int(record.get("linked_visual_count") or 0) > 5:
            reasons.append("linked_visual_count_gt_5")
        if record.get("next_question_boundary") is not None:
            reasons.append("touches_next_question_boundary")
        if reasons:
            suspicious.append(
                {
                    "question_index": record.get("question_index"),
                    "question_id": record.get("question_id"),
                    "page_num": record.get("page_num"),
                    "reasons": reasons,
                }
            )
    return {
        "total_questions": len(review_manifest),
        "accepted_questions": sum(1 for record in review_manifest if record.get("accepted")),
        "rejected_candidates": len(rejected_candidates),
        "questions_with_material": sum(1 for record in review_manifest if record.get("linked_material_id")),
        "questions_with_visuals": sum(1 for record in review_manifest if int(record.get("linked_visual_count") or 0) > 0),
        "avg_crop_width": round(sum(widths) / len(widths), 2) if widths else 0,
        "avg_crop_height": round(sum(heights) / len(heights), 2) if heights else 0,
        "max_crop_height": round(max(heights), 2) if heights else 0,
        "suspicious_crops": suspicious,
        "cache_hits": cache.cache_hits,
        "cache_misses": cache.cache_misses,
        "retried_pages": retried_pages,
        "timeout_pages": _timeout_pages(visual_pages),
        "failed_pages": _failed_pages(visual_pages),
    }


def _relative_path(output: Path, path: Any) -> str:
    if not path:
        return ""
    try:
        return str(Path(path).resolve().relative_to(output.resolve()))
    except (OSError, ValueError):
        return str(path)


def _enrich_visual_pages_with_cache(visual_pages: list[dict[str, Any]], cache: VisualPageCache) -> None:
    for page in visual_pages:
        try:
            page_index = int(page.get("page_num")) - 1
        except (TypeError, ValueError):
            continue
        page.update(cache.metadata_for_page(page_index))


def _timeout_pages(visual_pages: list[dict[str, Any]]) -> list[int]:
    pages: list[int] = []
    for page in visual_pages:
        warnings = set(str(item) for item in page.get("page_warnings") or [])
        if "vision_page_timeout" in warnings:
            try:
                pages.append(int(page.get("page_num")) - 1)
            except (TypeError, ValueError):
                continue
    return pages


def _failed_pages(visual_pages: list[dict[str, Any]]) -> list[int]:
    pages: list[int] = []
    for page in visual_pages:
        warnings = set(str(item) for item in page.get("page_warnings") or [])
        if page.get("request_status") == "failed" or warnings & {"vision_page_timeout", "visual_model_failed"}:
            try:
                pages.append(int(page.get("page_num")) - 1)
            except (TypeError, ValueError):
                continue
    return pages


def _cache_payload_failed(payload: dict[str, Any]) -> bool:
    if payload.get("request_status") == "failed":
        return True
    warnings = set(str(item) for item in payload.get("warnings") or [])
    return bool(warnings & {"vision_page_timeout", "visual_model_failed"})


def _request_status_for_visual_result(visual_result: dict[str, Any]) -> str:
    warnings = set(str(item) for item in visual_result.get("warnings") or [])
    return "failed" if warnings & {"vision_page_timeout", "visual_model_failed"} else "ok"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _count_reject_reasons(rejected_candidates: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in rejected_candidates:
        reason = str(candidate.get("reason") or "unknown")
        counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items()))


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(_jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp_path.write_text(json.dumps(_jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a bounded real visual API smoke on scanned question pages.")
    parser.add_argument("pdf", help="Path to the scanned question-book PDF.")
    parser.add_argument("--pages", required=True, help="Page count (legacy, e.g. 5), zero-based range (0-20), or zero-based list (8,9,10).")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--retry-failed-pages-only", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--clean-output", action="store_true")
    parser.add_argument("--allow-text-layer", action="store_true", help="Do not force visual fallback for text-layer PDFs.")
    args = parser.parse_args()

    safe_pages = str(args.pages).replace(",", "_").replace("-", "_")
    output_dir = Path(args.output_dir) if args.output_dir else ROOT / "tmp" / "visual-api-smoke" / f"pages-{safe_pages}"
    if args.clean_output and output_dir.exists() and not args.retry_failed_pages_only:
        shutil.rmtree(output_dir)

    summary = run_visual_api_smoke(
        args.pdf,
        pages=args.pages,
        output_dir=str(output_dir),
        retry_failed_pages_only=args.retry_failed_pages_only,
        force_visual=not args.allow_text_layer,
        no_cache=args.no_cache,
        refresh_cache=args.refresh_cache,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
