from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class VisionAIRequest:
    page: int
    image_base64: str
    questions: list[dict[str, Any]]
    visual_refs: list[dict[str, Any]]
    page_blocks: list[dict[str, Any]]
    ocr_text: str


@dataclass
class VisionAIResponse:
    page: int
    corrections: list[dict[str, Any]] = field(default_factory=list)
    question_reviews: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    prompt: str | None = None
    request_payload: dict[str, Any] | None = None
    raw_response: Any | None = None

    @classmethod
    def from_model_output(
        cls,
        value: Any,
        fallback_page: int,
        *,
        prompt: str | None = None,
        request_payload: dict[str, Any] | None = None,
    ) -> "VisionAIResponse":
        if not isinstance(value, dict):
            raise ValueError("vision_ai_response_not_object")
        page = _safe_int(value.get("page")) or fallback_page
        corrections = value.get("corrections") if isinstance(value.get("corrections"), list) else []
        question_reviews = value.get("questions") if isinstance(value.get("questions"), list) else []
        if not question_reviews and isinstance(value.get("question_reviews"), list):
            question_reviews = value.get("question_reviews")
        warnings = value.get("warnings") if isinstance(value.get("warnings"), list) else []
        return cls(
            page=page,
            corrections=[item for item in corrections if isinstance(item, dict)],
            question_reviews=[item for item in question_reviews if isinstance(item, dict)],
            warnings=[item for item in warnings if isinstance(item, dict)],
            prompt=prompt,
            request_payload=request_payload,
            raw_response=value,
        )


@dataclass
class VisionAIEnhancementResult:
    questions: list[dict[str, Any]]
    stats: dict[str, Any]


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
