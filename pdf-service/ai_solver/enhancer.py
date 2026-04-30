from __future__ import annotations

import os
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from ai_solver.bailian_deepseek_provider import provider_from_env
from ai_solver.base import QuestionSolverProvider
from ai_solver.schema import AISolverEnhancementResult, QuestionSolvingRequest, QuestionSolvingResponse


def enhance_questions_with_ai_solver(
    *,
    questions: list[dict[str, Any]],
    materials: list[dict[str, Any]] | None = None,
    provider: QuestionSolverProvider | None = None,
) -> AISolverEnhancementResult:
    stats: dict[str, Any] = {
        "enabled": ai_solver_enabled(),
        "provider": _provider_name(provider),
        "model": _provider_model(provider),
        "scope": _solver_scope(),
        "solved_question_ids": [],
        "warnings": [],
    }
    enhanced = deepcopy(questions)
    if not stats["enabled"]:
        return AISolverEnhancementResult(enhanced, stats)

    provider = provider or provider_from_env()
    if not provider:
        stats["warnings"].append("ai_solver_api_key_missing")
        return AISolverEnhancementResult(enhanced, stats)
    stats["provider"] = _provider_name(provider)
    stats["model"] = _provider_model(provider)

    material_by_id = _material_by_id(materials or [])
    scope = _solver_scope()
    for question in enhanced:
        if not should_solve_question(question, scope=scope):
            continue
        try:
            request = _request_for_question(question, material_by_id)
            response = provider.solve_question(request)
            _apply_response(
                question=question,
                response=response,
                provider_name=_provider_name(provider),
                model=_provider_model(provider),
            )
            stats["solved_question_ids"].append(request.question_id)
        except Exception as exc:
            stats["warnings"].append("ai_solver_failed")
            stats.setdefault("errors", []).append(
                {
                    "question_id": _question_id(question),
                    "error": str(exc),
                }
            )
            _append_warning(question, "ai_solver_failed")
            question["needs_review"] = True
    return AISolverEnhancementResult(enhanced, stats)


def should_solve_question(question: dict[str, Any], *, scope: str | None = None) -> bool:
    scope = (scope or _solver_scope()).strip().lower()
    if scope == "all":
        return True
    return bool(
        question.get("needs_review")
        or question.get("need_review")
        or question.get("visual_refs")
        or question.get("images")
        or question.get("image_refs")
        or question.get("ai_corrections")
    )


def ai_solver_enabled() -> bool:
    return str(os.getenv("ENABLE_AI_SOLVER") or "false").strip().lower() in {"1", "true", "yes", "on"}


def _apply_response(
    *,
    question: dict[str, Any],
    response: QuestionSolvingResponse,
    provider_name: str,
    model: str,
) -> None:
    confidence = _safe_float(response.ai_answer_confidence, 0.0)
    candidate_answer = str(response.ai_candidate_answer or "").strip()
    original_answer = str(question.get("answer") or "").strip()
    conflict = bool(response.answer_conflict)
    if original_answer and candidate_answer:
        conflict = conflict or _normalize_answer(original_answer) != _normalize_answer(candidate_answer)

    question["ai_candidate_answer"] = candidate_answer
    question["ai_candidate_analysis"] = str(response.ai_candidate_analysis or "").strip()
    question["ai_answer_confidence"] = confidence
    question["ai_reasoning_summary"] = str(response.ai_reasoning_summary or "").strip()
    question["ai_knowledge_points"] = [str(item) for item in response.ai_knowledge_points or []]
    question["ai_risk_flags"] = [str(item) for item in response.ai_risk_flags or []]
    question["ai_solver_provider"] = provider_name
    question["ai_solver_model"] = model
    question["ai_solver_created_at"] = _utc_now()
    question["ai_answer_conflict"] = conflict

    if conflict:
        question["needs_review"] = True
        _append_warning(question, "ai_answer_conflict")
    if confidence < _confidence_threshold():
        question["needs_review"] = True
        _append_warning(question, "low_ai_answer_confidence")
    if question["ai_risk_flags"]:
        question["needs_review"] = True


