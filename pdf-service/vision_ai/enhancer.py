from __future__ import annotations

import base64
import os
from copy import deepcopy
from typing import Any

import fitz

from vision_ai.base import VisionAIProvider
from vision_ai.qwen_vl_provider import provider_from_env
from vision_ai.schema import VisionAIEnhancementResult, VisionAIRequest

AUTO_APPLY_THRESHOLD = 0.85
SUGGESTION_THRESHOLD = 0.65


def enhance_questions_with_vision_ai(
    *,
    pdf_path: str,
    output_dir: str,
    questions: list[dict[str, Any]],
    page_elements: list[Any],
    visual_payloads: dict[str, dict[str, Any]],
    provider: VisionAIProvider | None = None,
) -> VisionAIEnhancementResult:
    stats: dict[str, Any] = {
        "enabled": vision_ai_enabled(),
        "provider": _provider_name(provider),
        "called_pages": [],
        "warnings": [],
    }
    enhanced = deepcopy(questions)
    if not stats["enabled"]:
        return VisionAIEnhancementResult(enhanced, stats)

    provider = provider or provider_from_env()
    if not provider:
        stats["warnings"].append("vision_ai_api_key_missing")
        return VisionAIEnhancementResult(enhanced, stats)
    stats["provider"] = _provider_name(provider)

    pages = sorted(_candidate_pages(enhanced, page_elements, visual_payloads))
    page_image_cache: dict[int, str] = {}
    for page in pages:
        page_questions = _questions_for_page(enhanced, page)
        page_visuals = _visual_refs_for_page(visual_payloads, page)
        page_blocks = [_element_payload(item) for item in page_elements if _element_page(item) == page]
        if not should_call_vision_ai(
            page_blocks=page_blocks,
            parsed_questions=page_questions,
            visual_refs=page_visuals,
            confidence_threshold=_confidence_threshold(),
        ):
            continue
        try:
            request = VisionAIRequest(
                page=page,
                image_base64=_page_image_base64(pdf_path, page, page_image_cache),
                questions=_question_prompt_payloads(page_questions),
                visual_refs=page_visuals,
                page_blocks=page_blocks,
                ocr_text="\n".join(str(item.get("text") or "") for item in page_blocks if item.get("text")),
            )
            response = provider.review_page(request)
            stats["called_pages"].append(page)
            if response.warnings:
                stats.setdefault("model_warnings", []).extend(response.warnings)
            _merge_response(
                questions=enhanced,
                response_page=response.page,
                corrections=response.corrections,
                visual_payloads=visual_payloads,
                provider_name=_provider_name(provider),
            )
        except Exception as exc:
            stats["warnings"].append("vision_ai_failed")
            stats.setdefault("errors", []).append({"page": page, "error": str(exc)})
    return VisionAIEnhancementResult(enhanced, stats)


def should_call_vision_ai(
    *,
    page_blocks: list[dict[str, Any]],
    parsed_questions: list[dict[str, Any]],
    visual_refs: list[dict[str, Any]],
    confidence_threshold: float,
) -> bool:
    if any((item.get("type") in {"image", "table"}) for item in page_blocks):
        return True
    if visual_refs:
        return True
    if any(bool(question.get("needs_review")) for question in parsed_questions):
        return True
    if any(_safe_float(question.get("parse_confidence") or question.get("confidence"), 1.0) < confidence_threshold for question in parsed_questions):
        return True
    if _has_source_visual_overlap(parsed_questions):
        return True
    if _has_shared_visual_ownership(parsed_questions):
        return True
    page_text = "\n".join(str(item.get("text") or "") for item in page_blocks)
    return any(keyword in page_text for keyword in ["资料分析", "图形推理", "数量关系", "表", "图"])


def _merge_response(
    *,
    questions: list[dict[str, Any]],
    response_page: int,
    corrections: list[dict[str, Any]],
    visual_payloads: dict[str, dict[str, Any]],
    provider_name: str,
) -> None:
    for correction in corrections:
        question = _find_question(questions, correction.get("question_id"))
        if not question:
            continue
        confidence = _safe_float(correction.get("confidence"), 0.0)
        if confidence >= AUTO_APPLY_THRESHOLD:
            status = "applied"
            _apply_allowed_updates(question, correction.get("updates") or {}, visual_payloads, correction.get("action"))
        elif confidence >= SUGGESTION_THRESHOLD:
            status = "suggested"
            question["needs_review"] = True
            _append_warning(question, "vision_ai_suggestion_pending")
        else:
            status = "ignored_low_confidence"
        _record_correction(
            question=question,
            correction=correction,
            page=response_page,
            provider_name=provider_name,
            status=status,
            confidence=confidence,
        )


