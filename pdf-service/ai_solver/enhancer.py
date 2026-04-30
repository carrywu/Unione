from __future__ import annotations

import os
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from ai_solver.bailian_deepseek_provider import resolve_default_model
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
            first_model = _first_pass_model(question)
            request = _request_for_question(question, material_by_id, model=first_model)
            response = provider.solve_question(request)
            response, final_model, recheck_meta = _maybe_recheck_with_pro(
                question=question,
                request=request,
                first_response=response,
                first_model=first_model,
                provider=provider,
                stats=stats,
            )
            _apply_response(
                question=question,
                response=response,
                provider_name=_provider_name(provider),
                first_model=first_model,
                final_model=final_model,
                recheck_meta=recheck_meta,
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
    first_model: str,
    final_model: str,
    recheck_meta: dict[str, Any] | None = None,
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
    question["ai_solver_model"] = final_model
    question["ai_solver_first_model"] = first_model
    question["ai_solver_final_model"] = final_model
    question["ai_solver_rechecked"] = bool(recheck_meta)
    question["ai_solver_recheck_reason"] = (recheck_meta or {}).get("reason") or None
    question["ai_solver_recheck_result"] = (recheck_meta or {}).get("result")
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
    *,
    model: str,
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
        model=model,
    )


def _maybe_recheck_with_pro(
    *,
    question: dict[str, Any],
    request: QuestionSolvingRequest,
    first_response: QuestionSolvingResponse,
    first_model: str,
    provider: QuestionSolverProvider,
    stats: dict[str, Any],
) -> tuple[QuestionSolvingResponse, str, dict[str, Any] | None]:
    reason = _pro_recheck_reason(question, first_response)
    if not _pro_recheck_enabled() or not reason:
        return first_response, first_model, None
    pro_model = _pro_model()
    if pro_model == first_model:
        return first_response, first_model, None
    try:
        pro_response = provider.solve_question(replace(request, model=pro_model))
    except Exception as exc:
        stats["warnings"].append("ai_solver_pro_recheck_failed")
        stats.setdefault("errors", []).append(
            {
                "question_id": request.question_id,
                "error": str(exc),
                "stage": "pro_recheck",
            }
        )
        _append_warning(question, "ai_solver_pro_recheck_failed")
        question["needs_review"] = True
        return first_response, first_model, None

    first_confidence = _safe_float(first_response.ai_answer_confidence, 0.0)
    pro_confidence = _safe_float(pro_response.ai_answer_confidence, 0.0)
    use_pro = pro_confidence > first_confidence
    selected_response = pro_response if use_pro else first_response
    selected_model = pro_model if use_pro else first_model
    return (
        selected_response,
        selected_model,
        {
            "reason": reason,
            "result": {
                "previous_result": _response_payload(first_response, first_model),
                "pro_result": _response_payload(pro_response, pro_model),
                "selected_result": "pro" if use_pro else "first",
            },
        },
    )


def _pro_recheck_reason(question: dict[str, Any], response: QuestionSolvingResponse) -> str:
    reasons: list[str] = []
    confidence = _safe_float(response.ai_answer_confidence, 0.0)
    if confidence < _pro_recheck_threshold():
        reasons.append("low_confidence")
    if _response_conflicts_with_official(question, response):
        reasons.append("answer_conflict")
    risk_flags = {str(item) for item in response.ai_risk_flags or []}
    if "missing_context" in risk_flags:
        reasons.append("missing_context")
    if confidence < _confidence_threshold():
        reasons.append("low_ai_answer_confidence")
    if _is_high_risk_visual_question(question, risk_flags):
        reasons.append("high_risk_visual_table")
    return ",".join(_dedupe(reasons))


def _response_conflicts_with_official(question: dict[str, Any], response: QuestionSolvingResponse) -> bool:
    original_answer = str(question.get("answer") or "").strip()
    candidate_answer = str(response.ai_candidate_answer or "").strip()
    if bool(response.answer_conflict):
        return True
    return bool(original_answer and candidate_answer and _normalize_answer(original_answer) != _normalize_answer(candidate_answer))


def _is_high_risk_visual_question(question: dict[str, Any], risk_flags: set[str]) -> bool:
    has_visual = bool(question.get("visual_refs") or question.get("images") or question.get("image_refs"))
    if not has_visual:
        return False
    return bool(
        question.get("needs_review")
        or question.get("need_review")
        or question.get("parse_warnings")
        or question.get("ai_corrections")
        or risk_flags.intersection({"requires_table", "missing_context", "requires_chart"})
    )


def _response_payload(response: QuestionSolvingResponse, model: str) -> dict[str, Any]:
    return {
        "model": model,
        "question_id": response.question_id,
        "ai_candidate_answer": response.ai_candidate_answer,
        "ai_candidate_analysis": response.ai_candidate_analysis,
        "ai_answer_confidence": response.ai_answer_confidence,
        "ai_reasoning_summary": response.ai_reasoning_summary,
        "ai_knowledge_points": list(response.ai_knowledge_points or []),
        "ai_risk_flags": list(response.ai_risk_flags or []),
        "answer_conflict": bool(response.answer_conflict),
    }


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


def _first_pass_model(question: dict[str, Any]) -> str:
    if _needs_reasoner_model(question):
        return _configured_model("REASONER")
    return _configured_model("FAST")


def _needs_reasoner_model(question: dict[str, Any]) -> bool:
    if question.get("visual_refs") or question.get("images") or question.get("image_refs"):
        return True
    if question.get("needs_review") or question.get("need_review"):
        return True
    if question.get("ai_answer_conflict"):
        return True
    if question.get("parse_warnings") or question.get("ai_corrections"):
        return True
    text = "\n".join(
        str(value or "")
        for value in [
            question.get("content"),
            question.get("material_text"),
            question.get("ai_review_notes"),
            " ".join(_visual_descriptions(question)),
        ]
    )
    reasoner_keywords = [
        "数量关系",
        "判断推理",
        "资料分析",
        "图形推理",
        "表格",
        "图表",
        "统计表",
        "增长率",
        "同比",
        "环比",
    ]
    return any(keyword in text for keyword in reasoner_keywords)


def _configured_model(route: str) -> str:
    routed_model = (os.getenv(f"BAILIAN_DEEPSEEK_{route}_MODEL") or "").strip()
    return routed_model or resolve_default_model()


def _pro_model() -> str:
    return _configured_model("PRO")


def _pro_recheck_enabled() -> bool:
    return str(os.getenv("ENABLE_AI_SOLVER_PRO_RECHECK") or "false").strip().lower() in {"1", "true", "yes", "on"}


def _pro_recheck_threshold() -> float:
    return _safe_float(os.getenv("AI_SOLVER_PRO_RECHECK_THRESHOLD"), 0.75)


def _provider_name(provider: QuestionSolverProvider | None) -> str:
    return str(getattr(provider, "name", None) or os.getenv("AI_SOLVER_PROVIDER") or "bailian-deepseek")


def _provider_model(provider: QuestionSolverProvider | None) -> str:
    return str(getattr(provider, "model", None) or resolve_default_model())


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