def _request_for_question(
    question: dict[str, Any],
    material_by_id: dict[str, dict[str, Any]],
) -> QuestionSolvingRequest:
    material = _question_material(question, material_by_id)
    return QuestionSolvingRequest(
        question_id=_question_id(question),
        question_number=_safe_int(question.get("index") or question.get("index_num")),
        stem=str(question.get("content") or ""),
        options=_question_options(question),
        material=material,
        original_answer=str(question.get("answer") or ""),
        original_analysis=str(question.get("analysis") or ""),
        visual_refs=[item for item in question.get("visual_refs") or [] if isinstance(item, dict)],
        image_refs=[str(item) for item in question.get("image_refs") or []],
        ai_review_notes=str(question.get("ai_review_notes") or ""),
        ai_corrections=[item for item in question.get("ai_corrections") or [] if isinstance(item, dict)],
        visual_descriptions=_visual_descriptions(question),
        source_page=_safe_int(question.get("source_page_start") or question.get("page_num")),
        parse_warnings=[str(item) for item in question.get("parse_warnings") or []],
        needs_review=bool(question.get("needs_review") or question.get("need_review")),
    )


def _question_options(question: dict[str, Any]) -> dict[str, str]:
    options = question.get("options") if isinstance(question.get("options"), dict) else {}
    result: dict[str, str] = {}
    for key in ["A", "B", "C", "D"]:
        value = options.get(key) or options.get(key.lower()) or question.get(f"option_{key.lower()}")
        if value:
            result[key] = str(value)
    return result


def _question_material(question: dict[str, Any], material_by_id: dict[str, dict[str, Any]]) -> str:
    direct = question.get("material")
    if isinstance(direct, dict):
        return str(direct.get("content") or "")
    if isinstance(direct, str):
        return direct
    material_id = str(question.get("material_temp_id") or question.get("material_id") or "")
    if material_id and material_id in material_by_id:
        return str(material_by_id[material_id].get("content") or "")
    return str(question.get("material_text") or "")


def _visual_descriptions(question: dict[str, Any]) -> list[str]:
    descriptions: list[str] = []
    for image in question.get("images") or []:
        if not isinstance(image, dict):
            continue
        for key in ["ai_desc", "caption", "ref"]:
            value = image.get(key)
            if value:
                descriptions.append(str(value))
        for absorbed in image.get("absorbed_texts") or []:
            if isinstance(absorbed, dict) and absorbed.get("text"):
                descriptions.append(str(absorbed["text"]))
    for visual in question.get("visual_refs") or []:
        if not isinstance(visual, dict):
            continue
        for key in ["caption", "id"]:
            value = visual.get(key)
            if value:
                descriptions.append(str(value))
        for absorbed in visual.get("absorbed_texts") or []:
            if isinstance(absorbed, dict) and absorbed.get("text"):
                descriptions.append(str(absorbed["text"]))
    return _dedupe(descriptions)


def _material_by_id(materials: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for material in materials:
        for key in [material.get("id"), material.get("temp_id")]:
            if key:
                result[str(key)] = material
    return result


def _append_warning(question: dict[str, Any], warning: str) -> None:
    warnings = [str(item) for item in question.get("parse_warnings") or []]
    if warning not in warnings:
        warnings.append(warning)
    question["parse_warnings"] = warnings


def _question_id(question: dict[str, Any]) -> str:
    return str(question.get("id") or f"q{question.get('index') or question.get('index_num') or ''}").strip()


def _solver_scope() -> str:
    scope = str(os.getenv("AI_SOLVER_SCOPE") or "review_only").strip().lower()
    return scope if scope in {"review_only", "all"} else "review_only"


def _confidence_threshold() -> float:
    return _safe_float(os.getenv("AI_SOLVER_CONFIDENCE_THRESHOLD"), 0.7)


def _provider_name(provider: QuestionSolverProvider | None) -> str:
    return str(getattr(provider, "name", None) or os.getenv("AI_SOLVER_PROVIDER") or "bailian-deepseek")


def _provider_model(provider: QuestionSolverProvider | None) -> str:
    return str(getattr(provider, "model", None) or os.getenv("BAILIAN_DEEPSEEK_MODEL") or "deepseek-r1")


def _normalize_answer(value: str) -> str:
    return str(value or "").strip().upper().replace("．", ".").replace("。", ".").rstrip(".、")


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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