def _apply_allowed_updates(
    question: dict[str, Any],
    updates: dict[str, Any],
    visual_payloads: dict[str, dict[str, Any]],
    action: Any,
) -> None:
    visual_ids = [str(item) for item in updates.get("visual_refs") or [] if str(item)]
    if visual_ids:
        visual_refs: list[dict[str, Any]] = []
        images: list[dict[str, Any]] = []
        for visual_id in visual_ids:
            payload = visual_payloads.get(visual_id)
            if not payload:
                continue
            visual_refs.append(deepcopy(payload["visual_ref"]))
            images.append(deepcopy(payload["image"]))
        if visual_refs:
            question["visual_refs"] = visual_refs
            question["images"] = images
            question["image_refs"] = [item.get("id") for item in visual_refs if item.get("id")]
    if action in {"update_source_bbox", "adjust_source_bbox"} and _valid_bbox(updates.get("source_bbox")):
        question["source_bbox"] = [float(item) for item in updates["source_bbox"]]
    if "warnings" in updates and isinstance(updates["warnings"], list):
        for warning in updates["warnings"]:
            _append_warning(question, str(warning))
    if "need_review" in updates or "needs_review" in updates:
        need_review = bool(updates.get("need_review", updates.get("needs_review")))
        question["needs_review"] = need_review or bool(question.get("parse_warnings"))


def _record_correction(
    *,
    question: dict[str, Any],
    correction: dict[str, Any],
    page: int,
    provider_name: str,
    status: str,
    confidence: float,
) -> None:
    entry = {
        "provider": provider_name,
        "page": page,
        "confidence": confidence,
        "action": str(correction.get("action") or ""),
        "reason": str(correction.get("reason") or ""),
        "status": status,
        "updates": correction.get("updates") if isinstance(correction.get("updates"), dict) else {},
    }
    question.setdefault("ai_corrections", []).append(entry)
    question["ai_confidence"] = max(_safe_float(question.get("ai_confidence"), 0.0), confidence)
    question["ai_provider"] = provider_name
    if entry["reason"]:
        existing = str(question.get("ai_review_notes") or "").strip()
        question["ai_review_notes"] = "\n".join(item for item in [existing, entry["reason"]] if item)


def _candidate_pages(questions: list[dict[str, Any]], page_elements: list[Any], visual_payloads: dict[str, dict[str, Any]]) -> set[int]:
    pages = {_element_page(item) for item in page_elements if _element_type(item) in {"image", "table"}}
    pages.update(_safe_int(payload.get("visual_ref", {}).get("page")) for payload in visual_payloads.values())
    for question in questions:
        if question.get("needs_review") or _safe_float(question.get("parse_confidence") or question.get("confidence"), 1.0) < _confidence_threshold():
            pages.update(_question_pages(question))
    return {page for page in pages if page}


def _questions_for_page(questions: list[dict[str, Any]], page: int) -> list[dict[str, Any]]:
    nearby = {page - 1, page, page + 1}
    result = []
    for question in questions:
        if _question_pages(question) & nearby:
            result.append(question)
    return result


def _question_pages(question: dict[str, Any]) -> set[int]:
    pages: set[int] = set()
    if isinstance(question.get("page_range"), list):
        values = [_safe_int(item) for item in question["page_range"]]
        values = [item for item in values if item]
        if len(values) >= 2:
            pages.update(range(values[0], values[-1] + 1))
        else:
            pages.update(values)
    for key in ("page_num", "source_page_start", "source_page_end"):
        value = _safe_int(question.get(key))
        if value:
            pages.add(value)
    return pages


