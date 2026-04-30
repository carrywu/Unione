from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class QuestionSolvingRequest:
    question_id: str
    question_number: int | None
    stem: str
    options: dict[str, str]
    material: str
    original_answer: str
    original_analysis: str
    visual_refs: list[dict[str, Any]]
    image_refs: list[str]
    ai_review_notes: str
    ai_corrections: list[dict[str, Any]]
    visual_descriptions: list[str]
    source_page: int | None
    parse_warnings: list[str]
    needs_review: bool
    model: str | None = None


@dataclass
class QuestionSolvingResponse:
    question_id: str
    ai_candidate_answer: str
    ai_candidate_analysis: str
    ai_answer_confidence: float
    ai_reasoning_summary: str
    ai_knowledge_points: list[str] = field(default_factory=list)
    ai_risk_flags: list[str] = field(default_factory=list)
    answer_conflict: bool = False
    raw_response: Any | None = None

    @classmethod
    def from_model_output(cls, value: Any, fallback_question_id: str) -> "QuestionSolvingResponse":
        if not isinstance(value, dict):
            raise ValueError("ai_solver_response_not_object")
        knowledge_points = value.get("ai_knowledge_points")
        risk_flags = value.get("ai_risk_flags")
        return cls(
            question_id=str(value.get("question_id") or fallback_question_id),
            ai_candidate_answer=str(value.get("ai_candidate_answer") or "").strip(),
            ai_candidate_analysis=str(value.get("ai_candidate_analysis") or "").strip(),
            ai_answer_confidence=_safe_float(value.get("ai_answer_confidence"), 0.0),
            ai_reasoning_summary=str(value.get("ai_reasoning_summary") or "").strip(),
            ai_knowledge_points=[str(item) for item in knowledge_points] if isinstance(knowledge_points, list) else [],
            ai_risk_flags=[str(item) for item in risk_flags] if isinstance(risk_flags, list) else [],
            answer_conflict=bool(value.get("answer_conflict")),
            raw_response=value,
        )


@dataclass
class AISolverEnhancementResult:
    questions: list[dict[str, Any]]
    stats: dict[str, Any]


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
