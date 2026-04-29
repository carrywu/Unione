from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


AnswerParseMode = Literal["text", "image"]
AnswerBookMode = Literal["text", "image", "auto"]


class AnswerCandidate(BaseModel):
    section_key: str | None = None
    question_index: int
    question_anchor: str | None = None
    answer: str | None = None
    analysis_text: str | None = None
    analysis_image_url: str | None = None
    analysis_image_base64: str | None = None
    image_width: int | None = None
    image_height: int | None = None
    source_page_num: int
    source_page_range: list[int] | None = None
    source_bbox: list[float] | None = None
    raw_text: str | None = None
    confidence: int
    parse_mode: AnswerParseMode


class AnswerBookParseResult(BaseModel):
    status: str = "success"
    mode: AnswerParseMode
    candidates: list[AnswerCandidate]
    stats: dict[str, Any]