def _question_prompt_payloads(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for question in questions:
        result.append(
            {
                "id": question.get("id") or f"q{question.get('index') or question.get('index_num')}",
                "index": question.get("index") or question.get("index_num"),
                "content": question.get("content"),
                "source_bbox": question.get("source_bbox"),
                "source_page_start": question.get("source_page_start"),
                "source_page_end": question.get("source_page_end"),
                "visual_refs": question.get("visual_refs") or [],
                "image_refs": question.get("image_refs") or [],
                "needs_review": bool(question.get("needs_review")),
                "parse_confidence": question.get("parse_confidence") or question.get("confidence"),
                "parse_warnings": question.get("parse_warnings") or [],
            }
        )
    return result


def _visual_refs_for_page(visual_payloads: dict[str, dict[str, Any]], page: int) -> list[dict[str, Any]]:
    return [
        deepcopy(payload["visual_ref"])
        for payload in visual_payloads.values()
        if _safe_int(payload.get("visual_ref", {}).get("page")) == page
    ]


def _page_image_base64(pdf_path: str, page: int, cache: dict[int, str]) -> str:
    if not pdf_path:
        return ""
    if page in cache:
        return cache[page]
    pdf = fitz.open(pdf_path)
    try:
        page_obj = pdf[page - 1]
        pix = page_obj.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
        encoded = base64.b64encode(pix.tobytes("png")).decode("ascii")
        cache[page] = encoded
        return encoded
    finally:
        pdf.close()


def _has_source_visual_overlap(questions: list[dict[str, Any]]) -> bool:
    for question in questions:
        source = question.get("source_bbox")
        if not _valid_bbox(source):
            continue
        for visual in question.get("visual_refs") or []:
            if _bbox_intersects(source, visual.get("bbox")):
                return True
    return False


def _has_shared_visual_ownership(questions: list[dict[str, Any]]) -> bool:
    owners: dict[str, int] = {}
    for question in questions:
        for ref in question.get("image_refs") or []:
            owners[str(ref)] = owners.get(str(ref), 0) + 1
        for visual in question.get("visual_refs") or []:
            visual_id = str(visual.get("id") or "")
            if visual_id:
                owners[visual_id] = owners.get(visual_id, 0) + 1
    return any(count > 1 for count in owners.values())


def _find_question(questions: list[dict[str, Any]], question_id: Any) -> dict[str, Any] | None:
    wanted = str(question_id or "").strip()
    if not wanted:
        return None
    for question in questions:
        aliases = {
            str(question.get("id") or ""),
            str(question.get("index") or ""),
            str(question.get("index_num") or ""),
            f"q{question.get('index') or question.get('index_num')}",
        }
        if wanted in aliases:
            return question
    return None


def _append_warning(question: dict[str, Any], warning: str) -> None:
    warnings = [str(item) for item in question.get("parse_warnings") or []]
    if warning not in warnings:
        warnings.append(warning)
    question["parse_warnings"] = warnings


def _element_payload(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return {
            "id": item.get("id"),
            "page": item.get("page"),
            "type": item.get("type"),
            "text": item.get("text"),
            "bbox": item.get("bbox"),
            "order_index": item.get("order_index"),
        }
    return {
        "id": getattr(item, "id", None),
        "page": getattr(item, "page", None),
        "type": getattr(item, "type", None),
        "text": getattr(item, "text", None),
        "bbox": getattr(item, "bbox", None),
        "order_index": getattr(item, "order_index", None),
    }


def _element_page(item: Any) -> int | None:
    return _safe_int(item.get("page") if isinstance(item, dict) else getattr(item, "page", None))


def _element_type(item: Any) -> str:
    return str(item.get("type") if isinstance(item, dict) else getattr(item, "type", "") or "")


def _bbox_intersects(left: Any, right: Any) -> bool:
    if not _valid_bbox(left) or not _valid_bbox(right):
        return False
    return max(left[0], right[0]) < min(left[2], right[2]) and max(left[1], right[1]) < min(left[3], right[3])


def _valid_bbox(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(item, (int, float)) for item in value)
        and value[2] > value[0]
        and value[3] > value[1]
    )


def vision_ai_enabled() -> bool:
    return str(os.getenv("ENABLE_VISION_AI") or "false").strip().lower() in {"1", "true", "yes", "on"}


def _confidence_threshold() -> float:
    return _safe_float(os.getenv("VISION_AI_CONFIDENCE_THRESHOLD"), 0.75)


def _provider_name(provider: VisionAIProvider | None) -> str:
    return str(getattr(provider, "name", None) or os.getenv("VISION_AI_PROVIDER") or "qwen-vl")


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
