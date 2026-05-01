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
            stats.setdefault("qwen_vl_raw_outputs", []).append(
                {
                    "page": response.page,
                    "prompt": response.prompt,
                    "request_payload": response.request_payload,
                    "raw_response": response.raw_response,
                },
            )
            if response.warnings:
                stats.setdefault("model_warnings", []).extend(response.warnings)
            _merge_response(
                questions=enhanced,
                response_page=response.page,
                corrections=response.corrections,
                question_reviews=response.question_reviews,
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
    question_reviews: list[dict[str, Any]],
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
    for review in question_reviews:
        _apply_question_review(
            questions=questions,
            response_page=response_page,
            review=review,
            visual_payloads=visual_payloads,
            provider_name=provider_name,
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


def _apply_question_review(
    *,
    questions: list[dict[str, Any]],
    response_page: int,
    review: dict[str, Any],
    visual_payloads: dict[str, dict[str, Any]],
    provider_name: str,
) -> None:
    question = _find_question(questions, review.get("question_id") or review.get("id"))
    if not question:
        question = _find_question(questions, f"q{review.get('question_no') or review.get('index') or ''}")
    if not question:
        return

    visuals = [item for item in review.get("visuals") or [] if isinstance(item, dict)]
    visual_statuses: list[str] = []
    visual_summaries: list[str] = []
    visual_confidences: list[float] = []
    visual_errors: list[str] = []
    for visual in visuals:
        _apply_visual_review(question, visual, visual_payloads, review)
        summary = str(visual.get("visual_summary") or "").strip()
        if summary:
            visual_summaries.append(summary)
        status = str(visual.get("visual_parse_status") or ("success" if summary else "")).strip()
        if status:
            visual_statuses.append(status)
        confidence = _safe_float(visual.get("confidence") or visual.get("visual_confidence"), None)
        if confidence is not None:
            visual_confidences.append(confidence)
        error = str(visual.get("visual_error") or "").strip()
        if error:
            visual_errors.append(error)

    understanding = review.get("understanding") if isinstance(review.get("understanding"), dict) else {}
    answer = review.get("answer_suggestion") if isinstance(review.get("answer_suggestion"), dict) else {}
    analysis = review.get("analysis_suggestion") if isinstance(review.get("analysis_suggestion"), dict) else {}
    audit = review.get("ai_audit") if isinstance(review.get("ai_audit"), dict) else {}
    quality = review.get("question_quality") if isinstance(review.get("question_quality"), dict) else {}

    candidate_answer = _normalize_candidate_answer(answer.get("answer"))
    if candidate_answer:
        question["ai_candidate_answer"] = candidate_answer
    answer_confidence = _safe_float(answer.get("confidence"), None)
    if answer_confidence is not None:
        question["ai_answer_confidence"] = answer_confidence
    answer_unknown_reason = str(answer.get("answer_unknown_reason") or "").strip()
    if answer_unknown_reason:
        question["answer_unknown_reason"] = answer_unknown_reason

    analysis_text = str(analysis.get("text") or analysis.get("analysis") or "").strip()
    if analysis_text:
        question["ai_candidate_analysis"] = analysis_text
    analysis_unknown_reason = str(analysis.get("analysis_unknown_reason") or "").strip()
    if analysis_unknown_reason:
        question["analysis_unknown_reason"] = analysis_unknown_reason

    reasoning = str(answer.get("reasoning") or understanding.get("question_intent") or "").strip()
    if reasoning:
        question["ai_reasoning_summary"] = reasoning
    question_type = str(review.get("question_type") or "").strip()
    if question_type:
        question["ai_knowledge_points"] = _dedupe([*(question.get("ai_knowledge_points") or []), question_type])

    if visual_summaries:
        question["visual_summary"] = "\n".join(_dedupe(visual_summaries))
    if visual_confidences:
        question["visual_confidence"] = max(visual_confidences)
    if visual_errors:
        question["visual_error"] = "\n".join(_dedupe(visual_errors))
    if visual_statuses:
        question["visual_parse_status"] = _aggregate_visual_status(visual_statuses)
    elif visuals:
        question["visual_parse_status"] = "partial"
    question["has_visual_context"] = bool(visuals or question.get("images") or question.get("visual_refs"))

    audit_status = _normalize_audit_status(audit.get("status"))
    audit_verdict = str(audit.get("verdict") or _audit_verdict_for_status(audit_status)).strip()
    question["ai_audit_status"] = audit_status
    question["ai_audit_verdict"] = audit_verdict
    question["ai_audit_summary"] = str(
        audit.get("summary")
        or audit.get("ai_audit_summary")
        or answer.get("reasoning")
        or analysis_text
        or audit_verdict
    ).strip()
    can_answer = bool(understanding.get("can_answer_from_available_context"))
    question["ai_can_understand_question"] = bool(understanding.get("question_intent") or can_answer or analysis_text)
    question["ai_can_solve_question"] = bool(can_answer and (candidate_answer or answer_unknown_reason == ""))
    question["ai_reviewed_before_human"] = True
    question["ai_review_error"] = None
    if quality:
        question["question_quality"] = quality

    risk_flags = [
        *(question.get("ai_risk_flags") or []),
        *[str(item) for item in audit.get("risk_flags") or []],
        *[str(item) for item in audit.get("review_reasons") or []],
        *[str(item) for item in quality.get("review_reasons") or []],
    ]
    missing_context = understanding.get("missing_context")
    if isinstance(missing_context, list) and missing_context:
        risk_flags.append("missing_context")
    if answer_unknown_reason:
        risk_flags.append(answer_unknown_reason)
    if analysis_unknown_reason:
        risk_flags.append(analysis_unknown_reason)
    question["ai_risk_flags"] = _dedupe([str(item) for item in risk_flags if str(item).strip()])

    confidence_candidates = [
        _safe_float(question.get("ai_confidence"), 0.0),
        _safe_float(question.get("ai_answer_confidence"), 0.0),
        _safe_float(question.get("visual_confidence"), 0.0),
    ]
    question["ai_confidence"] = max(confidence_candidates)
    question["ai_provider"] = provider_name
    question.setdefault("ai_corrections", [])
    question["ai_corrections"].append(
        {
            "provider": provider_name,
            "page": response_page,
            "confidence": question["ai_confidence"],
            "action": "ai_preaudit",
            "reason": question["ai_audit_summary"],
            "status": "applied" if audit_status == "passed" else "suggested",
            "updates": {"ai_audit_status": audit_status, "ai_audit_verdict": audit_verdict},
        }
    )

    needs_review = bool(
        audit.get("needs_review")
        or quality.get("needs_review")
        or question["ai_risk_flags"]
        or audit_status in {"warning", "failed", "skipped"}
        or not question["ai_can_solve_question"]
    )
    question["needs_review"] = bool(question.get("needs_review") or needs_review)
    if question["needs_review"]:
        _append_warning(question, "ai_preaudit_needs_review")


def _apply_visual_review(
    question: dict[str, Any],
    visual: dict[str, Any],
    visual_payloads: dict[str, dict[str, Any]],
    review: dict[str, Any],
) -> None:
    visual_id = str(visual.get("visual_id") or visual.get("id") or visual.get("ref") or "").strip()
    if visual_id and visual.get("belongs_to_question") is True and not _has_visual_ref(question, visual_id):
        payload = visual_payloads.get(visual_id)
        if payload:
            question.setdefault("visual_refs", []).append(deepcopy(payload["visual_ref"]))
            question.setdefault("images", []).append(deepcopy(payload["image"]))
            question["image_refs"] = _dedupe([*(question.get("image_refs") or []), visual_id])

    for collection_name in ["images", "visual_refs"]:
        for item in question.get(collection_name) or []:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("ref") or item.get("id") or "").strip()
            if visual_id and item_id and item_id != visual_id:
                continue
            item["belongs_to_question"] = bool(visual.get("belongs_to_question"))
            item["linked_question_no"] = review.get("question_no") or review.get("index") or question.get("index")
            item["linked_question_id"] = question.get("id") or f"q{question.get('index') or question.get('index_num')}"
            item["linked_by"] = visual.get("linked_by") or "ai"
            item["link_reason"] = str(visual.get("link_reason") or "").strip()
            item["image_role"] = visual.get("image_role") or item.get("image_role") or item.get("role") or "unknown"
            item["visual_summary"] = str(visual.get("visual_summary") or item.get("visual_summary") or "").strip()
            item["visual_parse_status"] = str(visual.get("visual_parse_status") or item.get("visual_parse_status") or ("success" if item["visual_summary"] else "partial")).strip()
            item["visual_confidence"] = _safe_float(visual.get("confidence") or visual.get("visual_confidence"), item.get("visual_confidence"))
            item["visual_error"] = visual.get("visual_error") or item.get("visual_error")


def _has_visual_ref(question: dict[str, Any], visual_id: str) -> bool:
    for item in [*(question.get("visual_refs") or []), *(question.get("images") or [])]:
        if isinstance(item, dict) and str(item.get("id") or item.get("ref") or "") == visual_id:
            return True
    return False


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


def _normalize_candidate_answer(value: Any) -> str:
    answer = str(value or "").strip().upper()
    if answer in {"A", "B", "C", "D", "对", "错"}:
        return answer
    return ""


def _normalize_audit_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    return status if status in {"passed", "warning", "failed", "skipped"} else "warning"


def _audit_verdict_for_status(status: str) -> str:
    return {
        "passed": "可通过",
        "warning": "需复核",
        "failed": "不建议入库",
        "skipped": "需复核",
    }.get(status, "需复核")


def _aggregate_visual_status(statuses: list[str]) -> str:
    normalized = {str(item or "").strip().lower() for item in statuses}
    if "failed" in normalized:
        return "failed" if normalized <= {"failed"} else "partial"
    if "partial" in normalized:
        return "partial"
    if "success" in normalized:
        return "success"
    if "skipped" in normalized:
        return "skipped"
    return "partial"


def _dedupe(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


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
