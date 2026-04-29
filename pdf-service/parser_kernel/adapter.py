from __future__ import annotations

import os
import queue
import re
import tempfile
import threading
import json
from pathlib import Path
from typing import Any

import ai_client
import fitz
from dotenv import load_dotenv
from debug_writer import write_debug_bundle
from models import PageContent, RawQuestion, Region
from parser_kernel.layout_engine import normalize_pages
from parser_kernel.question_group_builder import build_groups
from parser_kernel.routing import classify_pdf_kind
from parser_kernel.semantic_segmenter import annotate_semantics
from parser_kernel.types import MaterialGroup, QuestionGroup


OPTION_RE = re.compile(r"^\s*([A-D])[．.、。]\s*(.+)$")
VISUAL_PAGE_DPI = 110
VISUAL_PAGE_MAX_SIDE = 1600
DEFAULT_VISUAL_PAGE_TIMEOUT_SECONDS = 45.0
VISUAL_BBOX_CLAMP_EPSILON = 1e-3

load_dotenv()


def groups_to_raw_questions(
    pages: list[PageContent],
    materials: list[MaterialGroup],
    questions: list[QuestionGroup],
) -> list[RawQuestion]:
    material_text_by_id = {
        material.id: "\n".join(part for part in [material.prompt_text, material.body_text] if part).strip()
        for material in materials
    }
    return [
        RawQuestion(
            index=question.index,
            text=question.text,
            page_num=question.page_num,
            y0=question.y0,
            y1=question.y1,
            images=_attach_regions(question, pages),
            material_id=question.material_id,
            material_text=material_text_by_id.get(question.material_id),
        )
        for question in questions
    ]


def parse_pages_to_raw_questions(pages: list[PageContent]) -> list[RawQuestion]:
    elements = normalize_pages(pages)
    annotated = annotate_semantics(elements)
    materials, questions = build_groups(annotated)
    return groups_to_raw_questions(pages, materials, questions)


