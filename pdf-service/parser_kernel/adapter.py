from __future__ import annotations

import os
import base64
import queue
import re
import tempfile
import threading
import json
from pathlib import Path
from typing import Any

import ai_client
from ai_client import PAGE_PARSE_PROMPT
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
DEFAULT_VISUAL_PAGE_TIMEOUT_SECONDS = 120.0
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
    visual_links = getattr(
        extractor,
        "_parser_kernel_visual_links",
        {
            "materials": {},
            "questions": {},
            "question_material_ids": {},
            "material_texts": {},
            "material_groups": {},
            "question_material_group_ids": {},
            "question_link_warnings": {},
            "warnings": [],
            "semantic_question_entries": [],
            "semantic_pages": [],
            "semantic_recrop_plans": [],
            "page_understanding": [],
            "visual_merge_candidates": [],
        },
    )
    parser_warnings = getattr(extractor, "_parser_kernel_warnings", [])
    semantic_questions = visual_links.get("semantic_question_entries") or []
    if semantic_questions:
        questions, materials, raw_questions = _build_questions_from_semantic_payload(
            extractor,
            semantic_questions,
            visual_links=visual_links,
        )
        elements = [page.dict() for page in pages]
        annotated = []
        material_groups = []
        question_groups = []
    else:
        elements = normalize_pages(pages)
        annotated = annotate_semantics(elements)
        material_groups, question_groups = build_groups(annotated)
        raw_questions = groups_to_raw_questions(pages, material_groups, question_groups)
        questions, materials, raw_questions = _build_questions_from_layout_groups(
            extractor=extractor,
            visual_links=visual_links,
            raw_questions=raw_questions,
            material_ids_by_text={},
            material_groups_by_id=visual_links.get("material_groups", {}),
            material_group_ids_by_question=visual_links.get("question_material_group_ids", {}),
            link_warnings=visual_links.get("question_link_warnings", {}),
            element_pages=pages,
        )

    link_warnings = visual_links.get("question_link_warnings", {})
    material_group_ids_by_question = visual_links.get("question_material_group_ids", {})
    material_groups_by_id = visual_links.get("material_groups", {})
    vision_ai_calls = getattr(extractor, "_parser_kernel_vision_ai_calls", [])
    vision_ai_stats = _build_vision_ai_stats(vision_ai_calls)

    _inject_semantic_debug_payload(
        debug_dir=debug_dir,
        total_pages=total_pages,
        visual_pages=getattr(extractor, "_parser_kernel_visual_pages", []),
        failed_pages=getattr(extractor, "_parser_kernel_failed_pages", []),
        failed_page_details=getattr(extractor, "_parser_kernel_failed_page_details", []),
        visual_links=visual_links,
        page_elements_count=len(elements),
        raw_questions_count=len(raw_questions),
        output_questions_count=len(questions),
        materials_count=len(materials),
    )

    write_debug_bundle(
        debug_dir,
        visual_pages=getattr(extractor, "_parser_kernel_visual_pages", []),
        failed_pages={
            "failed_pages": getattr(extractor, "_parser_kernel_failed_pages", []),
            "failed_page_details": getattr(extractor, "_parser_kernel_failed_page_details", []),
        },
        page_elements=elements,
        annotated_elements=annotated,
        material_groups=material_groups,
        question_groups=question_groups,
        raw_questions=raw_questions,
        output_questions=questions,
        output_materials=materials,
        page_understanding=visual_links.get("page_understanding", []),
        semantic_groups=visual_links.get("semantic_question_entries", []),
        recrop_plan=visual_links.get("semantic_recrop_plans", []),
        visual_merge_candidates=visual_links.get("visual_merge_candidates", []),
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
            "vision_ai": vision_ai_stats,
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


def _build_vision_ai_stats(vision_ai_calls: list[dict[str, Any]]) -> dict[str, Any]:
    called_pages: list[int] = []
    qwen_vl_raw_outputs: list[dict[str, Any]] = []
    providers: list[str] = []
    models: list[str] = []
    for call in vision_ai_calls:
        page = _coerce_int(call.get("page"))
        if page is not None:
            called_pages.append(page)
        provider = str(call.get("provider") or "").strip()
        model = str(call.get("model") or "").strip()
        if provider:
            providers.append(provider)
        if model:
            models.append(model)
        qwen_vl_raw_outputs.append(call)
    return {
        "enabled": bool(vision_ai_calls),
        "called_pages": called_pages,
        "calledPages": called_pages,
        "qwen_vl_raw_outputs": qwen_vl_raw_outputs,
        "qwen_vl_prompt": PAGE_PARSE_PROMPT,
        "providers": list(dict.fromkeys(providers)),
        "models": list(dict.fromkeys(models)),
    }


def _dict_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _debug_bbox(value: Any) -> list[float] | None:
    return _coerce_visual_bbox(value)


def _image_size_bbox(image_size: dict[str, Any] | None) -> list[float]:
    width = _safe_float((image_size or {}).get("width")) or 1000.0
    height = _safe_float((image_size or {}).get("height")) or 1000.0
    return [0.0, 0.0, width, height]


def _debug_block(
    *,
    page_no: int,
    kind: str,
    bbox: Any = None,
    text: Any = None,
    label: Any = None,
    source: str | None = None,
    uncertain: bool = False,
    reason: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    block: dict[str, Any] = {
        "page_no": page_no,
        "kind": kind,
        "bbox": _debug_bbox(bbox),
        "text": str(text).strip() if text is not None else None,
        "label": str(label).strip() if label is not None else None,
        "source": source,
        "uncertain": uncertain,
        "reason": reason,
    }
    if extra:
        block.update(extra)
    return block


def _question_no_from_entry(entry: dict[str, Any]) -> int | None:
    for key in ["question_no", "index", "question_index", "no"]:
        number = _coerce_int(entry.get(key))
        if number is not None:
            return number
    return None


def _page_numbers_from_entry(entry: dict[str, Any], fallback_page: int) -> list[int]:
    pages = _coerce_int_list(entry.get("pages"))
    if not pages:
        page = _coerce_int(entry.get("page_num") or entry.get("page_no")) or fallback_page
        pages = [page]
    return sorted(set(pages))


def _blocks_from_visual_group(page_no: int, group: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    group_id = group.get("group_id")
    common = {
        "group_id": group_id,
        "confidence": group.get("confidence"),
        "visual_summary": group.get("visual_summary"),
        "is_fragmented_before_merge": bool(group.get("is_fragmented_before_merge")),
    }
    blocks = {
        "visual": [
            _debug_block(
                page_no=page_no,
                kind=str(group.get("type") or "visual"),
                bbox=group.get("merged_bbox") or group.get("bbox"),
                text=group.get("visual_summary"),
                source="visual_group",
                extra=common,
            )
        ],
        "title": [],
        "table_header": [],
        "legend": [],
        "note": [],
    }
    for field, kind, bucket in [
        ("title_bbox", "chart_title", "title"),
        ("table_header_bbox", "table_header", "table_header"),
        ("legend_bbox", "legend", "legend"),
        ("notes_bbox", "note", "note"),
    ]:
        if group.get(field):
            blocks[bucket].append(
                _debug_block(
                    page_no=page_no,
                    kind=kind,
                    bbox=group.get(field),
                    source="visual_group",
                    extra={"group_id": group_id},
                )
            )
    return blocks


def _build_page_understanding_record(
    *,
    page_num: int,
    visual_result: dict[str, Any],
    source_image_path: str,
    prompt_path: str,
    raw_output_ref: str,
    image_size: dict[str, Any] | None,
) -> dict[str, Any]:
    questions = _dict_items(visual_result.get("semantic_questions")) or _dict_items(visual_result.get("questions"))
    detected_numbers = sorted(
        {
            number
            for number in (_question_no_from_entry(question) for question in questions)
            if number is not None
        }
    )
    stem_blocks: list[dict[str, Any]] = []
    option_blocks: list[dict[str, Any]] = []
    visual_blocks: list[dict[str, Any]] = []
    title_blocks: list[dict[str, Any]] = []
    table_header_blocks: list[dict[str, Any]] = []
    legend_blocks: list[dict[str, Any]] = []
    note_blocks: list[dict[str, Any]] = []
    suspected_cross_page_links: list[dict[str, Any]] = []

    for question in questions:
        question_no = _question_no_from_entry(question)
        if question.get("stem_bbox") or question.get("bbox") or question.get("content"):
            stem_blocks.append(
                _debug_block(
                    page_no=page_num,
                    kind="stem",
                    bbox=question.get("stem_bbox") or question.get("bbox"),
                    text=question.get("content"),
                    label=question_no,
                    source="question",
                    uncertain=not bool(question.get("stem_bbox")),
                    reason=None if question.get("stem_bbox") else "stem_bbox_missing",
                )
            )
        for option in _dict_items(question.get("options")):
            option_blocks.append(
                _debug_block(
                    page_no=page_num,
                    kind="option",
                    bbox=option.get("bbox"),
                    text=option.get("text"),
                    label=option.get("label"),
                    source="question.options",
                    uncertain=not bool(option.get("bbox")),
                    reason=None if option.get("bbox") else "option_bbox_missing",
                )
            )
        for label in ["A", "B", "C", "D"]:
            option_text = question.get(f"option_{label.lower()}")
            if option_text and not any(block.get("label") == label for block in option_blocks):
                option_blocks.append(
                    _debug_block(
                        page_no=page_num,
                        kind="option",
                        text=option_text,
                        label=label,
                        source="question.option_field",
                        uncertain=True,
                        reason="option_bbox_missing",
                    )
                )
        if question.get("is_cross_page") or len(_page_numbers_from_entry(question, page_num)) > 1:
            suspected_cross_page_links.append(
                {
                    "question_no": question_no,
                    "pages": _page_numbers_from_entry(question, page_num),
                    "reason": "model_marked_cross_page_or_multiple_pages",
                }
            )
        for group in _dict_items(question.get("visual_groups")):
            grouped = _blocks_from_visual_group(page_num, group)
            visual_blocks.extend(grouped["visual"])
            title_blocks.extend(grouped["title"])
            table_header_blocks.extend(grouped["table_header"])
            legend_blocks.extend(grouped["legend"])
            note_blocks.extend(grouped["note"])

    for visual in _dict_items(visual_result.get("visuals")):
        visual_blocks.append(
            _debug_block(
                page_no=page_num,
                kind=str(visual.get("kind") or "visual"),
                bbox=visual.get("bbox"),
                text=visual.get("caption"),
                label=visual.get("question_index"),
                source="page_visuals",
                uncertain=not bool(visual.get("bbox")),
                reason=None if visual.get("bbox") else "visual_bbox_missing",
                extra={
                    "group_id": visual.get("group_id"),
                    "belongs_to_question": visual.get("belongs_to_question"),
                },
            )
        )

    uncertain_regions: list[dict[str, Any]] = []
    failed = _visual_result_failed(visual_result)
    failure_reason = _classify_vision_failure(visual_result)
    warnings = [str(item) for item in visual_result.get("warnings") or []]
    if failed:
        fallback_block = _debug_block(
            page_no=page_num,
            kind="unknown_full_page_visual",
            bbox=_image_size_bbox(image_size),
            source="parser_fallback",
            uncertain=True,
            reason=visual_result.get("error") or "vision_ai_failed",
        )
        if not visual_blocks:
            visual_blocks.append(fallback_block)
        uncertain_regions.append(fallback_block)

    page_analysis = visual_result.get("page_analysis") if isinstance(visual_result.get("page_analysis"), dict) else {}
    if page_analysis.get("cross_page_needed"):
        suspected_cross_page_links.append(
            {
                "question_no": None,
                "pages": [page_num, page_num + 1],
                "reason": "page_analysis_cross_page_needed",
            }
        )

    return {
        "page_no": page_num,
        "provider": visual_result.get("_vision_provider"),
        "model": visual_result.get("_vision_model"),
        "source_image_path": source_image_path,
        "prompt_path": prompt_path,
        "raw_output_ref": raw_output_ref,
        "detected_question_numbers": detected_numbers,
        "stem_blocks": stem_blocks,
        "option_blocks": option_blocks,
        "visual_blocks": visual_blocks,
        "chart_title_blocks": title_blocks,
        "table_header_blocks": table_header_blocks,
        "legend_blocks": legend_blocks,
        "note_blocks": note_blocks,
        "suspected_cross_page_links": suspected_cross_page_links,
        "uncertain_regions": uncertain_regions,
        "confidence": 0.0 if failed else float(page_analysis.get("confidence") or 0.6),
        "reason": visual_result.get("error") or (failure_reason if failed else "vision_ai_page_understanding"),
        "failureReason": failure_reason,
        "recommendedFix": _vision_failure_recommended_fix(failure_reason),
        "coarse_fallback": bool(failed),
        "fallback_evidence": "full_page_image" if failed else None,
        "can_synthesize_question": bool(detected_numbers),
        "page_warnings": warnings,
        "page_analysis": page_analysis,
        "schema_validation": visual_result.get("schema_validation") or {},
        "vision_call_result": visual_result.get("vision_call_result") or {},
    }


def _group_text(blocks: list[dict[str, Any]]) -> str:
    return "\n".join(str(block.get("text") or "").strip() for block in blocks if block.get("text")).strip()


def _debug_group(blocks: list[dict[str, Any]], *, complete: bool | None = None) -> dict[str, Any]:
    bboxes = [block.get("bbox") for block in blocks if block.get("bbox")]
    return {
        "blocks": blocks,
        "text": _group_text(blocks),
        "bbox": _union_visual_bboxes(bboxes),
        "complete": complete,
    }


def _build_semantic_debug_groups(visual_links: dict[str, Any]) -> list[dict[str, Any]]:
    raw_entries = _dict_items(visual_links.get("semantic_question_entries"))
    groups: list[dict[str, Any]] = []
    if raw_entries:
        for entry in raw_entries:
            fallback_page = _coerce_int(entry.get("page_num") or entry.get("page_no")) or 1
            pages = _page_numbers_from_entry(entry, fallback_page)
            page_no = pages[0] if pages else fallback_page
            stem_blocks = [
                _debug_block(
                    page_no=page_no,
                    kind="stem",
                    bbox=entry.get("stem_bbox") or entry.get("bbox"),
                    text=entry.get("content"),
                    label=_question_no_from_entry(entry),
                    source="semantic_question",
                    uncertain=not bool(entry.get("stem_bbox") or entry.get("bbox")),
                    reason=None if entry.get("stem_bbox") or entry.get("bbox") else "stem_bbox_missing",
                )
            ]
            option_blocks = [
                _debug_block(
                    page_no=page_no,
                    kind="option",
                    bbox=option.get("bbox"),
                    text=option.get("text"),
                    label=option.get("label"),
                    source="semantic_question.options",
                    uncertain=not bool(option.get("bbox")),
                    reason=None if option.get("bbox") else "option_bbox_missing",
                )
                for option in _dict_items(entry.get("options"))
            ]
            visual_blocks: list[dict[str, Any]] = []
            title_blocks: list[dict[str, Any]] = []
            table_header_blocks: list[dict[str, Any]] = []
            legend_blocks: list[dict[str, Any]] = []
            note_blocks: list[dict[str, Any]] = []
            for visual_group in _dict_items(entry.get("visual_groups")):
                grouped = _blocks_from_visual_group(page_no, visual_group)
                visual_blocks.extend(grouped["visual"])
                title_blocks.extend(grouped["title"])
                table_header_blocks.extend(grouped["table_header"])
                legend_blocks.extend(grouped["legend"])
                note_blocks.extend(grouped["note"])
            content_quality = entry.get("content_quality") if isinstance(entry.get("content_quality"), dict) else {}
            question_quality = entry.get("question_quality") if isinstance(entry.get("question_quality"), dict) else {}
            risk_flags = list(
                dict.fromkeys(
                    [
                        *[str(item) for item in content_quality.get("risk_flags") or []],
                        *[str(item) for item in question_quality.get("review_reasons") or []],
                    ]
                )
            )
            uncertain = bool(content_quality.get("needs_review") or question_quality.get("needs_review"))
            bboxes = [
                block.get("bbox")
                for block in [
                    *stem_blocks,
                    *option_blocks,
                    *visual_blocks,
                    *title_blocks,
                    *table_header_blocks,
                    *legend_blocks,
                    *note_blocks,
                ]
                if block.get("bbox")
            ]
            groups.append(
                {
                    "question_no": _question_no_from_entry(entry),
                    "source_page_start": min(pages) if pages else page_no,
                    "source_page_end": max(pages) if pages else page_no,
                    "stem_group": _debug_group(stem_blocks, complete=content_quality.get("stem_complete")),
                    "options_group": _debug_group(option_blocks, complete=content_quality.get("options_complete")),
                    "visual_group": _debug_group(visual_blocks, complete=content_quality.get("visual_complete")),
                    "title_group": _debug_group(title_blocks, complete=bool(title_blocks)),
                    "table_header_group": _debug_group(table_header_blocks, complete=bool(table_header_blocks)),
                    "legend_group": _debug_group(legend_blocks, complete=bool(legend_blocks)),
                    "notes_group": _debug_group(note_blocks, complete=bool(note_blocks)),
                    "bbox_list": bboxes,
                    "grouping_confidence": float(entry.get("confidence") or 0.6),
                    "grouping_reason": "semantic_question_from_page_understanding",
                    "risk_flags": risk_flags,
                    "uncertain": uncertain,
                }
            )
        return groups

    for page in _dict_items(visual_links.get("page_understanding")):
        page_no = _coerce_int(page.get("page_no") or page.get("page_num")) or 1
        visual_blocks = _dict_items(page.get("visual_blocks"))
        bboxes = [block.get("bbox") for block in visual_blocks if block.get("bbox")]
        risk_flags = list(
            dict.fromkeys(
                [
                    *[str(item) for item in page.get("page_warnings") or []],
                    "question_number_unknown",
                    "need_manual_fix",
                ]
            )
        )
        groups.append(
            {
                "question_no": None,
                "source_page_start": page_no,
                "source_page_end": page_no,
                "stem_group": _debug_group(_dict_items(page.get("stem_blocks")), complete=False),
                "options_group": _debug_group(_dict_items(page.get("option_blocks")), complete=False),
                "visual_group": _debug_group(visual_blocks, complete=False),
                "title_group": _debug_group(_dict_items(page.get("chart_title_blocks")), complete=False),
                "table_header_group": _debug_group(_dict_items(page.get("table_header_blocks")), complete=False),
                "legend_group": _debug_group(_dict_items(page.get("legend_blocks")), complete=False),
                "notes_group": _debug_group(_dict_items(page.get("note_blocks")), complete=False),
                "bbox_list": bboxes,
                "grouping_confidence": 0.0,
                "grouping_reason": page.get("reason") or "parser_fallback_uncertain_page_group",
                "risk_flags": risk_flags,
                "uncertain": True,
            }
        )
    return groups


def _collect_required_regions(group: dict[str, Any]) -> list[dict[str, Any]]:
    regions: list[dict[str, Any]] = []
    for field, kind in [
        ("stem_group", "stem"),
        ("options_group", "options"),
        ("visual_group", "visual"),
        ("title_group", "chart_title"),
        ("table_header_group", "table_header"),
        ("legend_group", "legend"),
        ("notes_group", "notes"),
    ]:
        value = group.get(field) if isinstance(group.get(field), dict) else {}
        for block in _dict_items(value.get("blocks")):
            if block.get("bbox"):
                regions.append({"kind": kind, "bbox": block.get("bbox"), "page_no": block.get("page_no")})
    return regions


def _build_recrop_debug_plan(semantic_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    plans: list[dict[str, Any]] = []
    for group in semantic_groups:
        required_regions = _collect_required_regions(group)
        bboxes = [region.get("bbox") for region in required_regions if region.get("bbox")]
        crop_bbox = _union_visual_bboxes(bboxes)
        visual_group = group.get("visual_group") if isinstance(group.get("visual_group"), dict) else {}
        title_group = group.get("title_group") if isinstance(group.get("title_group"), dict) else {}
        table_header_group = group.get("table_header_group") if isinstance(group.get("table_header_group"), dict) else {}
        visual_blocks = _dict_items(visual_group.get("blocks"))
        has_visual = bool(visual_blocks)
        has_title = bool(_dict_items(title_group.get("blocks")))
        has_table_header = bool(_dict_items(table_header_group.get("blocks")))
        risk_flags = [str(item) for item in group.get("risk_flags") or []]
        if has_visual and not has_title:
            risk_flags.append("chart_title_missing_or_unlocalized")
        if has_visual and not has_table_header:
            risk_flags.append("table_header_missing_or_unlocalized")
        need_manual_fix = bool(group.get("uncertain") or not crop_bbox or (has_visual and (not has_title or not has_table_header)))
        if need_manual_fix:
            risk_flags.append("need_manual_fix")
        source_start = int(group.get("source_page_start") or 1)
        source_end = int(group.get("source_page_end") or source_start)
        plans.append(
            {
                "question_no": group.get("question_no"),
                "source_pages": list(range(source_start, source_end + 1)),
                "crop_bbox": crop_bbox,
                "required_include_regions": required_regions,
                "padding_top": 24,
                "padding_bottom": 24,
                "padding_left": 24,
                "padding_right": 24,
                "must_keep_chart_title": has_visual,
                "must_keep_table_header": has_visual,
                "must_keep_legend": has_visual,
                "must_keep_axis_labels": has_visual,
                "must_keep_notes": has_visual,
                "merge_visual_blocks": len(visual_blocks) > 1 or any(block.get("is_fragmented_before_merge") for block in visual_blocks),
                "risk_flags": list(dict.fromkeys(risk_flags)),
                "recrop_confidence": 0.0 if need_manual_fix else float(group.get("grouping_confidence") or 0.6),
                "recrop_reason": group.get("grouping_reason") or ("need_manual_fix" if need_manual_fix else "semantic_group_union_bbox"),
                "need_manual_fix": need_manual_fix,
            }
        )
    return plans


def _build_questions_from_semantic_payload(
    extractor: Any,
    semantic_questions: list[dict[str, Any]],
    visual_links: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    visual_links = visual_links or {}
    question_map: dict[int, dict[str, Any]] = {}
    all_raw_questions: list[dict[str, Any]] = []
    materials_by_text: dict[str, str] = {}
    materials: list[dict[str, Any]] = []
    questions: list[dict[str, Any]] = []
    seen_signatures: dict[str, int] = {}
    semantic_visual_index: dict[int, list[dict[str, Any]]] = {}

    for entry in semantic_questions:
        if not isinstance(entry, dict):
            continue
        index = _coerce_int(entry.get("index") or entry.get("question_no"))
        if index is None:
            continue
        question = question_map.setdefault(index, _empty_semantic_bucket(index))

        if entry.get("content"):
            question["content"] = _strip_placeholder_text(str(entry.get("content")))
        question["question_type"] = str(entry.get("question_type") or question["question_type"]).strip() or question["question_type"]
        question["pages"] = _merge_unique_ints(question.get("pages", []), entry.get("pages"))
        question["is_cross_page"] = bool(question.get("is_cross_page") or entry.get("is_cross_page"))

        direct_keys = ("option_a", "option_b", "option_c", "option_d")
        for direct_key in direct_keys:
            label = direct_key[-1].upper()
            value = entry.get(direct_key)
            if isinstance(value, str):
                value = _strip_placeholder_text(value).strip()
                if value:
                    question["options"][label] = value

        for option in entry.get("options") or []:
            if not isinstance(option, dict):
                continue
            label = str(option.get("label") or "").strip().upper()
            if label not in {"A", "B", "C", "D"}:
                continue
            text = _strip_placeholder_text(str(option.get("text") or option.get("content") or "")).strip()
            if text:
                question["options"][label] = text

        for field in [
            "content_quality",
            "question_quality",
            "capture_plan",
            "understanding",
            "answer_suggestion",
            "analysis_suggestion",
            "ai_audit",
        ]:
            question[field] = _merge_dict(question[field], _as_dict(entry.get(field)))

        question["content_quality"]["needs_review"] = bool(
            question["content_quality"].get("needs_review") or entry.get("content_quality", {}).get("needs_review")
        )
        question["question_quality"]["needs_review"] = bool(
            question["question_quality"].get("needs_review") or entry.get("question_quality", {}).get("needs_review")
        )

        if not entry.get("visual_groups") and visual_links.get("questions"):
            cached_regions = visual_links.get("questions", {}).get(index, [])
            synthesized_visual_groups = _synthesize_visual_groups_from_regions(
                extractor,
                question_no=index,
                regions=cached_regions,
            )
            if synthesized_visual_groups:
                question["parse_warnings"].append("visual_groups_synthesized_from_region_cache")
                semantic_visual_index[index] = synthesized_visual_groups

        for visual_group in entry.get("visual_groups") or []:
            if isinstance(visual_group, dict):
                question["visual_groups"].append(visual_group)
        for visual_group in semantic_visual_index.get(index) or []:
            question["visual_groups"].append(visual_group)

        material_ids = entry.get("material_temp_ids") or entry.get("material_temp_id")
        for material_id in _coerce_str_list(material_ids):
            if material_id and material_id not in question["material_temp_ids"]:
                question["material_temp_ids"].append(material_id)

        page_num = _coerce_int(entry.get("page_num"))
        if page_num is None:
            page_num = _coerce_int(entry.get("source_page_num")) or 1
        if page_num is not None and page_num not in question["question_pages"]:
            question["question_pages"].append(page_num)

        question["question_regions"].append(
            {
                "page_num": page_num,
                "stem_bbox": entry.get("stem_bbox"),
                "options_bbox": entry.get("options_bbox"),
                "capture_plan": entry.get("capture_plan"),
                "risk_flags": _coerce_str_list(entry.get("risk_flags") or entry.get("risk_flags_new")),
                "question_type": entry.get("question_type") or question["question_type"],
                "content_quality": _as_dict(entry.get("content_quality")),
                "question_quality": _as_dict(entry.get("question_quality")),
            }
        )

        question["parse_warnings"].extend(_coerce_str_list(entry.get("parse_warnings")))
        if _coerce_bool(entry.get("is_incomplete", False)):
            question["parse_warnings"].append("question_incomplete_by_ai")

        if not question["pages"] and page_num is not None:
            question["pages"] = [page_num]

        if entry.get("material_text"):
            question["material_text"] = str(entry.get("material_text"))
        for material_text in _coerce_str_list(entry.get("material_texts")):
            all_raw_questions.append({"question_no": index, "material_text": material_text})

        question["raw_entries"].append(entry)

    for index in sorted(question_map):
        question = question_map[index]
        options = question["options"]

        page_min = min(question["question_pages"]) if question["question_pages"] else index
        page_max = max(question["question_pages"]) if question["question_pages"] else page_min
        page_no = page_min
        source_pages = sorted(set(question["pages"] or question["question_pages"] or [page_no]))

        all_raw_questions.append(
            {
                "index": index,
                "text": question["content"],
                "page_num": page_no,
                "y0": 0,
                "y1": 0,
            }
        )

        parse_warnings = list(dict.fromkeys(question["parse_warnings"]))
        question_regions, visual_region_count = _build_semantic_question_regions(
            extractor=extractor,
            question_no=index,
            entry=question,
            parse_warnings=parse_warnings,
        )

        content_quality = question.get("content_quality") or {}
        question_quality = question.get("question_quality") or {}
        if not content_quality.get("stem_complete", True):
            parse_warnings.append("semantic_stem_incomplete")
        if not content_quality.get("options_complete", True):
            parse_warnings.append("semantic_options_incomplete")
        if not question_quality.get("visual_context_complete", True):
            parse_warnings.append("semantic_visual_incomplete")
        if question.get("is_cross_page"):
            parse_warnings.append("question_cross_page")

        answer_suggestion = _normalize_answer_suggestion(question.get("answer_suggestion") or {})
        analysis_suggestion = _normalize_analysis_suggestion(question.get("analysis_suggestion") or {})
        quality = question.get("question_quality") or {}
        ai_audit = _merge_dict(
            {
                "status": "warning" if quality.get("needs_review") else "passed",
                "verdict": "需复核" if quality.get("needs_review") else "可通过",
                "summary": "",
                "needs_review": bool(quality.get("needs_review")),
                "risk_flags": [],
                "review_reasons": [],
            },
            question.get("ai_audit") or {},
        )

        if quality.get("needs_review"):
            parse_warnings.append("question_quality_review_required")

        material_text = question.get("material_text")
        material_temp_id: str | None = None
        if material_text:
            material_temp_id = materials_by_text.get(material_text)
            if material_temp_id is None:
                material_temp_id = f"m_{len(materials) + 1}"
                materials_by_text[material_text] = material_temp_id
                materials.append(
                    {
                        "temp_id": material_temp_id,
                        "content": material_text,
                        "images": [],
                    }
                )
        if question["material_temp_ids"]:
            material_temp_id = question["material_temp_ids"][0]

        question["material_temp_ids"] = _coerce_unique(question["material_temp_ids"])

        material_group = {
            "question_no": index,
            "question_indexes": [index],
            "question_ids": [f"q{index:03d}"],
            "warnings": list(dict.fromkeys(parse_warnings)),
        }

        visual_confidence = _safe_float(quality.get("visual_confidence"))
        if visual_confidence is None:
            visual_conf_vals = [
                _safe_float(item.get("confidence")) for item in (question.get("visual_groups") or []) if isinstance(item, dict)
            ]
            visual_conf_vals = [value for value in visual_conf_vals if value is not None]
            if visual_conf_vals:
                visual_confidence = sum(visual_conf_vals) / len(visual_conf_vals)

        question_type_raw = str(question.get("question_type") or "single").lower()
        question_type = "judge" if ("judge" in question_type_raw or "判断" in question_type_raw) else "single"
        has_visual_context = bool(question_regions)
        source_bbox = _union_visual_bboxes([region.bbox for region in question_regions])

        visuals_for_question = [_region_to_image(region, assignment_confidence=0.95) for region in question_regions]
        visual_summary = _visual_summary_from_regions(
            regions=question_regions,
            fallback_groups=_coerce_str_list(question.get("visual_groups")) or question.get("visual_groups") or [],
        )

        risk_flags = _coerce_unique(
            _coerce_str_list(quality.get("risk_flags"))
            + _coerce_str_list(question["content_quality"].get("risk_flags"))
            + _coerce_str_list(parse_warnings)
        )

        result = {
            "index": index,
            "type": question_type,
            "content": question["content"],
            "option_a": options.get("A"),
            "option_b": options.get("B"),
            "option_c": options.get("C"),
            "option_d": options.get("D"),
            "options": options,
            "answer": answer_suggestion.get("answer"),
            "analysis": analysis_suggestion.get("text"),
            "needs_review": bool(parse_warnings),
            "material_text": material_text,
            "material_temp_id": material_temp_id,
            "material_group_id": f"sg_{index}",
            "material_group_question_indexes": [index],
            "material_group_confidence": None,
            "material_group_reason": "semantic_group_by_qwen_vl",
            "shared_material": False,
            "images": _dedupe_images(visuals_for_question),
            "image_refs": [str(image.get("ref") or "") for image in visuals_for_question if image.get("ref")],
            "visual_refs": [_region_to_visual_ref(region) for region in question_regions],
            "page_num": page_no,
            "page_range": [page_min, page_max],
            "source_page_start": page_min,
            "source_page_end": page_max,
            "source_bbox": source_bbox,
            "source_anchor_text": f"{index}.",
            "source_confidence": 0.75 if has_visual_context else 0.45,
            "source": "parser_kernel_semantic",
            "parse_warnings": sorted(set(parse_warnings)),
            "visual_summary": visual_summary,
            "visual_confidence": visual_confidence,
            "visual_parse_status": "success" if visual_region_count else "partial",
            "visual_error": None if visual_region_count else "未检测到完整图表或图形",
            "visual_risk_flags": risk_flags,
            "has_visual_context": has_visual_context,
            "answer_unknown_reason": answer_suggestion.get("answer_unknown_reason"),
            "analysis_unknown_reason": analysis_suggestion.get("analysis_unknown_reason"),
            "ai_audit_status": ai_audit.get("status") or "warning",
            "ai_audit_verdict": ai_audit.get("verdict") or "需复核",
            "ai_audit_summary": ai_audit.get("summary") or "",
            "ai_can_understand_question": bool(
                question["content"] and all(options.get(label) for label in ("A", "B", "C", "D"))
            ),
            "ai_can_solve_question": bool(answer_suggestion.get("answer") and answer_suggestion.get("answer") != "unknown"),
            "ai_reviewed_before_human": True,
            "ai_review_error": None,
            "question_quality": quality,
            "question_pages": source_pages,
            "is_cross_page": question.get("is_cross_page", False),
            "capture_plan": question.get("capture_plan"),
            "understanding": question.get("understanding"),
        }
        result_signature = _question_signature(
            question_text=result["content"],
            options=options,
            question_type=result["type"],
            source_pages=source_pages,
            has_visual_context=bool(question_regions),
            image_count=len(visuals_for_question),
        )
        if result_signature:
            duplicate_of = seen_signatures.get(result_signature)
            if duplicate_of is not None:
                parse_warnings.append(f"duplicate_question_signature_detected:{duplicate_of}")
                quality["duplicate_suspected"] = True
                if question["content"]:
                    all_raw_questions.append({"index": index, "text": result["content"]})
                continue
            seen_signatures[result_signature] = index
        result.update(material_group)
        questions.append(result)
        all_raw_questions.append({"index": index, "text": result["content"]})

    return questions, materials, all_raw_questions


def _build_questions_from_layout_groups(
    extractor: Any,
    visual_links: dict[str, Any],
    raw_questions: list[RawQuestion],
    material_ids_by_text: dict[str, str],
    material_groups_by_id: dict[str, Any],
    material_group_ids_by_question: dict[int, str],
    link_warnings: dict[int, list[str]],
    element_pages: list[PageContent] | None = None,  # noqa: ARG001
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    del element_pages
    materials: list[dict[str, Any]] = []
    questions: list[dict[str, Any]] = []
    all_raw_questions: list[dict[str, Any]] = []

    for raw in raw_questions:
        all_raw_questions.append(
            {
                "index": raw.index,
                "text": raw.text,
                "page_num": raw.page_num,
                "y0": raw.y0,
                "y1": raw.y1,
            }
        )

        content, options = _split_options(raw.text)
        effective_material_id = visual_links.get("question_material_ids", {}).get(raw.index) or raw.material_id
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

        linked_regions = list(raw.images)
        if effective_material_id:
            linked_regions.extend(visual_links.get("materials", {}).get(effective_material_id, []))
        linked_regions.extend(visual_links.get("questions", {}).get(raw.index, []))

        question_regions: list[Region] = []
        for region in linked_regions:
            if not _has_matching_region(question_regions, region):
                question_regions.append(region)

        question_warnings = list(getattr(raw, "warnings", []) or [])
        question_warnings.extend(link_warnings.get(raw.index, []))
        material_group_id = material_group_ids_by_question.get(raw.index)
        material_group = material_groups_by_id.get(material_group_id) if material_group_id else None
        if material_group:
            question_warnings.extend(material_group.get("warnings") or [])

        if not content:
            question_warnings.append("question_content_empty")

        source_bbox = _source_bbox_for_question(extractor, raw, visual_links)
        question_images = [_region_to_image(region) for region in question_regions]
        visual_refs = [_region_to_visual_ref(region) for region in question_regions]
        image_refs = [str(image.get("ref") or "") for image in question_images if image.get("ref")]

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
                "material_group_id": material_group_id,
                "material_group_question_indexes": (material_group or {}).get("question_indexes") or [],
                "material_group_confidence": (material_group or {}).get("confidence"),
                "material_group_reason": (material_group or {}).get("link_reason"),
                "shared_material": bool(material_group and len(material_group.get("question_indexes") or []) > 1),
                "images": question_images,
                "image_refs": image_refs,
                "visual_refs": visual_refs,
                "page_num": raw.page_num,
                "page_range": [raw.page_num, raw.page_num],
                "source_page_start": raw.page_num,
                "source_page_end": raw.page_num,
                "source_bbox": source_bbox,
                "source_anchor_text": f"{raw.index}.",
                "source_confidence": 0.7 if source_bbox else 0.4,
                "source": "parser_kernel_scanned",
                "parse_warnings": sorted(set(question_warnings)),
                "visual_summary": None,
                "visual_confidence": None,
                "visual_parse_status": "partial" if question_images else "skipped",
                "visual_error": None,
                "visual_risk_flags": question_warnings,
                "has_visual_context": bool(question_images),
                "answer_unknown_reason": None,
                "analysis_unknown_reason": None,
                "ai_audit_status": "warning",
                "ai_audit_verdict": "需复核",
                "ai_audit_summary": "layout_fallback_result",
                "ai_can_understand_question": bool(content and options),
                "ai_can_solve_question": False,
                "ai_reviewed_before_human": True,
                "ai_review_error": None,
                "question_quality": {
                    "question_complete": bool(content and options),
                    "visual_context_complete": bool(question_images),
                    "needs_review": True,
                    "risk_flags": question_warnings,
                },
            }
        )

    return questions, materials, all_raw_questions


def _synthesize_visual_groups_from_regions(
    extractor: Any,
    question_no: int,
    regions: list[Any],
) -> list[dict[str, Any]]:
    del extractor
    grouped: dict[str, list[Any]] = {}
    for region in regions:
        if not isinstance(region, Region):
            continue
        if region.type not in {"chart", "table", "image", "visual", "diagram", "material"}:
            continue
        group_id = region.same_visual_group_id or f"{region.type}:{question_no}:{len(grouped)}"
        grouped.setdefault(group_id, []).append(region)

    if not grouped:
        return []

    result: list[dict[str, Any]] = []
    for idx, (group_id, members) in enumerate(grouped.items(), start=1):
        if not members:
            continue
        member_bboxes = [_coerce_visual_bbox(getattr(member, "bbox", None)) for member in members]
        merged_bbox = _union_visual_bboxes(member_bboxes)
        if not merged_bbox:
            continue
        first_type = str(members[0].type or "image").strip().lower() or "image"
        region_type = "image"
        if first_type == "chart":
            region_type = "chart"
        elif first_type == "table":
            region_type = "table"
        elif first_type == "diagram":
            region_type = "diagram"
        captions = [str(getattr(member, "caption", "") or "").strip() for member in members]
        caption_text = next((item for item in captions if item), None)
        title_included = bool(caption_text)
        if not title_included and captions:
            title_included = any("标题" in item for item in captions)

        result.append(
            {
                "group_id": group_id if group_id else f"auto_vg_{question_no}_{idx}",
                "type": region_type,
                "member_blocks": [f"{idx}_{offset}" for offset, _ in enumerate(members)],
                "merged_bbox": merged_bbox,
                "title_included": title_included,
                "legend_included": False,
                "axis_included": False,
                "table_header_included": False,
                "is_fragmented_before_merge": len(members) > 1,
                "belongs_to_question": True,
                "link_reason": "synthesized_from_region_cache",
                "visual_summary": str(caption_text) if caption_text else "",
                "confidence": 0.7,
                "same_visual_group_id": group_id,
            }
        )

    return result


def _build_semantic_question_regions(
    extractor: Any,
    question_no: int,
    entry: dict[str, Any],
    parse_warnings: list[str],
) -> tuple[list[Region], int]:
    regions: list[Region] = []
    for region in entry.get("question_regions") or []:
        if not isinstance(region, dict):
            continue
        page_no = _coerce_int(region.get("page_num")) or 1
        page_index = max(page_no - 1, 0)
        capture_plan = _as_dict(region.get("capture_plan") or entry.get("capture_plan"))
        padding = _safe_float(capture_plan.get("padding")) or 12.0

        stem_bbox = _coerce_visual_bbox(region.get("stem_bbox"))
        if stem_bbox:
            stem_region = _region_from_bbox(
                extractor,
                page_index,
                _expand_bbox(stem_bbox, padding, extractor, page_index),
                "question_stem",
                warnings=parse_warnings,
            )
            if stem_region:
                stem_region.type = "question_stem"
                stem_region.assignment_confidence = 0.88
                stem_region.visual_parse_status = "success"
                stem_region.visual_summary = "question stem"
                stem_region.visual_confidence = 0.88
                stem_region.visual_error = None
                stem_region.belongs_to_question = True
                stem_region.linked_question_no = question_no
                stem_region.linked_question_id = f"q{question_no:03d}"
                stem_region.linked_by = "semantic_capture_plan"
                stem_region.link_reason = "semantic-question-stem"
                stem_region.visual_parse_input = {
                    "source": "semantic_capture_plan",
                    "page_num": page_no,
                    "question_no": question_no,
                }
                regions.append(stem_region)

        options_bbox = _coerce_visual_bbox(region.get("options_bbox"))
        if options_bbox:
            options_region = _region_from_bbox(
                extractor,
                page_index,
                _expand_bbox(options_bbox, padding, extractor, page_index),
                "question_options",
                warnings=parse_warnings,
            )
            if options_region:
                options_region.type = "question_options"
                options_region.assignment_confidence = 0.86
                options_region.visual_parse_status = "success"
                options_region.visual_summary = "question options"
                options_region.visual_confidence = 0.86
                options_region.visual_error = None
                options_region.belongs_to_question = True
                options_region.linked_question_no = question_no
                options_region.linked_question_id = f"q{question_no:03d}"
                options_region.linked_by = "semantic_capture_plan"
                options_region.link_reason = "semantic-question-options"
                options_region.visual_parse_input = {
                    "source": "semantic_capture_plan",
                    "page_num": page_no,
                    "question_no": question_no,
                }
                regions.append(options_region)

    for visual_group in entry.get("visual_groups") or []:
        if not isinstance(visual_group, dict):
            continue
        source_page_no = _coerce_int(visual_group.get("page_num")) or 1
        page_index = max(source_page_no - 1, 0)
        group_type = str(visual_group.get("type") or "image").strip().lower() or "image"
        region_type = "image"
        if group_type == "chart":
            region_type = "chart"
        elif group_type == "table":
            region_type = "table"
        elif group_type == "diagram":
            region_type = "diagram"

        group_bbox = _coerce_visual_bbox(visual_group.get("merged_bbox") or visual_group.get("bbox"))
        if not group_bbox:
            continue
        context_bboxes = [
            visual_group.get("title_bbox"),
            visual_group.get("legend_bbox"),
            visual_group.get("axis_bbox"),
            visual_group.get("table_header_bbox"),
            visual_group.get("notes_bbox"),
        ]
        union_bbox = _expand_with_related_bboxes(group_bbox, context_bboxes, extractor, page_index)
        if union_bbox:
            group_bbox = union_bbox
        if visual_group.get("is_fragmented_before_merge"):
            parse_warnings.append("visual_group_fragmented")
        region_bbox = _expand_bbox(group_bbox, 16.0, extractor, page_index)
        if not region_bbox:
            continue
        visual_region = _region_from_bbox(
            extractor,
            page_index,
            region_bbox,
            region_type,
            warnings=parse_warnings,
            caption=_strip_placeholder_text(str(visual_group.get("visual_summary") or "")),
            same_visual_group_id=str(visual_group.get("group_id") or ""),
        )
        if visual_region:
            visual_region.assignment_confidence = _safe_float(visual_group.get("confidence")) or 0.78
            visual_region.visual_parse_status = "success"
            visual_region.visual_summary = _strip_placeholder_text(str(visual_group.get("visual_summary") or ""))
            visual_region.visual_confidence = _safe_float(visual_group.get("confidence"))
            visual_region.visual_error = None
            visual_region.belongs_to_question = bool(visual_group.get("belongs_to_question", True))
            visual_region.linked_question_no = question_no
            visual_region.linked_question_id = f"q{question_no:03d}"
            visual_region.linked_by = "semantic_visual_group"
            visual_region.link_reason = str(visual_group.get("link_reason") or "semantic-group")
            visual_region.visual_parse_input = {
                "source": "semantic_visual_group",
                "page_num": source_page_no,
                "question_no": question_no,
                "group_id": visual_group.get("group_id"),
            }
            regions.append(visual_region)

    return _dedupe_regions(regions), len([region for region in regions if region.type != "question_stem"])


def _expand_bbox(
    bbox: list[float],
    padding: float,
    extractor: Any,
    page_index: int,
) -> list[float]:
    if not bbox:
        return []
    try:
        left, top, right, bottom = [float(item) for item in bbox]
    except (TypeError, ValueError):
        return []
    page_rect = _page_rect(extractor, page_index)
    left = max(0.0, left - padding)
    top = max(0.0, top - padding)
    right = min(float(page_rect.width), right + padding)
    bottom = min(float(page_rect.height), bottom + padding)
    if right <= left or bottom <= top:
        return []
    return [left, top, right, bottom]


def _expand_with_related_bboxes(
    base_bbox: list[float],
    related_bboxes: list[Any],
    extractor: Any,
    page_index: int,
    default_padding: float = 8.0,
) -> list[float]:
    coerce = [ _coerce_visual_bbox(base_bbox) ]
    for item in related_bboxes:
        value = _coerce_visual_bbox(item)
        if value and _bboxes_touch_or_close(base_bbox, value, extractor, page_index):
            coerce.append(value)
    merged = _union_visual_bboxes(coerce)
    if not merged:
        return base_bbox
    if default_padding <= 0:
        return merged
    return _expand_bbox(merged, default_padding, extractor, page_index) or merged


def _bboxes_touch_or_close(
    base_bbox: list[float],
    related_bbox: list[float],
    extractor: Any,
    page_index: int,
) -> bool:
    if not base_bbox or not related_bbox:
        return False
    try:
        left1, top1, right1, bottom1 = [float(item) for item in base_bbox]
        left2, top2, right2, bottom2 = [float(item) for item in related_bbox]
    except (TypeError, ValueError):
        return False

    page_height = _visual_page_height(extractor, page_index)
    page_width = _visual_page_width(extractor, page_index)
    if page_height <= 0 or page_width <= 0:
        return True

    y_gap = max(0.0, min(top2, bottom2) - max(top1, bottom1))
    x_gap = max(0.0, min(left2, right2) - max(left1, right1))
    if x_gap > page_width * 0.04:
        return False
    return y_gap <= page_height * 0.12


def _dedupe_regions(regions: list[Region]) -> list[Region]:
    if not regions:
        return []
    unique: list[Region] = []
    for region in regions:
        if not _has_matching_region(unique, region):
            unique.append(region)
    return unique


def _visual_summary_from_regions(
    regions: list[Region],
    fallback_groups: list[Any] | dict[str, Any] | None = None,
) -> str | None:
    summaries: list[str] = []
    for region in regions:
        if region.visual_summary:
            summaries.append(str(region.visual_summary).strip())

    if isinstance(fallback_groups, dict):
        candidate = fallback_groups.get("visual_summary")
        if isinstance(candidate, str) and candidate.strip():
            summaries.append(candidate.strip())

    if isinstance(fallback_groups, list):
        for item in fallback_groups:
            if not isinstance(item, dict):
                continue
            value = item.get("visual_summary")
            if isinstance(value, str) and value.strip():
                summaries.append(value.strip())

    summaries = [item for item in summaries if item]
    return summaries[0] if summaries else None


def _normalize_answer_suggestion(value: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "answer": None,
        "confidence": None,
        "reasoning": None,
        "answer_unknown_reason": None,
    }
    if not isinstance(value, dict):
        return result

    answer = str(value.get("answer") or "").strip().upper()
    if answer in {"A", "B", "C", "D"}:
        result["answer"] = answer
    result["confidence"] = _safe_float(value.get("confidence"))
    if isinstance(value.get("reasoning"), str) and value.get("reasoning").strip():
        result["reasoning"] = _strip_placeholder_text(str(value.get("reasoning")).strip())
    if value.get("answer_unknown_reason"):
        result["answer_unknown_reason"] = str(value.get("answer_unknown_reason"))
    return result


def _normalize_analysis_suggestion(value: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "text": None,
        "confidence": None,
        "analysis_unknown_reason": None,
    }
    if not isinstance(value, dict):
        return result
    if isinstance(value.get("text"), str) and value.get("text").strip():
        result["text"] = _strip_placeholder_text(str(value.get("text")).strip())
    result["confidence"] = _safe_float(value.get("confidence"))
    if value.get("analysis_unknown_reason"):
        result["analysis_unknown_reason"] = str(value.get("analysis_unknown_reason"))
    return result


def _empty_semantic_bucket(index: int) -> dict[str, Any]:
    del index
    return {
        "content": "",
        "question_type": "single",
        "pages": [],
        "question_pages": [],
        "options": {},
        "material_temp_ids": [],
        "question_regions": [],
        "visual_groups": [],
        "parse_warnings": [],
        "raw_entries": [],
        "material_text": None,
        "is_cross_page": False,
        "content_quality": {
            "question_complete": False,
            "visual_complete": False,
            "stem_complete": False,
            "options_complete": False,
            "title_missing": True,
            "stem_missing": False,
            "options_missing": False,
            "needs_review": True,
            "risk_flags": [],
            "review_reasons": [],
        },
        "question_quality": {
            "stem_complete": False,
            "options_complete": False,
            "visual_context_complete": False,
            "answer_derivable": False,
            "analysis_derivable": False,
            "duplicate_suspected": False,
            "needs_review": True,
            "risk_flags": [],
            "review_reasons": [],
        },
        "capture_plan": {
            "should_recrop": True,
            "crop_targets": [],
            "padding": 24,
            "must_include": ["chart_title", "legend", "axis_labels", "table_header", "notes"],
        },
        "understanding": {
            "question_intent": "",
            "required_visual_evidence": "",
            "can_answer_from_available_context": False,
            "missing_context": [],
        },
        "answer_suggestion": {
            "answer": None,
            "confidence": None,
            "reasoning": None,
            "answer_unknown_reason": None,
        },
        "analysis_suggestion": {
            "text": None,
            "confidence": None,
            "analysis_unknown_reason": None,
        },
        "ai_audit": {
            "status": "warning",
            "verdict": "需复核",
            "summary": "",
            "needs_review": True,
            "risk_flags": [],
            "review_reasons": [],
        },
    }


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _coerce_int_list(value: Any) -> list[int]:
    if isinstance(value, (int, float, str)):
        parsed = _coerce_int(value)
        return [parsed] if parsed is not None else []
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in (_coerce_int(v) for v in value) if item is not None]


def _merge_unique_ints(values: list[int], extra: Any) -> list[int]:
    result = list(values)
    for item in _coerce_int_list(extra):
        if item not in result:
            result.append(item)
    return result


def _coerce_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _coerce_unique(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[Any] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _question_signature(
    question_text: str,
    options: dict[str, str],
    question_type: str,
    source_pages: list[int],
    has_visual_context: bool,
    image_count: int,
) -> str:
    normalized_text = str(question_text or "").strip()
    if not normalized_text:
        return ""
    normalized_options = [str(options.get(label) or "").strip() for label in ("A", "B", "C", "D")]
    signature_payload = {
        "type": str(question_type or "").strip().lower(),
        "text": normalized_text.replace(" ", ""),
        "options": normalized_options,
        "pages": source_pages,
        "has_visual_context": bool(has_visual_context),
        "image_count": int(image_count),
    }
    return json.dumps(signature_payload, ensure_ascii=False, sort_keys=True)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): val for key, val in value.items()}
    return {}


def _merge_dict(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base or {})
    for key, value in (overrides or {}).items():
        if value is None:
            continue
        merged[key] = value
    return merged


def _strip_placeholder_text(text: str) -> str:
    result = str(text or "")
    result = re.sub(r"\[visual parse unavailable\]", "", result, flags=re.IGNORECASE)
    result = re.sub(r"visual parse unavailable", "", result, flags=re.IGNORECASE)
    result = re.sub(r"page\s*\d+\s*visual parse", "", result, flags=re.IGNORECASE)
    result = re.sub(r"unavailable", "", result, flags=re.IGNORECASE)
    return result.strip()


def _dedupe_images(images: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for image in images:
        ref = str(image.get("ref") or "")
        if ref and ref in seen:
            continue
        if ref:
            seen.add(ref)
        result.append(image)
    return result


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _inject_semantic_debug_payload(
    *,
    debug_dir: str,
    total_pages: int,
    visual_pages: list[dict[str, Any]],
    failed_pages: list[int],
    visual_links: dict[str, Any] | None,
    page_elements_count: int,
    raw_questions_count: int,
    output_questions_count: int,
    materials_count: int,
    failed_page_details: list[dict[str, Any]] | None = None,
) -> None:
    try:
        debug_root = Path(debug_dir) / "debug"
        debug_root.mkdir(parents=True, exist_ok=True)
        visual_links = visual_links or {}
        failed_page_details = failed_page_details or []
        semantic_groups_payload = _build_semantic_debug_groups(visual_links)
        recrop_plan_payload = _build_recrop_debug_plan(semantic_groups_payload)
        page_understanding_payload = visual_links.get("page_understanding", [])
        stage_counts = _build_stage_counts_debug(
            total_pages=total_pages,
            visual_pages=visual_pages,
            failed_pages=failed_pages,
            failed_page_details=failed_page_details,
            page_understanding=page_understanding_payload,
            semantic_groups=semantic_groups_payload,
            recrop_plan=recrop_plan_payload,
            page_elements_count=page_elements_count,
            raw_questions_count=raw_questions_count,
            output_questions_count=output_questions_count,
            materials_count=materials_count,
        )
        first_failed_stage = _first_failed_stage_debug(stage_counts)
        semantic_debug = {
            "task_pages": len(visual_pages),
            "failed_pages": failed_pages,
            "failed_page_details": failed_page_details,
            "semantic_question_count": len(visual_links.get("semantic_question_entries", [])),
            "semantic_question_entries": visual_links.get("semantic_question_entries", []),
            "semantic_recrop_plans": visual_links.get("semantic_recrop_plans", []),
            "visual_merge_candidates": visual_links.get("visual_merge_candidates", []),
            "page_understanding": visual_links.get("page_understanding", []),
            "semantic_pages": visual_links.get("semantic_pages", []),
            "stage_counts": stage_counts,
            "first_failed_stage": first_failed_stage,
        }
        (debug_root / "semantic_debug_payload.json").write_text(
            json.dumps(semantic_debug, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        payload_groups = {
            "page_understanding": page_understanding_payload,
            "semantic_groups": semantic_groups_payload,
            "recrop_plan": recrop_plan_payload,
            "visual_merge_candidates": visual_links.get("visual_merge_candidates", []),
            "stage_counts": stage_counts,
            "first_failed_stage": first_failed_stage,
        }
        for name, payload in payload_groups.items():
            (debug_root / f"{name}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        legacy_alias = {
            "page-understanding.json": payload_groups["page_understanding"],
            "semantic-groups.json": payload_groups["semantic_groups"],
            "recrop-plan.json": payload_groups["recrop_plan"],
            "stage-counts.json": payload_groups["stage_counts"],
            "first-failed-stage.json": payload_groups["first_failed_stage"],
        }
        for alias_name, payload in legacy_alias.items():
            (debug_root / alias_name).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    except Exception:
        return


def _build_stage_counts_debug(
    *,
    total_pages: int,
    visual_pages: list[dict[str, Any]],
    failed_pages: list[int],
    failed_page_details: list[dict[str, Any]] | None,
    page_understanding: list[dict[str, Any]],
    semantic_groups: list[dict[str, Any]],
    recrop_plan: list[dict[str, Any]],
    page_elements_count: int,
    raw_questions_count: int,
    output_questions_count: int,
    materials_count: int,
) -> dict[str, Any]:
    failed_page_details = failed_page_details or []
    detected_question_numbers = [
        number
        for page in page_understanding
        for number in (page.get("detected_question_numbers") or [])
        if number is not None
    ]
    reason_counts: dict[str, int] = {}
    for detail in failed_page_details:
        reason = str(detail.get("failureReason") or detail.get("reason") or "unknown")
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    def _visual_page_reason(page: dict[str, Any]) -> str | None:
        raw = page.get("raw_result") if isinstance(page.get("raw_result"), dict) else {}
        normalized = page.get("normalized_result") if isinstance(page.get("normalized_result"), dict) else {}
        return _classify_vision_failure(normalized or raw, page.get("attempts"), page.get("attempt_errors") or [])

    visual_reasons = [_visual_page_reason(page) for page in visual_pages]
    vision_timeout_count = sum(1 for reason in visual_reasons if reason == "provider_timeout")
    vision_empty_count = sum(1 for reason in visual_reasons if reason == "provider_empty_response")
    schema_invalid_count = sum(1 for reason in visual_reasons if reason == "schema_invalid")
    provider_error_count = sum(1 for reason in visual_reasons if reason in {"provider_error", "visual_model_failed"})
    fallback_attempt_count = sum(1 for page in visual_pages if page.get("fallback_attempted"))
    fallback_success_count = sum(1 for page in visual_pages if page.get("fallback_success"))
    schema_repaired_count = sum(
        1
        for page in visual_pages
        if any(str(err.get("retry_type") or "") == "schema_repair_retry" for err in (page.get("attempt_errors") or []))
        and page.get("request_status") == "ok"
    )
    coarse_count = sum(1 for page in page_understanding if page.get("coarse_fallback") or page.get("fallback_evidence") == "full_page_image")
    success_count = sum(1 for page in visual_pages if page.get("request_status") == "ok")

    failure_reason = None
    if reason_counts:
        failure_reason = max(reason_counts.items(), key=lambda item: item[1])[0]
    elif failed_pages:
        failure_reason = "fallback_failed" if fallback_attempt_count else "provider_error"
    elif detected_question_numbers and not semantic_groups:
        failure_reason = "semantic_grouping_failed"
    elif semantic_groups and output_questions_count == 0:
        failure_reason = "candidate_synthesis_failed"
    elif page_understanding and not detected_question_numbers and coarse_count:
        failure_reason = "coarse_only_no_synthesizable_question"
    elif page_understanding and not detected_question_numbers:
        failure_reason = "page_understanding_failed"

    recommended_fix = _vision_failure_recommended_fix(failure_reason)
    return {
        "pages_count": total_pages,
        "visual_pages_count": len(visual_pages),
        "failed_pages_count": len(failed_pages),
        "failed_pages": failed_pages,
        "failed_page_details": failed_page_details,
        "page_understanding_count": len(page_understanding),
        "page_understanding_detected_question_numbers_count": len(detected_question_numbers),
        "semantic_groups_count": len(semantic_groups),
        "recrop_plan_count": len(recrop_plan),
        "page_elements_count": page_elements_count,
        "raw_questions_count": raw_questions_count,
        "output_questions_count": output_questions_count,
        "materials_count": materials_count,
        "visionCallCount": sum(int(page.get("attempts") or 1) for page in visual_pages),
        "visionSuccessCount": success_count,
        "visionTimeoutCount": vision_timeout_count,
        "visionProviderErrorCount": provider_error_count,
        "visionEmptyResponseCount": vision_empty_count,
        "schemaInvalidCount": schema_invalid_count,
        "schemaRepairedCount": schema_repaired_count,
        "fallbackAttemptCount": fallback_attempt_count,
        "fallbackSuccessCount": fallback_success_count,
        "coarsePageUnderstandingCount": coarse_count,
        "failureReason": failure_reason,
        "recommendedFix": recommended_fix,
        "visionFailureReasonCounts": reason_counts,
    }


def _first_failed_stage_debug(stage_counts: dict[str, Any]) -> dict[str, Any]:
    total_pages = int(stage_counts.get("pages_count") or 0)
    visual_pages_count = int(stage_counts.get("visual_pages_count") or 0)
    failed_pages_count = int(stage_counts.get("failed_pages_count") or 0)
    detected_count = int(stage_counts.get("page_understanding_detected_question_numbers_count") or 0)
    semantic_groups_count = int(stage_counts.get("semantic_groups_count") or 0)
    output_questions_count = int(stage_counts.get("output_questions_count") or 0)
    failure_reason = stage_counts.get("failureReason")

    if visual_pages_count == 0 or (total_pages > 0 and failed_pages_count >= total_pages):
        stage = failure_reason or "provider_error"
        reason = "visual_pages missing or every page is listed in failed_pages"
    elif detected_count == 0:
        stage = failure_reason or "page_understanding_failed"
        reason = "page_understanding exists but detected_question_numbers is empty on all pages"
    elif semantic_groups_count == 0:
        stage = failure_reason or "semantic_grouping_failed"
        reason = "page_understanding detected question numbers but semantic_groups is empty"
    elif output_questions_count == 0:
        stage = failure_reason or "candidate_synthesis_failed"
        reason = "semantic_groups is non-empty but output_questions is empty"
    else:
        stage = None
        reason = "no parser-stage failure detected before backend final preview"
    return {
        "firstFailedStage": stage,
        "reason": reason,
        "failureReason": failure_reason,
        "recommendedFix": stage_counts.get("recommendedFix"),
        "stage_counts": stage_counts,
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
    failed_page_details: list[dict[str, Any]] = []
    page_indexes = _visual_page_indexes(total_pages, debug_dir, retry_failed_pages_only)
    cache_dir = Path(debug_dir) / "debug" / "visual_page_cache"
    vision_ai_dir = Path(debug_dir) / "debug" / "vision_ai_inputs"
    cache_dir.mkdir(parents=True, exist_ok=True)
    vision_ai_dir.mkdir(parents=True, exist_ok=True)
    common_prompt_path = vision_ai_dir / "page_parse_prompt.txt"
    if not common_prompt_path.exists():
        common_prompt_path.write_text(PAGE_PARSE_PROMPT, encoding="utf-8")
    visual_links: dict[str, Any] = {
        "materials": {},
        "questions": {},
        "question_material_ids": {},
        "material_texts": {},
        "question_positions": {},
        "material_positions": {},
        "visual_positions": [],
        "material_groups": {},
        "question_material_group_ids": {},
        "question_link_warnings": {},
        "warnings": [],
        "semantic_question_entries": [],
        "semantic_pages": [],
        "semantic_recrop_plans": [],
        "visual_merge_candidates": [],
        "vision_ai_calls": [],
        "page_understanding": [],
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
        visual_timeout = _visual_page_timeout_seconds()
        page_num = page_index + 1
        page_image_path = vision_ai_dir / f"page_{page_num}.png"
        page_prompt_path = common_prompt_path
        try:
            page_image_data = base64.b64decode(page_b64)
            page_image_path.write_bytes(page_image_data)
        except Exception:
            page_image_data = b""
        visual_result, attempt_errors, attempts = _parse_page_visual_with_retry(
            page_b64,
            timeout_seconds=visual_timeout,
        )
        initial_page_image_path = page_image_path
        initial_prompt_path = page_prompt_path
        fallback_attempted = False
        fallback_success = False
        fallback_image_path: Path | None = None
        fallback_prompt_path: Path | None = None
        fallback_attempt_errors: list[dict[str, Any]] = []
        fallback_attempt_count = 0
        if _visual_result_failed(visual_result) and (
            visual_result.get("error") or visual_result.get("schema_validation")
        ):
            compact_size = 1000
            if compact_size < VISUAL_PAGE_MAX_SIDE:
                try:
                    compact_b64 = _get_page_screenshot(
                        extractor,
                        page_index,
                        dpi=max(70, VISUAL_PAGE_DPI - 30),
                        max_side=compact_size,
                    )
                    compact_prompt_path = vision_ai_dir / f"page_{page_num}_compact_prompt.txt"
                except Exception:
                    compact_b64 = ""
                    compact_prompt_path = None
                if compact_b64 and compact_prompt_path:
                    fallback_attempted = True
                    fallback_prompt_path = compact_prompt_path
                    try:
                        compact_image_data = base64.b64decode(compact_b64)
                        compact_image_path = vision_ai_dir / f"page_{page_num}_compact.png"
                        compact_image_path.write_bytes(compact_image_data)
                    except Exception:
                        compact_image_path = None
                    fallback_image_path = compact_image_path
                    fallback_result, fallback_errors, fallback_attempts = _parse_page_visual_with_retry(
                        compact_b64,
                        timeout_seconds=max(20.0, min(visual_timeout, 60.0)),
                    )
                    fallback_attempt_errors = fallback_errors
                    fallback_attempt_count = fallback_attempts
                    attempts += fallback_attempts
                    attempt_errors.extend(fallback_errors)
                    if not _visual_result_failed(fallback_result):
                        fallback_success = True
                        visual_result = fallback_result
                        if compact_image_path is not None:
                            page_image_path = compact_image_path
                        page_prompt_path = compact_prompt_path

        if not page_prompt_path.exists():
            page_prompt_path.write_text(PAGE_PARSE_PROMPT, encoding="utf-8")
        if fallback_success and fallback_prompt_path and not fallback_prompt_path.exists():
            fallback_prompt_path.write_text(PAGE_PARSE_PROMPT, encoding="utf-8")
        visual_result["vision_call_result"] = _vision_call_result_payload(
            result=visual_result,
            attempts=attempts,
            attempt_errors=attempt_errors,
            fallback_attempted=fallback_attempted,
            fallback_success=fallback_success,
        )
        visual_result.setdefault("vision_retry_plan", {})
        visual_result["vision_retry_plan"].setdefault(
            "reduced_image_retry",
            "success" if fallback_success else ("failed" if fallback_attempted else "not_attempted"),
        )
        visual_result["vision_retry_plan"].setdefault("simplified_prompt_retry", "skipped")
        visual_result["vision_retry_plan"].setdefault(
            "simplified_prompt_retry_reason",
            "prompt_builder_not_yet_parameterized",
        )
        request_payload = {
            "page": page_num,
            "provider": visual_result.get("_vision_provider") or "qwen_vl",
            "model": visual_result.get("_vision_model") or os.getenv("AI_VISUAL_MODEL") or "qwen-vl-max",
            "timeout_seconds": visual_timeout,
            "page_image_path": str(page_image_path),
            "prompt_path": str(page_prompt_path),
            "used_image_path": str(page_image_path),
            "used_prompt_path": str(page_prompt_path),
            "initial_page_image_path": str(initial_page_image_path),
            "initial_prompt_path": str(initial_prompt_path),
            "fallback_attempted": fallback_attempted,
            "fallback_success": fallback_success,
            "fallback_image_path": str(fallback_image_path) if fallback_image_path else None,
            "fallback_prompt_path": str(fallback_prompt_path) if fallback_prompt_path else None,
            "fallback_attempts": fallback_attempt_count,
            "fallback_attempt_errors": fallback_attempt_errors,
            "prompt_length": len(PAGE_PARSE_PROMPT),
            "ocr_text_length": 0,
        }
        vision_call_record = {
            "page": page_num,
            "provider": visual_result.get("_vision_provider") or "qwen_vl",
            "model": visual_result.get("_vision_model") or os.getenv("AI_VISUAL_MODEL") or "qwen-vl-max",
            "timeout_seconds": visual_result.get("_vision_timeout_seconds") or visual_timeout,
            "elapsed_ms": visual_result.get("_vision_elapsed_ms"),
            "fallback_from": visual_result.get("_vision_fallback_from"),
            "prompt_path": str(page_prompt_path),
            "page_image_path": str(page_image_path),
            "used_prompt_path": str(page_prompt_path),
            "used_image_path": str(page_image_path),
            "attempts": attempts,
            "attempt_errors": attempt_errors,
            "request_payload": request_payload,
            "request_payload_redacted": dict(request_payload),
            "raw_output": visual_result,
            "parsed_json": {key: value for key, value in visual_result.items() if not key.startswith("_")},
            "error_type": "visual_model_failed" if _visual_result_failed(visual_result) else None,
            "error_message": visual_result.get("error"),
        }
        visual_links["vision_ai_calls"].append(vision_call_record)
        visual_result["vision_ai"] = {
            "page": page_num,
            "provider": visual_result.get("_vision_provider") or "qwen_vl",
            "model": visual_result.get("_vision_model") or os.getenv("AI_VISUAL_MODEL") or "qwen-vl-max",
            "timeout_seconds": visual_result.get("_vision_timeout_seconds") or visual_timeout,
            "elapsed_ms": visual_result.get("_vision_elapsed_ms"),
            "fallback_from": visual_result.get("_vision_fallback_from"),
            "prompt_path": str(page_prompt_path),
            "page_image_path": str(page_image_path),
            "used_prompt_path": str(page_prompt_path),
            "used_image_path": str(page_image_path),
            "attempts": attempts,
            "attempt_errors": attempt_errors,
            "request_payload": request_payload,
            "request_payload_redacted": dict(request_payload),
            "fallback_attempted": fallback_attempted,
            "fallback_success": fallback_success,
            "fallback_image_path": str(fallback_image_path) if fallback_image_path else None,
            "fallback_prompt_path": str(fallback_prompt_path) if fallback_prompt_path else None,
        }
        raw_output_path = vision_ai_dir / f"page_{page_num}_raw_output.json"
        try:
            raw_output_path.write_text(
                json.dumps(vision_result_to_debug_payload(visual_result, page_num), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass
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
            "failureReason": visual_result.get("vision_call_result", {}).get("failureReason"),
            "recommendedFix": visual_result.get("vision_call_result", {}).get("recommendedFix"),
            "fallback_attempted": fallback_attempted,
            "fallback_success": fallback_success,
            "fallback_attempts": fallback_attempt_count,
            "attempts": attempts,
            "attempt_errors": attempt_errors,
            "image_size": image_size,
            "base64_size": len(page_b64),
        }
        page_analysis = visual_result.get("page_analysis") or {}
        visual_links["page_understanding"].append(
            _build_page_understanding_record(
                page_num=page_num,
                visual_result=visual_result,
                source_image_path=str(page_image_path),
                prompt_path=str(page_prompt_path),
                raw_output_ref=str(raw_output_path),
                image_size=image_size,
            )
        )
        semantic_questions = visual_result.get("semantic_questions") or []
        for semantic_entry in semantic_questions:
            if not isinstance(semantic_entry, dict):
                continue
            semantic_entry = dict(semantic_entry)
            semantic_entry.setdefault("pages", [])
            if not semantic_entry["pages"]:
                semantic_entry["pages"] = [page_index + 1]
            visual_links["semantic_question_entries"].append(semantic_entry)
            capture_plan = semantic_entry.get("capture_plan")
            if isinstance(capture_plan, dict):
                visual_links["semantic_recrop_plans"].append(
                    {
                        "page_num": page_index + 1,
                        "question_no": semantic_entry.get("question_no") or semantic_entry.get("index"),
                        "capture_plan": capture_plan,
                        "crop_targets": capture_plan.get("crop_targets") or [],
                    }
                )
        semantic_merge_candidates = visual_result.get("visual_merge_candidates") or []
        for merge_candidate in semantic_merge_candidates:
            if isinstance(merge_candidate, dict):
                visual_links["visual_merge_candidates"].append(merge_candidate)

        semantic_question_pages = visual_links.setdefault("semantic_question_pages", {})
        for semantic_question_no in [
            semantic_entry.get("index") for semantic_entry in semantic_questions if isinstance(semantic_entry, dict)
        ]:
            if semantic_question_no is None:
                continue
            pages_for_question = semantic_question_pages.setdefault(semantic_question_no, [])
            if (page_index + 1) not in pages_for_question:
                pages_for_question.append(page_index + 1)
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
                        "material_key": material_key,
                        "kind": "material",
                        "bbox": _coerce_visual_bbox(bbox),
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
            stem_bbox = question.get("stem_bbox") or question.get("bbox")
            option_bboxes = {item.get("label"): item.get("bbox") for item in question.get("options", []) or []}
            source_bboxes = [
                bbox
                for bbox in [stem_bbox, *[option_bboxes.get(label) for label in ["A", "B", "C", "D"]]]
                if _valid_source_visual_bbox(extractor, page_index, bbox)
            ]
            source_bbox = _union_visual_bboxes([_coerce_visual_bbox(bbox) for bbox in source_bboxes])
            text_block_bbox = source_bbox or [0.0, y, 1000.0, y + 10.0]
            blocks.append({"bbox": text_block_bbox, "text": anchor_line})
            visual_links["question_positions"][index] = {
                "page_num": page_index + 1,
                "bbox": source_bbox,
                "question_bbox": question_bbox,
                "source_bboxes": source_bboxes,
                "y0": float(text_block_bbox[1]),
                "y1": float(text_block_bbox[3]),
            }
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
            for label in ["A", "B", "C", "D"]:
                option_value = question.get(f"option_{label.lower()}")
                if not option_value:
                    continue
                option_line = f"{label}. {str(option_value).strip()}"
                lines.append(option_line)
                option_bbox = option_bboxes.get(label) or [0.0, y, 1000.0, y + 10.0]
                blocks.append(
                    {
                        "bbox": option_bbox
                        if _valid_source_visual_bbox(extractor, page_index, option_bbox)
                        else [0.0, y, 1000.0, y + 10.0],
                        "text": option_line,
                    }
                )
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
                y += 12.0

        question_bboxes = [
            question.get("bbox")
            for question in visual_result.get("questions", []) or []
            if question.get("bbox")
        ]
        visual_items = _merge_adjacent_visuals(
            visual_result.get("visuals", []) or [],
            question_bboxes,
            page_height=_visual_page_height(extractor, page_index),
            page_num=page_index + 1,
        )
        for visual in visual_items:
            bbox = visual.get("bbox")
            if not bbox:
                continue
            visual_region = _region_from_bbox(
                extractor,
                page_index,
                bbox,
                visual.get("kind") or "image",
                warnings=page_warnings,
                caption=visual.get("caption"),
                same_visual_group_id=visual.get("same_visual_group_id"),
            )
            if visual_region:
                regions.append(visual_region)
                visual_links.setdefault("visual_positions", []).append(
                    {
                        "page_num": page_index + 1,
                        "kind": visual.get("kind") or "visual",
                        "bbox": _coerce_visual_bbox(bbox),
                        "y0": float(bbox[1]),
                        "y1": float(bbox[3]),
                        "explicit_question_link": isinstance(visual.get("question_index"), int),
                        "region": visual_region,
                        "caption": visual.get("caption"),
                        "same_visual_group_id": visual.get("same_visual_group_id"),
                    }
                )
                material_temp_id = str(visual.get("material_temp_id") or "")
                question_index = visual.get("question_index")
                if material_temp_id:
                    material_key = page_material_keys.get(material_temp_id)
                    if material_key:
                        visual_links["materials"].setdefault(material_key, []).append(visual_region)
                elif isinstance(question_index, int):
                    visual_links["questions"].setdefault(question_index, []).append(visual_region)

        _apply_backward_material_links(visual_links, page_num=page_index + 1)
        page_material_groups = _build_shared_material_groups(extractor, visual_links, page_index=page_index)

        if not blocks:
            text = extractor.get_page_text(page_index)
            fallback_lines = [line.strip() for line in text.splitlines() if line.strip()]
            for line in fallback_lines:
                lines.append(line)
                blocks.append({"bbox": [0.0, y, 1000.0, y + 10.0], "text": line})
                y += 12.0
            if not fallback_lines:
                regions.append(_full_page_region(extractor, page_index))
                page_warnings.append("visual_page_fallback_used")
                page_warnings.append("visual_parse_failed")
        if _needs_page_fallback_region(page_warnings, visual_result):
            if not any(region.type == "page_fallback" for region in regions):
                regions.append(_full_page_region(extractor, page_index))

        visual_debug["normalized_blocks"] = blocks
        visual_debug["regions"] = [{"type": region.type, "bbox": region.bbox} for region in regions]
        visual_debug["material_groups"] = page_material_groups
        visual_debug["page_warnings"] = sorted(set((visual_result.get("warnings") or []) + page_warnings))
        visual_debug["schema_validation"] = visual_result.get("schema_validation") or {}
        visual_pages.append(visual_debug)
        if _visual_result_failed(visual_result):
            failed_pages.append(page_index + 1)
            failed_page_details.append(
                {
                    "page": page_index + 1,
                    "reason": visual_result.get("error") or visual_debug.get("failureReason") or "vision_call_failed",
                    "failureReason": visual_debug.get("failureReason") or _classify_vision_failure(visual_result),
                    "recommendedFix": visual_debug.get("recommendedFix"),
                    "attempts": attempts,
                    "attemptErrors": attempt_errors,
                    "fallbackAttempted": fallback_attempted,
                    "fallbackSuccess": fallback_success,
                    "providerAttempts": visual_result.get("_vision_provider_attempts") or [],
                    "visionCallResult": visual_result.get("vision_call_result") or {},
                }
            )
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
    setattr(extractor, "_parser_kernel_failed_page_details", failed_page_details)
    setattr(extractor, "_parser_kernel_vision_ai_calls", visual_links.get("vision_ai_calls", []))
    return pages


def vision_result_to_debug_payload(result: dict[str, Any], page: int) -> dict[str, Any]:
    vision_ai = result.get("vision_ai") if isinstance(result.get("vision_ai"), dict) else {}
    request_payload = vision_ai.get("request_payload") if isinstance(vision_ai.get("request_payload"), dict) else {}
    request_payload_redacted = (
        vision_ai.get("request_payload_redacted")
        if isinstance(vision_ai.get("request_payload_redacted"), dict)
        else dict(request_payload)
    )
    raw_output = result.get("raw_model_result") or result
    used_image_path = (
        vision_ai.get("used_image_path")
        or vision_ai.get("page_image_path")
        or request_payload.get("used_image_path")
        or request_payload.get("page_image_path")
    )
    used_prompt_path = (
        vision_ai.get("used_prompt_path")
        or vision_ai.get("prompt_path")
        or request_payload.get("used_prompt_path")
        or request_payload.get("prompt_path")
    )
    return {
        "page": page,
        "provider": vision_ai.get("provider") or result.get("_vision_provider"),
        "model": vision_ai.get("model") or result.get("_vision_model"),
        "timeout_seconds": vision_ai.get("timeout_seconds") or result.get("_vision_timeout_seconds"),
        "elapsed_ms": vision_ai.get("elapsed_ms") or result.get("_vision_elapsed_ms"),
        "fallback_from": vision_ai.get("fallback_from") or result.get("_vision_fallback_from"),
        "status": "failed" if _visual_result_failed(result) else "ok",
        "attempts": vision_ai.get("attempts") if vision_ai.get("attempts") is not None else result.get("attempts"),
        "attempt_errors": vision_ai.get("attempt_errors") or result.get("attempt_errors") or [],
        "request_payload": request_payload,
        "request_payload_redacted": request_payload_redacted,
        "raw_output": raw_output,
        "parsed_json": {key: value for key, value in result.items() if not key.startswith("_") and key != "raw_model_result"},
        "used_image_path": used_image_path,
        "used_prompt_path": used_prompt_path,
        "warnings": result.get("warnings") or [],
        "schema_validation": result.get("schema_validation") or {},
        "error_type": "visual_model_failed" if _visual_result_failed(result) else None,
        "error_message": result.get("error"),
        "error": result.get("error"),
        "raw_model_result": raw_output,
        "page_analysis": result.get("page_analysis") or {},
        "semantic_questions": result.get("semantic_questions") or [],
        "visual_merge_candidates": result.get("visual_merge_candidates") or [],
        "provider_attempts": result.get("_vision_provider_attempts") or [],
        "vision_ai": vision_ai,
    }


def _attach_regions(question: QuestionGroup, pages: list[PageContent]) -> list[Region]:
    regions: list[Region] = []
    visual_region_types = {"chart", "table", "image", "visual"}
    for page in pages:
        if page.page_num != question.page_num:
            continue
        for region in page.regions:
            if region.type not in visual_region_types:
                continue
            y0 = region.bbox[1]
            if question.y0 <= y0 <= question.y1:
                regions.append(region)
    return regions


def _source_bbox_for_question(extractor: Any, raw: RawQuestion, visual_links: dict[str, Any]) -> list[float] | None:
    position = (visual_links.get("question_positions") or {}).get(raw.index) or {}
    source_bboxes = position.get("source_bboxes") or []
    normalized_bboxes: list[list[float]] = []
    for bbox in source_bboxes:
        normalized = _normalized_source_bbox(extractor, raw.page_num - 1, bbox)
        if normalized:
            normalized_bboxes.append(normalized)
    if normalized_bboxes:
        return _union_visual_bboxes(normalized_bboxes)

    bbox = position.get("bbox")
    if bbox:
        return _normalized_source_bbox(extractor, raw.page_num - 1, bbox)
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
    caption: str | None = None,
    same_visual_group_id: str | None = None,
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
        caption=caption,
        page=page_index + 1,
        same_visual_group_id=same_visual_group_id,
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
        "ref": _region_ref(region),
        "role": region.type,
        "image_role": _image_role_for_region(region.type),
        "caption": region.caption,
        "page": region.page,
        "bbox": region.bbox,
        "raw_bbox": region.bbox,
        "expanded_bbox": region.bbox,
        "absorbed_texts": [],
        "child_visual_ids": [],
        "same_visual_group_id": region.same_visual_group_id,
        "assignment_confidence": region.assignment_confidence or assignment_confidence,
    }


def _region_to_visual_ref(region: Region) -> dict[str, Any]:
    return {
        "id": _region_ref(region),
        "ref": _region_ref(region),
        "page": region.page,
        "bbox": region.bbox,
        "raw_bbox": region.bbox,
        "expanded_bbox": region.bbox,
        "absorbed_texts": [],
        "child_visual_ids": [],
        "role": region.type,
        "kind": region.type,
        "caption": region.caption,
        "same_visual_group_id": region.same_visual_group_id,
        "assignment_confidence": region.assignment_confidence,
    }


def _region_ref(region: Region) -> str:
    page = region.page or 0
    bbox_key = "-".join(str(int(round(value))) for value in region.bbox[:4])
    return f"{region.type}-p{page}-{bbox_key}"


def _has_matching_region(regions: list[Region], region: Region) -> bool:
    for existing in regions:
        if existing.type == region.type and existing.bbox == region.bbox and existing.page == region.page:
            return True
    return False


def _image_role_for_region(region_type: str) -> str:
    if region_type in {"chart", "table", "image", "visual", "material"}:
        return "material" if region_type == "material" else "question_visual"
    if region_type.startswith("option_"):
        return "option_image"
    return "unknown"


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


def _classify_vision_failure(
    result: dict[str, Any],
    attempts: Any = None,
    attempt_errors: list[dict[str, Any]] | None = None,
) -> str | None:
    warnings = {str(item) for item in (result.get("warnings") or [])}
    schema_validation = result.get("schema_validation") if isinstance(result.get("schema_validation"), dict) else {}
    provider_attempts = result.get("_vision_provider_attempts") or []
    attempt_errors = attempt_errors or []
    error = str(result.get("error") or "")
    error_lc = error.lower()
    all_attempts = []
    if isinstance(provider_attempts, list):
        all_attempts.extend(item for item in provider_attempts if isinstance(item, dict))
    all_attempts.extend(item for item in attempt_errors if isinstance(item, dict))
    attempt_error_types = {str(item.get("error_type") or "").lower() for item in all_attempts}
    attempt_messages = " ".join(str(item.get("error_message") or item.get("error") or "") for item in all_attempts).lower()

    if "vision_page_timeout" in warnings or "timeout" in attempt_error_types or "timeout" in error_lc:
        return "provider_timeout"
    if "visual_schema_invalid" in warnings or schema_validation.get("valid") is False:
        return "schema_invalid"
    if "empty" in error_lc or "empty" in attempt_messages or error_lc == "visual_page_empty_result":
        return "provider_empty_response"
    if "visual_model_failed" in warnings or error or any(item.get("status") == "failed" for item in all_attempts):
        return "provider_error"
    return None


def _vision_failure_recommended_fix(reason: Any) -> str | None:
    reason = str(reason or "")
    mapping = {
        "provider_timeout": "increase visual provider timeout, inspect provider latency, retry the failed chunk with reduced_image_retry",
        "provider_empty_response": "inspect raw provider response and retry with reduced image or simplified prompt",
        "schema_invalid": "inspect raw output and run schema_repair_retry; update prompt/schema if repeated",
        "schema_repair_failed": "capture raw output, add parser repair tests, and update schema normalization",
        "provider_error": "inspect provider error details and environment/provider configuration",
        "fallback_failed": "inspect reduced_image_retry artifacts and provider diagnostics",
        "coarse_only_no_synthesizable_question": "coarse page evidence exists but no structured question; improve whole-page understanding prompt/parser",
        "page_understanding_failed": "inspect page-understanding.json and raw visual output; improve page understanding extraction",
        "semantic_grouping_failed": "inspect semantic-groups.json; improve semantic grouping from page understanding",
        "candidate_synthesis_failed": "inspect recrop-plan and raw question synthesis; improve candidate construction",
        "source_evidence_missing": "rerun with full PDF/source locator and block auto/manual publish until evidence is complete",
    }
    return mapping.get(reason)


def _vision_call_result_payload(
    *,
    result: dict[str, Any],
    attempts: int,
    attempt_errors: list[dict[str, Any]],
    fallback_attempted: bool = False,
    fallback_success: bool = False,
) -> dict[str, Any]:
    failure_reason = _classify_vision_failure(result, attempts, attempt_errors)
    if fallback_attempted and failure_reason and not fallback_success:
        failure_reason = "fallback_failed"
    status = "success" if not failure_reason else "failed"
    return {
        "status": status,
        "failureReason": failure_reason,
        "recommendedFix": _vision_failure_recommended_fix(failure_reason),
        "attempts": attempts,
        "providerAttempts": result.get("_vision_provider_attempts") or [],
        "attemptErrors": attempt_errors,
        "fallbackAttempted": fallback_attempted,
        "fallbackSuccess": fallback_success,
        "schemaValidation": result.get("schema_validation") or {},
    }


def _parse_page_visual_with_retry(
    page_b64: str,
    timeout_seconds: float | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    attempt_errors: list[dict[str, Any]] = []
    timeout = timeout_seconds or _visual_page_timeout_seconds()
    first_result = _parse_page_visual_with_timeout(page_b64, timeout_seconds=timeout)
    first_reason = _classify_vision_failure(first_result, 1, attempt_errors)
    if not _visual_result_retryable(first_result):
        first_result["vision_call_result"] = _vision_call_result_payload(
            result=first_result,
            attempts=1,
            attempt_errors=attempt_errors,
        )
        first_result["vision_retry_plan"] = {
            "reduced_image_retry": "handled_by_page_fallback" if first_reason else "not_needed",
            "schema_repair_retry": "not_applicable",
            "simplified_prompt_retry": "skipped",
            "simplified_prompt_retry_reason": "prompt_builder_not_yet_parameterized",
        }
        return first_result, attempt_errors, 1
    first_warnings = set(str(item) for item in first_result.get("warnings") or [])
    if "visual_schema_invalid" not in first_warnings:
        first_result["vision_call_result"] = _vision_call_result_payload(
            result=first_result,
            attempts=1,
            attempt_errors=attempt_errors,
        )
        first_result["vision_retry_plan"] = {
            "reduced_image_retry": "handled_by_page_fallback" if first_reason else "not_needed",
            "schema_repair_retry": "skipped_non_schema_retryable_result",
            "simplified_prompt_retry": "skipped",
            "simplified_prompt_retry_reason": "prompt_builder_not_yet_parameterized",
        }
        return first_result, attempt_errors, 1
    attempt_errors.append(
        {
            "retry_type": "schema_repair_retry",
            "warnings": list(first_result.get("warnings") or []),
            "schema_validation": first_result.get("schema_validation") or {},
            "error": first_result.get("error"),
        }
    )
    second_result = _parse_page_visual_with_timeout(page_b64, timeout_seconds=timeout)
    second_reason = _classify_vision_failure(second_result, 2, attempt_errors)
    second_result["vision_call_result"] = _vision_call_result_payload(
        result=second_result,
        attempts=2,
        attempt_errors=attempt_errors,
    )
    second_result["vision_retry_plan"] = {
        "reduced_image_retry": "handled_by_page_fallback" if second_reason else "not_needed",
        "schema_repair_retry": "success" if not second_reason else "failed",
        "simplified_prompt_retry": "skipped",
        "simplified_prompt_retry_reason": "prompt_builder_not_yet_parameterized",
    }
    return second_result, attempt_errors, 2


def _parse_page_visual_with_timeout(
    page_b64: str,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    timeout = timeout_seconds or _visual_page_timeout_seconds()
    chain_timeout = _visual_chain_timeout_seconds(timeout)
    result_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
    error_queue: queue.Queue[Exception] = queue.Queue(maxsize=1)

    def _runner() -> None:
        try:
            result_queue.put(ai_client.parse_page_visual(page_b64))
        except Exception as exc:  # pragma: no cover - exercised via caller behavior
            error_queue.put(exc)

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join(chain_timeout)

    if thread.is_alive():
        return _visual_timeout_result(chain_timeout)

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
    return _classify_vision_failure(result) is not None


def _visual_page_timeout_seconds() -> float:
    raw = (
        os.getenv("VISION_AI_TIMEOUT_SECONDS")
        or os.getenv("PDF_VISUAL_PAGE_TIMEOUT_SECONDS")
        or os.getenv("PDF_VISUAL_OPENAI_TIMEOUT_SECONDS")
    )
    if not raw:
        return DEFAULT_VISUAL_PAGE_TIMEOUT_SECONDS
    try:
        timeout = float(raw)
    except ValueError:
        return DEFAULT_VISUAL_PAGE_TIMEOUT_SECONDS
    return timeout if timeout > 0 else DEFAULT_VISUAL_PAGE_TIMEOUT_SECONDS


def _visual_chain_timeout_seconds(provider_timeout_seconds: float) -> float:
    fallback_enabled = bool(os.getenv("MIMO_API_KEY")) or bool(os.getenv("PDF_VISUAL_PROVIDER_TIMEOUT_SECONDS")) or bool(
        os.getenv("VISION_AI_PROVIDER_TIMEOUT_SECONDS")
    )
    provider_slots = 2 if fallback_enabled else 1
    if os.getenv("VISION_AI_ENABLE_DASHSCOPE_SDK_FALLBACK", "").lower() in {"1", "true", "yes"}:
        provider_slots += 1
    return max(provider_timeout_seconds, provider_timeout_seconds * provider_slots + 10.0)


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
        "_vision_provider": "qwen_vl",
        "_vision_model": os.getenv("AI_VISUAL_MODEL") or "qwen-vl-max",
        "_vision_timeout_seconds": timeout_seconds,
        "_vision_elapsed_ms": int(timeout_seconds * 1000),
        "_vision_provider_attempts": [
            {
                "provider": "qwen_vl",
                "model": os.getenv("AI_VISUAL_MODEL") or "qwen-vl-max",
                "timeout_seconds": timeout_seconds,
                "elapsed_ms": int(timeout_seconds * 1000),
                "status": "failed",
                "error_type": "timeout",
                "error_message": f"page_visual_timeout_after_{timeout_seconds:.1f}s",
                "fallback_from": None,
            }
        ],
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
        "_vision_provider": "qwen_vl",
        "_vision_model": os.getenv("AI_VISUAL_MODEL") or "qwen-vl-max",
        "_vision_timeout_seconds": _visual_page_timeout_seconds(),
        "_vision_elapsed_ms": 0,
        "_vision_provider_attempts": [
            {
                "provider": "qwen_vl",
                "model": os.getenv("AI_VISUAL_MODEL") or "qwen-vl-max",
                "timeout_seconds": _visual_page_timeout_seconds(),
                "elapsed_ms": 0,
                "status": "failed",
                "error_type": "exception",
                "error_message": message,
                "fallback_from": None,
            }
        ],
    }


def _needs_page_fallback_region(page_warnings: list[str], visual_result: dict[str, Any]) -> bool:
    warning_set = set(page_warnings)
    warning_set.update(str(item) for item in visual_result.get("warnings") or [])
    return bool(warning_set & {"vision_page_timeout", "visual_model_failed"})


def _build_shared_material_groups(
    extractor: Any,
    visual_links: dict[str, Any],
    *,
    page_index: int,
) -> list[dict[str, Any]]:
    page_num = page_index + 1
    question_positions = visual_links.get("question_positions", {})
    material_positions = visual_links.get("material_positions", {})
    visual_positions = visual_links.get("visual_positions", [])
    material_groups = visual_links.setdefault("material_groups", {})
    question_group_ids = visual_links.setdefault("question_material_group_ids", {})
    visual_link_warnings = visual_links.setdefault("warnings", [])

    page_questions = [
        {"index": index, **position}
        for index, position in question_positions.items()
        if position.get("page_num") == page_num
    ]
    if not page_questions:
        return []
    page_questions.sort(key=lambda item: (item["y0"], item["index"]))

    seeds: list[dict[str, Any]] = []
    for material_key, position in material_positions.items():
        if position.get("page_num") != page_num:
            continue
        seeds.append({**position, "seed_type": "material", "material_key": material_key})
    for index, position in enumerate(visual_positions, start=1):
        if position.get("page_num") != page_num:
            continue
        if position.get("explicit_question_link"):
            continue
        kind = str(position.get("kind") or "visual").lower()
        if kind not in {"chart", "table", "image", "visual"}:
            continue
        seeds.append({**position, "seed_type": "visual", "visual_index": index})
    seeds = [seed for seed in seeds if _coerce_visual_bbox(seed.get("bbox"))]
    seeds.sort(key=lambda item: (float(item["y0"]), float(item["y1"])))
    if not seeds:
        return []

    max_gap = _material_group_max_gap(extractor, page_index)
    page_groups: list[dict[str, Any]] = []
    grouped_material_keys: set[str] = set()

    for material_key, position in material_positions.items():
        if position.get("page_num") != page_num:
            continue
        seed_bbox = _coerce_visual_bbox(position.get("bbox"))
        if not seed_bbox:
            continue
        candidates = [
            question
            for question in page_questions
            if visual_links.get("question_material_ids", {}).get(question["index"]) == material_key
        ]
        if not candidates:
            continue
        candidates.sort(key=lambda item: (item["y0"], item["index"]))
        question_indexes = [int(question["index"]) for question in candidates]
        group_id = f"mg_p{page_num}_{len(page_groups) + 1}"
        confidence = 0.9 if len(question_indexes) > 1 else 0.72
        warnings = [] if len(question_indexes) > 1 else ["material_group_low_confidence"]
        group = {
            "group_id": group_id,
            "page_num": page_num,
            "bbox": _union_visual_bboxes([seed_bbox] + [_coerce_visual_bbox(q.get("bbox")) for q in candidates]),
            "visual_bbox_list": [],
            "material_bbox_list": [seed_bbox],
            "question_indexes": question_indexes,
            "question_ids": [f"page_{page_num:03d}_q{index:03d}" for index in question_indexes],
            "start_y": min(float(position["y0"]), min(float(question["y0"]) for question in candidates)),
            "end_y": max(float(position["y1"]), max(float(question["y1"]) for question in candidates)),
            "confidence": confidence,
            "link_reason": "explicit_material_group",
            "warnings": warnings,
        }
        material_groups[group_id] = group
        page_groups.append(group)
        grouped_material_keys.add(str(material_key))
        for question_index in question_indexes:
            question_group_ids[question_index] = group_id

    for seed_index, seed in enumerate(seeds):
        material_key = str(seed.get("material_key") or "")
        if material_key and material_key in grouped_material_keys:
            continue
        seed_bbox = _coerce_visual_bbox(seed.get("bbox"))
        if not seed_bbox:
            continue
        next_seed_y = float(seeds[seed_index + 1]["y0"]) if seed_index + 1 < len(seeds) else None
        candidates = [
            question
            for question in page_questions
            if float(question["y0"]) >= float(seed["y1"])
            and (next_seed_y is None or float(question["y0"]) < next_seed_y)
        ]
        if not candidates:
            continue
        first_gap = float(candidates[0]["y0"]) - float(seed["y1"])
        if first_gap > max_gap:
            visual_link_warnings.append(
                {
                    "page_num": page_num,
                    "seed_bbox": seed_bbox,
                    "first_question_index": candidates[0]["index"],
                    "warning": "material_group_range_uncertain",
                }
            )
            continue

        question_indexes = [int(question["index"]) for question in candidates]
        group_id = f"mg_p{page_num}_{len(page_groups) + 1}"
        material_bbox_list = [seed_bbox] if seed.get("seed_type") == "material" else []
        visual_bbox_list = [seed_bbox] if seed.get("seed_type") == "visual" else []
        confidence = 0.86 if len(question_indexes) > 1 else 0.72
        warnings = [] if len(question_indexes) > 1 else ["material_group_low_confidence"]
        group = {
            "group_id": group_id,
            "page_num": page_num,
            "bbox": _union_visual_bboxes([seed_bbox] + [_coerce_visual_bbox(q.get("bbox")) for q in candidates]),
            "visual_bbox_list": visual_bbox_list,
            "material_bbox_list": material_bbox_list,
            "question_indexes": question_indexes,
            "question_ids": [f"page_{page_num:03d}_q{index:03d}" for index in question_indexes],
            "start_y": float(seed["y0"]),
            "end_y": max(float(question["y1"]) for question in candidates),
            "confidence": confidence,
            "link_reason": f"downward_{seed.get('seed_type')}_group",
            "warnings": warnings,
        }
        material_groups[group_id] = group
        page_groups.append(group)
        for question_index in question_indexes:
            question_group_ids.setdefault(question_index, group_id)
            if seed.get("seed_type") == "visual" and seed.get("region") is not None:
                region = seed["region"]
                if hasattr(region, "assignment_confidence"):
                    region.assignment_confidence = confidence
                visual_links.setdefault("questions", {}).setdefault(question_index, []).append(region)

    return page_groups


def _merge_adjacent_visuals(
    visuals: list[dict[str, Any]],
    question_bboxes: list[Any],
    *,
    page_height: float,
    page_num: int,
) -> list[dict[str, Any]]:
    normalized = [dict(visual) for visual in visuals if _coerce_visual_bbox(visual.get("bbox"))]
    normalized.sort(key=lambda item: (_coerce_visual_bbox(item["bbox"])[1], _coerce_visual_bbox(item["bbox"])[0]))
    merged: list[dict[str, Any]] = []
    used: set[int] = set()
    group_index = 1
    for index, visual in enumerate(normalized):
        if index in used:
            continue
        current_group = [visual]
        used.add(index)
        current_bbox = _coerce_visual_bbox(visual.get("bbox"))
        for next_index in range(index + 1, len(normalized)):
            if next_index in used:
                continue
            candidate = normalized[next_index]
            candidate_bbox = _coerce_visual_bbox(candidate.get("bbox"))
            if not current_bbox or not candidate_bbox:
                continue
            if not _can_merge_visuals(current_bbox, candidate_bbox, question_bboxes, page_height):
                continue
            current_group.append(candidate)
            used.add(next_index)
            current_bbox = _union_visual_bboxes([current_bbox, candidate_bbox])
        if len(current_group) == 1:
            merged.append(current_group[0])
            continue
        group_id = f"vg_p{page_num}_{group_index}"
        group_index += 1
        captions = [str(item.get("caption") or "").strip() for item in current_group if str(item.get("caption") or "").strip()]
        merged_visual = {
            **current_group[0],
            "bbox": _union_visual_bboxes([_coerce_visual_bbox(item.get("bbox")) for item in current_group]),
            "caption": captions[0] if captions else current_group[0].get("caption"),
            "same_visual_group_id": group_id,
        }
        merged.append(merged_visual)
    return merged


def _can_merge_visuals(
    first: list[float],
    second: list[float],
    question_bboxes: list[Any],
    page_height: float,
) -> bool:
    if _x_overlap_ratio(first, second) <= 0.6:
        return False
    y_gap = max(0.0, second[1] - first[3])
    if y_gap > page_height * 0.08:
        return False
    return not _has_question_between(first[3], second[1], question_bboxes)


def _x_overlap_ratio(first: list[float], second: list[float]) -> float:
    overlap = max(0.0, min(first[2], second[2]) - max(first[0], second[0]))
    narrower = max(1.0, min(first[2] - first[0], second[2] - second[0]))
    return overlap / narrower


def _has_question_between(top_y: float, bottom_y: float, question_bboxes: list[Any]) -> bool:
    for bbox_value in question_bboxes:
        bbox = _coerce_visual_bbox(bbox_value)
        if not bbox:
            continue
        if top_y <= bbox[1] <= bottom_y:
            return True
    return False


def _visual_page_height(extractor: Any, page_index: int) -> float:
    image_size = _cached_visual_render_size(extractor, page_index)
    try:
        height = float((image_size or {}).get("height") or 0)
    except (TypeError, ValueError, AttributeError):
        height = 0.0
    if height > 0:
        return height
    return float(_page_rect(extractor, page_index).height)


def _visual_page_width(extractor: Any, page_index: int) -> float:
    image_size = _cached_visual_render_size(extractor, page_index)
    try:
        width = float((image_size or {}).get("width") or 0)
    except (TypeError, ValueError, AttributeError):
        width = 0.0
    if width > 0:
        return width
    page_rect = _page_rect(extractor, page_index)
    scale_x, _ = _visual_render_scale(extractor, page_index, page_rect)
    return float(page_rect.width * scale_x)


def _valid_source_visual_bbox(extractor: Any, page_index: int, bbox_value: Any) -> bool:
    bbox = _coerce_visual_bbox(bbox_value)
    if not bbox:
        return False
    page_width = max(_visual_page_width(extractor, page_index), 1.0)
    page_height = max(_visual_page_height(extractor, page_index), 1.0)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    if bbox[0] < -page_width * 0.02 or bbox[1] < -page_height * 0.02:
        return False
    if bbox[2] > page_width * 1.02 or bbox[3] > page_height * 1.02:
        return False
    if width > page_width * 1.05 or height > page_height * 0.45:
        return False
    return (width * height) / (page_width * page_height) <= 0.5


def _normalized_source_bbox(extractor: Any, page_index: int, bbox_value: Any) -> list[float] | None:
    if not _valid_source_visual_bbox(extractor, page_index, bbox_value):
        return None
    warnings: list[str] = []
    _, normalized = _bbox_to_page_rect(extractor, page_index, bbox_value, warnings)
    if normalized is None:
        return None
    page_rect = _page_rect(extractor, page_index)
    if "visual_bbox_clamped" in warnings and _source_bbox_looks_like_page_fallback(normalized, page_rect):
        return None
    return normalized


def _source_bbox_looks_like_page_fallback(bbox: list[float], page_rect: fitz.Rect) -> bool:
    page_width = max(float(page_rect.width), 1.0)
    page_height = max(float(page_rect.height), 1.0)
    width_ratio = (bbox[2] - bbox[0]) / page_width
    height_ratio = (bbox[3] - bbox[1]) / page_height
    area_ratio = width_ratio * height_ratio
    return area_ratio >= 0.65 or (width_ratio >= 0.95 and height_ratio >= 0.45)


def _coerce_visual_bbox(value: Any) -> list[float] | None:
    if not isinstance(value, list | tuple) or len(value) != 4:
        return None
    try:
        bbox = [float(item) for item in value]
    except (TypeError, ValueError):
        return None
    if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        return None
    return bbox


def _material_group_max_gap(extractor: Any, page_index: int) -> float:
    image_size = _cached_visual_render_size(extractor, page_index)
    try:
        height = float((image_size or {}).get("height") or 0)
    except (TypeError, ValueError, AttributeError):
        height = 0.0
    if height <= 0:
        height = float(_page_rect(extractor, page_index).height)
    return min(max(height * 0.35, 120.0), 360.0)


def _union_visual_bboxes(bboxes: list[list[float] | None]) -> list[float] | None:
    valid = [bbox for bbox in bboxes if bbox]
    if not valid:
        return None
    return [
        min(bbox[0] for bbox in valid),
        min(bbox[1] for bbox in valid),
        max(bbox[2] for bbox in valid),
        max(bbox[3] for bbox in valid),
    ]


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
