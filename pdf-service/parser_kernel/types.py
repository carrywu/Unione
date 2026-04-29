from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


ElementKind = Literal["text", "region"]
SemanticRole = Literal[
    "unknown",
    "question_anchor",
    "option",
    "material_prompt",
    "material_body",
    "teaching_text",
    "directory_heading",
    "question_body",
]


@dataclass
class PageElement:
    page_num: int
    order_index: int
    bbox: list[float]
    text: str
    kind: ElementKind = "text"
    semantic_role: SemanticRole = "unknown"


@dataclass
class MaterialGroup:
    id: str
    prompt_text: str
    body_text: str
    question_range: tuple[int, int] | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class QuestionGroup:
    index: int
    text: str
    page_num: int
    y0: float
    y1: float
    material_id: str | None = None
    warnings: list[str] = field(default_factory=list)