def parse_extractor_with_kernel(
    extractor: Any,
    *,
    page_limit: int | None = None,
    debug_dir: str | None = None,
    retry_failed_pages_only: bool = False,
) -> dict[str, Any]:
    file_name = os.path.basename(getattr(extractor, "pdf_path", "") or "")
    total_pages = min(
        getattr(extractor, "total_pages", 0),
        page_limit or getattr(extractor, "total_pages", 0),
    )
    text_lengths = [
        len((extractor.get_page_text(page_index) or "").strip())
        for page_index in range(total_pages)
    ]
    pdf_kind = classify_pdf_kind(
        file_name=file_name,
        total_pages=total_pages,
        text_lengths=text_lengths,
    )
    if pdf_kind in {"answer_note", "scanned_answer_book"}:
        return {"questions": [], "materials": [], "pdf_kind": pdf_kind}

    debug_dir = debug_dir or tempfile.mkdtemp(prefix="pdf-parser-kernel-")
    pages = (
        _pages_from_visual_fallback(
            extractor,
            total_pages,
            debug_dir=debug_dir,
            retry_failed_pages_only=retry_failed_pages_only,
        )
        if pdf_kind == "scanned_question_book"
        else _pages_from_extractor(extractor, total_pages)
    )
    elements = normalize_pages(pages)
    annotated = annotate_semantics(elements)
    material_groups, question_groups = build_groups(annotated)
    raw_questions = groups_to_raw_questions(pages, material_groups, question_groups)
    visual_links = getattr(
        extractor,
        "_parser_kernel_visual_links",
        {
            "materials": {},
            "questions": {},
            "question_material_ids": {},
            "material_texts": {},
            "question_link_warnings": {},
            "warnings": [],
        },
    )
    parser_warnings = getattr(extractor, "_parser_kernel_warnings", [])
    material_ids_by_text: dict[str, str] = {}
    materials: list[dict[str, Any]] = []
    questions: list[dict[str, Any]] = []
    link_warnings = visual_links.get("question_link_warnings", {})

    for raw in raw_questions:
        content, options = _split_options(raw.text)
        effective_material_id = raw.material_id or visual_links.get("question_material_ids", {}).get(raw.index)
        effective_material_text = raw.material_text or visual_links.get("material_texts", {}).get(effective_material_id)
        material_temp_id = None
        if effective_material_text:
            material_temp_id = material_ids_by_text.get(effective_material_text)
            if material_temp_id is None:
                material_temp_id = f"m_{len(materials) + 1}"
                material_ids_by_text[effective_material_text] = material_temp_id
                materials.append(
                    {
                        "temp_id": material_temp_id,
                        "content": effective_material_text,
                        "images": [],
                    }
                )
            for material in materials:
                if material["temp_id"] == material_temp_id:
                    material["images"] = [
                        _region_to_image(region, assignment_confidence=0.85)
                        for region in visual_links.get("materials", {}).get(effective_material_id or "", [])
                    ]
                    break
        question_images = [_region_to_image(region) for region in raw.images]
        question_images.extend(
            _region_to_image(region, assignment_confidence=0.8)
            for region in visual_links.get("questions", {}).get(raw.index, [])
            if region.base64 not in {image["base64"] for image in question_images}
        )
        question_warnings = list(getattr(raw, "warnings", []) or [])
        question_warnings.extend(link_warnings.get(raw.index, []))
        if not content:
            question_warnings.append("question_content_empty")
        if not question_images:
            question_warnings.append("question_region_missing")
            question_images.append(_region_to_image(_full_page_region(extractor, raw.page_num - 1), assignment_confidence=0.2))
        source_bbox = _source_bbox_for_question(extractor, raw, visual_links)
        questions.append(
            {
                "index": raw.index,
                "type": "single" if options else "judge",
                "content": content,
                "option_a": options.get("A"),
                "option_b": options.get("B"),
                "option_c": options.get("C"),
                "option_d": options.get("D"),
                "options": options,
                "answer": None,
                "analysis": None,
                "needs_review": True,
                "material_text": effective_material_text,
                "material_temp_id": material_temp_id,
                "images": question_images,
                "page_num": raw.page_num,
                "page_range": [raw.page_num, raw.page_num],
                "source_page_start": raw.page_num,
                "source_page_end": raw.page_num,
                "source_bbox": source_bbox,
                "source_anchor_text": f"{raw.index}.",
                "source_confidence": 0.7 if source_bbox else 0.4,
                "source": "parser_kernel_scanned",
                "parse_warnings": sorted(set(question_warnings)),
            }
        )

    write_debug_bundle(
        debug_dir,
        visual_pages=getattr(extractor, "_parser_kernel_visual_pages", []),
        failed_pages={"failed_pages": getattr(extractor, "_parser_kernel_failed_pages", [])},
        page_elements=elements,
        annotated_elements=annotated,
        material_groups=material_groups,
        question_groups=question_groups,
        raw_questions=raw_questions,
        output_questions=questions,
        output_materials=materials,
        warnings={
            "pdf_kind": pdf_kind,
            "summary": _debug_counts(
                total_pages=total_pages,
                page_elements_count=len(elements),
                question_candidates_count=len(raw_questions),
                accepted_questions_count=len(questions),
                rejected_questions_count=max(0, len(raw_questions) - len(questions)),
                materials_count=len(materials),
                visuals_count=sum(len(page.regions) for page in pages),
            ),
            "parser_warnings": parser_warnings,
            "visual_link_warnings": visual_links.get("warnings", []),
        },
    )

    return {
        "questions": questions,
        "materials": materials,
        "pdf_kind": pdf_kind,
        "debug_dir": debug_dir,
        "stats": {
            **_debug_counts(
                total_pages=total_pages,
                page_elements_count=len(elements),
                question_candidates_count=len(raw_questions),
                accepted_questions_count=len(questions),
                rejected_questions_count=max(0, len(raw_questions) - len(questions)),
                materials_count=len(materials),
                visuals_count=sum(len(page.regions) for page in pages),
            ),
            "debug_dir": debug_dir,
        },
    }


def _debug_counts(
    *,
    total_pages: int,
    page_elements_count: int,
    question_candidates_count: int,
    accepted_questions_count: int,
    rejected_questions_count: int,
    materials_count: int,
    visuals_count: int,
) -> dict[str, int]:
    return {
        "pages_count": total_pages,
        "page_elements_count": page_elements_count,
        "question_candidates_count": question_candidates_count,
        "accepted_questions_count": accepted_questions_count,
        "rejected_questions_count": rejected_questions_count,
        "materials_count": materials_count,
        "visuals_count": visuals_count,
    }


