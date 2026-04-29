from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

BBox = list[float]


@dataclass
class LayoutElement:
    id: str
    page: int
    type: Literal[
        "text",
        "image",
        "table",
        "caption",
        "heading",
        "option",
        "question_marker",
        "material_marker",
        "answer_marker",
    ]
    text: str | None
    bbox: BBox
    image_path: str | None
    markdown: str | None
    order_index: int
    confidence: float = 1.0


@dataclass
class VisualCandidate:
    target_id: str
    target_type: Literal["question", "material"]
    score: float
    reasons: list[str] = field(default_factory=list)


@dataclass
class VisualBlock:
    id: str
    page: int
    kind: Literal["image", "table", "chart"]
    bbox: BBox
    image_path: str
    raw_bbox: BBox | None = None
    expanded_bbox: BBox | None = None
    absorbed_texts: list[dict[str, Any]] = field(default_factory=list)
    caption: str | None = None
    nearby_text_before: str | None = None
    nearby_text_after: str | None = None
    assigned_to: str | None = None
    assigned_type: Literal["question", "material"] | None = None
    assignment_confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)
    candidates: list[VisualCandidate] = field(default_factory=list)


@dataclass
class QuestionCoreBlock:
    id: str
    index: int
    source: str | None
    page_start: int
    page_end: int
    marker_text: str
    stem_text: str
    options: dict[str, str]
    element_ids: list[str]
    bbox_range: list[BBox]
    raw_markdown: str
    source_element_ids: list[str] = field(default_factory=list)
    source_bbox_range: list[BBox] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class SharedMaterialBlock:
    id: str
    title: str | None
    content: str
    question_range: tuple[int, int] | None
    page_start: int
    page_end: int
    visual_ids: list[str]
    element_ids: list[str]
    raw_markdown: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class ExerciseBlock:
    id: str
    question_core: QuestionCoreBlock
    material_id: str | None
    visual_ids: list[str]
    page_range: tuple[int, int]
    source_bbox: BBox | None
    source_anchor_text: str | None
    raw_markdown: str
    parse_confidence: float
    warnings: list[str] = field(default_factory=list)