def _pages_from_extractor(extractor: Any, total_pages: int) -> list[PageContent]:
    pages: list[PageContent] = []
    for page_index in range(total_pages):
        text = extractor.get_page_text(page_index)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        blocks = []
        y = 0.0
        for line in lines:
            blocks.append({"bbox": [0.0, y, 1000.0, y + 10.0], "text": line})
            y += 12.0
        pages.append(
            PageContent(
                page_num=page_index + 1,
                text=text,
                blocks=blocks,
                regions=[],
            )
        )
    return pages


def _visual_page_indexes(total_pages: int, debug_dir: str, retry_failed_pages_only: bool) -> list[int]:
    if not retry_failed_pages_only:
        return list(range(total_pages))
    failed_pages_file = Path(debug_dir) / "debug" / "failed_pages.json"
    try:
        payload = json.loads(failed_pages_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return list(range(total_pages))
    failed_pages = payload.get("failed_pages") or []
    indexes: list[int] = []
    for page_num in failed_pages:
        try:
            page_index = int(page_num) - 1
        except (TypeError, ValueError):
            continue
        if 0 <= page_index < total_pages:
            indexes.append(page_index)
    return indexes


def _get_page_screenshot(
    extractor: Any,
    page_index: int,
    *,
    dpi: int,
    max_side: int | None,
) -> str:
    try:
        return extractor.get_page_screenshot(page_index, dpi=dpi, max_side=max_side)
    except TypeError:
        return extractor.get_page_screenshot(page_index, dpi=dpi)


def _get_page_screenshot_size(
    extractor: Any,
    page_index: int,
    *,
    dpi: int,
    max_side: int | None,
) -> dict[str, Any] | None:
    if not hasattr(extractor, "get_page_screenshot_size"):
        return None
    try:
        return extractor.get_page_screenshot_size(page_index, dpi=dpi, max_side=max_side)
    except TypeError:
        return extractor.get_page_screenshot_size(page_index, dpi=dpi)
    except Exception:
        return None


def _write_visual_page_cache(cache_dir: Path, page_num: int, visual_result: dict[str, Any]) -> None:
    if _visual_result_failed(visual_result):
        return
    (cache_dir / f"page_{page_num}.json").write_text(
        json.dumps(visual_result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _pages_from_visual_fallback(
    extractor: Any,
    total_pages: int,
    *,
    debug_dir: str,
    retry_failed_pages_only: bool = False,
) -> list[PageContent]:
    pages: list[PageContent] = []
    visual_pages: list[dict[str, Any]] = []
    failed_pages: list[int] = []
    page_indexes = _visual_page_indexes(total_pages, debug_dir, retry_failed_pages_only)
    cache_dir = Path(debug_dir) / "debug" / "visual_page_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    visual_links: dict[str, Any] = {
        "materials": {},
        "questions": {},
        "question_material_ids": {},
        "material_texts": {},
        "question_positions": {},
        "material_positions": {},
        "question_link_warnings": {},
        "warnings": [],
    }
    parser_warnings: list[dict[str, Any]] = []
    for page_index in page_indexes:
        page_b64 = _get_page_screenshot(
            extractor,
            page_index,
            dpi=VISUAL_PAGE_DPI,
            max_side=VISUAL_PAGE_MAX_SIDE,
        )
        image_size = _get_page_screenshot_size(
            extractor,
            page_index,
            dpi=VISUAL_PAGE_DPI,
            max_side=VISUAL_PAGE_MAX_SIDE,
        )
        _cache_visual_render_size(extractor, page_index, image_size)
        visual_result, attempt_errors, attempts = _parse_page_visual_with_retry(page_b64)
        blocks = []
        regions: list[Region] = []
        lines: list[str] = []
        y = 0.0
        page_warnings: list[str] = []
        visual_debug = {
            "page_num": page_index + 1,
            "raw_result": visual_result.get("raw_model_result", visual_result),
            "normalized_result": {
                key: value
                for key, value in visual_result.items()
                if key != "raw_model_result"
            },
            "request_status": "failed" if _visual_result_failed(visual_result) else "ok",
            "attempts": attempts,
            "attempt_errors": attempt_errors,
            "image_size": image_size,
            "base64_size": len(page_b64),
        }
        page_material_keys: dict[str, str] = {}

        for material in visual_result.get("materials", []) or []:
            content = str(material.get("content") or "").strip()
            if not content:
                continue
            material_text = _material_block_text(content)
            lines.append(material_text)
            bbox = material.get("bbox") or [0.0, y, 1000.0, y + 10.0]
            blocks.append({"bbox": bbox, "text": material_text})
            if material.get("bbox"):
                material_region = _region_from_bbox(
                    extractor,
                    page_index,
                    material["bbox"],
                    "material",
                    warnings=page_warnings,
                )
                if material_region:
                    regions.append(material_region)
                    material_id = str(material.get("temp_id") or "") or f"material_{len(page_material_keys) + 1}"
                    material_key = f"page_{page_index + 1}:{material_id}"
                    page_material_keys[material_id] = material_key
                    visual_links["materials"].setdefault(material_key, []).append(material_region)
                    visual_links["material_texts"][material_key] = content
                    visual_links["material_positions"][material_key] = {
                        "page_num": page_index + 1,
                        "y0": float(bbox[1]),
                        "y1": float(bbox[3]),
                    }
            y += 12.0

        for question in visual_result.get("questions", []) or []:
            index = question.get("index")
            if index is None:
                continue
            material_temp_id = str(question.get("material_temp_id") or "")
            if material_temp_id:
                material_key = page_material_keys.get(material_temp_id)
                if material_key:
                    visual_links["question_material_ids"][index] = material_key
            anchor_line = f"{index}. {str(question.get('content') or '').strip()}".strip()
            lines.append(anchor_line)
            question_bbox = question.get("bbox") or [0.0, y, 1000.0, y + 10.0]
            blocks.append({"bbox": question_bbox, "text": anchor_line})
            visual_links["question_positions"][index] = {
                "page_num": page_index + 1,
                "bbox": question_bbox,
                "y0": float(question_bbox[1]),
                "y1": float(question_bbox[3]),
            }
            stem_bbox = question.get("stem_bbox") or question.get("bbox")
            stem_region = _region_from_bbox(
                extractor,
                page_index,
                stem_bbox,
                "question_stem",
                warnings=page_warnings,
                fallback_to_full_page=not bool(stem_bbox),
            )
            if stem_region:
                regions.append(stem_region)
            y += 12.0
            question_regions = visual_links["questions"].setdefault(index, [])
            if stem_region:
                question_regions.append(stem_region)
            option_bboxes = {item.get("label"): item.get("bbox") for item in question.get("options", []) or []}
            for label in ["A", "B", "C", "D"]:
                option_value = question.get(f"option_{label.lower()}")
                if not option_value:
                    continue
                option_line = f"{label}. {str(option_value).strip()}"
                lines.append(option_line)
                option_bbox = option_bboxes.get(label) or [0.0, y, 1000.0, y + 10.0]
                blocks.append({"bbox": option_bbox, "text": option_line})
                if option_bboxes.get(label):
                    option_region = _region_from_bbox(
                        extractor,
                        page_index,
                        option_bboxes[label],
                        f"option_{label.lower()}",
                        warnings=page_warnings,
                    )
                    if option_region:
                        regions.append(option_region)
                        question_regions.append(option_region)
                y += 12.0

        for visual in visual_result.get("visuals", []) or []:
            bbox = visual.get("bbox")
            if not bbox:
                continue
            blocks.append({"bbox": bbox, "text": visual.get("caption") or f"[{visual.get('kind') or 'image'}]"})
            visual_region = _region_from_bbox(
                extractor,
                page_index,
                bbox,
                visual.get("kind") or "image",
                warnings=page_warnings,
            )
            if visual_region:
                regions.append(visual_region)
                material_temp_id = str(visual.get("material_temp_id") or "")
                question_index = visual.get("question_index")
                if material_temp_id:
                    material_key = page_material_keys.get(material_temp_id)
                    if material_key:
                        visual_links["materials"].setdefault(material_key, []).append(visual_region)
                elif isinstance(question_index, int):
                    visual_links["questions"].setdefault(question_index, []).append(visual_region)

        _apply_backward_material_links(visual_links, page_num=page_index + 1)

        if not blocks:
            text = extractor.get_page_text(page_index)
            fallback_lines = [line.strip() for line in text.splitlines() if line.strip()]
            for line in fallback_lines:
                lines.append(line)
                blocks.append({"bbox": [0.0, y, 1000.0, y + 10.0], "text": line})
                y += 12.0
            if not fallback_lines:
                lines.append(f"[page {page_index + 1} visual parse unavailable]")
                blocks.append({"bbox": [0.0, 0.0, 1000.0, 10.0], "text": lines[-1]})
                regions.append(_full_page_region(extractor, page_index))
                page_warnings.append("visual_page_fallback_used")
        if _needs_page_fallback_region(page_warnings, visual_result):
            if not any(region.type == "page_fallback" for region in regions):
                regions.append(_full_page_region(extractor, page_index))

        visual_debug["normalized_blocks"] = blocks
        visual_debug["regions"] = [{"type": region.type, "bbox": region.bbox} for region in regions]
        visual_debug["page_warnings"] = sorted(set((visual_result.get("warnings") or []) + page_warnings))
        visual_debug["schema_validation"] = visual_result.get("schema_validation") or {}
        visual_pages.append(visual_debug)
        if _visual_result_failed(visual_result):
            failed_pages.append(page_index + 1)
        parser_warnings.append(
            {
                "page_num": page_index + 1,
                "warnings": visual_debug["page_warnings"],
            }
        )
        _write_visual_page_cache(cache_dir, page_index + 1, visual_result)
        pages.append(
            PageContent(
                page_num=page_index + 1,
                text="\n".join(lines),
                blocks=blocks,
                regions=regions,
            )
        )
    setattr(extractor, "_parser_kernel_visual_pages", visual_pages)
    setattr(extractor, "_parser_kernel_visual_links", visual_links)
    setattr(extractor, "_parser_kernel_warnings", parser_warnings)
    setattr(extractor, "_parser_kernel_failed_pages", failed_pages)
    return pages


def _attach_regions(question: QuestionGroup, pages: list[PageContent]) -> list[Region]:
    regions: list[Region] = []
    for page in pages:
        if page.page_num != question.page_num:
            continue
        for region in page.regions:
            y0 = region.bbox[1]
            if question.y0 <= y0 <= question.y1:
                regions.append(region)
    return regions


def _source_bbox_for_question(extractor: Any, raw: RawQuestion, visual_links: dict[str, Any]) -> list[float] | None:
    position = (visual_links.get("question_positions") or {}).get(raw.index) or {}
    bbox = position.get("bbox")
    if bbox:
        rect, normalized = _bbox_to_page_rect(extractor, raw.page_num - 1, bbox, [])
        if rect is not None and normalized is not None:
            return normalized

    try:
        page_rect = _page_rect(extractor, raw.page_num - 1)
        return [page_rect.x0, float(raw.y0), page_rect.x1, float(raw.y1)]
    except Exception:
        return None


def _split_options(text: str) -> tuple[str, dict[str, str]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    content_lines: list[str] = []
    options: dict[str, str] = {}
    for line in lines:
        option_match = OPTION_RE.match(line)
        if option_match:
            options[option_match.group(1)] = option_match.group(2).strip()
            continue
        content_lines.append(line)
    content = "\n".join(content_lines).strip()
    return content, options


def _region_from_bbox(
    extractor: Any,
    page_index: int,
    bbox: list[float] | None,
    region_type: str,
    *,
    warnings: list[str] | None = None,
    fallback_to_full_page: bool = False,
) -> Region | None:
    warning_sink = warnings if warnings is not None else []
    rect, normalized_bbox = _bbox_to_page_rect(extractor, page_index, bbox, warning_sink)
    if rect is None or normalized_bbox is None:
        if fallback_to_full_page:
            warning_sink.append(f"{region_type}_bbox_missing")
            return _full_page_region(extractor, page_index, region_type=region_type)
        return None
    try:
        base64 = extractor.get_region_screenshot(page_index, rect)
    except Exception:
        warning_sink.append(f"{region_type}_capture_failed")
        if fallback_to_full_page:
            return _full_page_region(extractor, page_index, region_type=region_type)
        return None
    return Region(
        type=region_type,
        bbox=normalized_bbox,
        base64=base64,
    )


def _full_page_region(extractor: Any, page_index: int, region_type: str = "page_fallback") -> Region:
    page = extractor.doc[page_index]
    bbox = [page.rect.x0, page.rect.y0, page.rect.x1, page.rect.y1]
    return Region(
        type=region_type,
        bbox=bbox,
        base64=_get_page_screenshot(
            extractor,
            page_index,
            dpi=VISUAL_PAGE_DPI,
            max_side=VISUAL_PAGE_MAX_SIDE,
        ),
    )


def _region_to_image(region: Region, assignment_confidence: float = 0.7) -> dict[str, Any]:
    return {
        "base64": region.base64,
        "ref": region.type,
        "role": region.type,
        "assignment_confidence": assignment_confidence,
    }


def _material_block_text(content: str) -> str:
    if not content:
        return ""
    if content.startswith("根据以下资料") or content.startswith("根据下列资料") or content.startswith("根据材料"):
        return content
    return f"根据以下资料：\n{content}"


def _bbox_to_page_rect(
    extractor: Any,
    page_index: int,
    bbox: list[float] | None,
    warnings: list[str],
) -> tuple[fitz.Rect | None, list[float] | None]:
    if not bbox or len(bbox) != 4:
        return None, None
    try:
        x0, y0, x1, y1 = [float(value) for value in bbox]
    except (TypeError, ValueError):
        warnings.append("visual_bbox_invalid")
        return None, None
    page_rect = _page_rect(extractor, page_index)
    scale_x, scale_y = _visual_render_scale(extractor, page_index, page_rect)
    rect = fitz.Rect(x0 / scale_x, y0 / scale_y, x1 / scale_x, y1 / scale_y)
    clipped = rect & page_rect
    if clipped.is_empty or clipped.width < 2 or clipped.height < 2:
        warnings.append("visual_bbox_out_of_page")
        return None, None
    normalized = [clipped.x0, clipped.y0, clipped.x1, clipped.y1]
    if any(
        abs(clipped_value - original_value) > VISUAL_BBOX_CLAMP_EPSILON
        for clipped_value, original_value in zip(normalized, [rect.x0, rect.y0, rect.x1, rect.y1])
    ):
        warnings.append("visual_bbox_clamped")
    return clipped, normalized


def _page_rect(extractor: Any, page_index: int) -> fitz.Rect:
    rect = extractor.doc[page_index].rect
    if isinstance(rect, fitz.Rect):
        return rect
    return fitz.Rect(
        float(rect.x0),
        float(rect.y0),
        float(rect.x1),
        float(rect.y1),
    )


def _visual_render_scale(extractor: Any, page_index: int, page_rect: fitz.Rect) -> tuple[float, float]:
    image_size = _cached_visual_render_size(extractor, page_index)
    if page_index not in _visual_render_size_cache(extractor):
        image_size = _get_page_screenshot_size(
            extractor,
            page_index,
            dpi=VISUAL_PAGE_DPI,
            max_side=VISUAL_PAGE_MAX_SIDE,
        )
        _cache_visual_render_size(extractor, page_index, image_size)
    if image_size:
        try:
            width = float(image_size.get("width") or 0)
            height = float(image_size.get("height") or 0)
        except (TypeError, ValueError, AttributeError):
            width = 0.0
            height = 0.0
        if width > 0 and height > 0 and page_rect.width > 0 and page_rect.height > 0:
            return width / page_rect.width, height / page_rect.height
    fallback = VISUAL_PAGE_DPI / 72.0
    return fallback, fallback


def _visual_render_size_cache(extractor: Any) -> dict[int, dict[str, Any] | None]:
    cache = getattr(extractor, "_parser_kernel_visual_render_sizes", None)
    if isinstance(cache, dict):
        return cache
    cache = {}
    setattr(extractor, "_parser_kernel_visual_render_sizes", cache)
    return cache


def _cached_visual_render_size(extractor: Any, page_index: int) -> dict[str, Any] | None:
    return _visual_render_size_cache(extractor).get(page_index)


def _cache_visual_render_size(extractor: Any, page_index: int, image_size: dict[str, Any] | None) -> None:
    _visual_render_size_cache(extractor)[page_index] = image_size


def _parse_page_visual_with_retry(page_b64: str) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    attempt_errors: list[dict[str, Any]] = []
    first_result = _parse_page_visual_with_timeout(page_b64)
    if not _visual_result_retryable(first_result):
        return first_result, attempt_errors, 1

    attempt_errors.append(
        {
            "warnings": list(first_result.get("warnings") or []),
            "schema_validation": first_result.get("schema_validation") or {},
            "error": first_result.get("error"),
        }
    )
    second_result = _parse_page_visual_with_timeout(page_b64)
    return second_result, attempt_errors, 2


def _parse_page_visual_with_timeout(
    page_b64: str,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    timeout = timeout_seconds or _visual_page_timeout_seconds()
    result_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
    error_queue: queue.Queue[Exception] = queue.Queue(maxsize=1)

    def _runner() -> None:
        try:
            result_queue.put(ai_client.parse_page_visual(page_b64))
        except Exception as exc:  # pragma: no cover - exercised via caller behavior
            error_queue.put(exc)

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join(timeout)

    if thread.is_alive():
        return _visual_timeout_result(timeout)

    if not error_queue.empty():
        error = error_queue.get()
        if isinstance(error, TimeoutError):
            return _visual_timeout_result(timeout)
        return _visual_failure_result(str(error))

    if not result_queue.empty():
        return result_queue.get()

    return _visual_failure_result("visual_page_empty_result")


def _visual_result_retryable(result: dict[str, Any]) -> bool:
    warnings = set(str(item) for item in result.get("warnings") or [])
    schema_validation = result.get("schema_validation") or {}
    if "visual_schema_invalid" in warnings:
        return True
    if schema_validation and result.get("page_type") == "unknown":
        return "vision_page_timeout" not in warnings and "visual_model_failed" not in warnings
    return False


def _visual_result_failed(result: dict[str, Any]) -> bool:
    warnings = set(str(item) for item in result.get("warnings") or [])
    return bool(warnings & {"vision_page_timeout", "visual_model_failed"})


def _visual_page_timeout_seconds() -> float:
    raw = os.getenv("PDF_VISUAL_PAGE_TIMEOUT_SECONDS")
    if not raw:
        return DEFAULT_VISUAL_PAGE_TIMEOUT_SECONDS
    try:
        timeout = float(raw)
    except ValueError:
        return DEFAULT_VISUAL_PAGE_TIMEOUT_SECONDS
    return timeout if timeout > 0 else DEFAULT_VISUAL_PAGE_TIMEOUT_SECONDS


def _visual_timeout_result(timeout_seconds: float) -> dict[str, Any]:
    return {
        "page_type": "unknown",
        "materials": [],
        "questions": [],
        "visuals": [],
        "warnings": ["vision_page_timeout"],
        "error": f"page_visual_timeout_after_{timeout_seconds:.1f}s",
        "schema_validation": {"timeout_seconds": timeout_seconds},
        "raw_model_result": {"error": "vision_page_timeout"},
    }


def _visual_failure_result(message: str) -> dict[str, Any]:
    return {
        "page_type": "unknown",
        "materials": [],
        "questions": [],
        "visuals": [],
        "warnings": ["visual_model_failed"],
        "error": message,
        "schema_validation": {"exception": message},
        "raw_model_result": {"error": message},
    }


def _needs_page_fallback_region(page_warnings: list[str], visual_result: dict[str, Any]) -> bool:
    warning_set = set(page_warnings)
    warning_set.update(str(item) for item in visual_result.get("warnings") or [])
    return bool(warning_set & {"vision_page_timeout", "visual_model_failed"})


def _apply_backward_material_links(visual_links: dict[str, Any], *, page_num: int) -> None:
    question_positions = visual_links.get("question_positions", {})
    material_positions = visual_links.get("material_positions", {})
    question_material_ids = visual_links.get("question_material_ids", {})
    question_link_warnings = visual_links.setdefault("question_link_warnings", {})
    visual_link_warnings = visual_links.setdefault("warnings", [])

    page_questions = [
        {"index": index, **position}
        for index, position in question_positions.items()
        if position.get("page_num") == page_num
    ]
    if not page_questions:
        return
    page_questions.sort(key=lambda item: (item["y0"], item["index"]))

    for material_key, position in material_positions.items():
        if position.get("page_num") != page_num:
            continue
        explicit_after = [
            question
            for question in page_questions
            if question_material_ids.get(question["index"]) == material_key and question["y0"] >= position["y0"]
        ]
        if not explicit_after:
            continue
        candidates = [
            question
            for question in page_questions
            if question["y1"] <= position["y0"] and question_material_ids.get(question["index"]) is None
        ]
        if not candidates:
            continue
        candidate = candidates[-1]
        question_material_ids[candidate["index"]] = material_key
        warnings = question_link_warnings.setdefault(candidate["index"], [])
        for warning in ["backward_material_link_low_confidence", "material_range_uncertain"]:
            if warning not in warnings:
                warnings.append(warning)
        visual_link_warnings.append(
            {
                "page_num": page_num,
                "question_index": candidate["index"],
                "material_key": material_key,
                "warning": "backward_material_link_low_confidence",
            }
        )
