from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class Region(BaseModel):
    type: str
    bbox: List[float]
    base64: str
    caption: Optional[str] = None
    page: Optional[int] = None
    same_visual_group_id: Optional[str] = None
    assignment_confidence: Optional[float] = None


class TextBlock(BaseModel):
    bbox: List[float]
    text: str


class PageContent(BaseModel):
    page_num: int
    text: str
    blocks: List[TextBlock]
    regions: List[Region]


class RawQuestion(BaseModel):
    index: int
    text: str
    page_num: int
    y0: float
    y1: float
    images: List[Region] = []
    material_id: Optional[str] = None
    material_text: Optional[str] = None


class QuestionImage(BaseModel):
    base64: str
    url: Optional[str] = None
    ref: Optional[str] = None
    caption: Optional[str] = None
    page: Optional[int] = None
    role: Optional[str] = None
    image_role: Optional[str] = None
    image_order: Optional[int] = None
    insert_position: Optional[str] = None
    bbox: Optional[List[float]] = None
    same_visual_group_id: Optional[str] = None
    assignment_confidence: Optional[float] = None
    ai_desc: Optional[str] = None


class Question(BaseModel):
    index: int
    type: str = "single"
    content: str
    options: Optional[Dict[str, str]] = None
    answer: Optional[str] = None
    analysis: Optional[str] = None
    images: List[QuestionImage] = []
    material_id: Optional[str] = None
    needs_review: bool = False
    page_num: Optional[int] = None
    page_range: Optional[List[int]] = None
    source_page_start: Optional[int] = None
    source_page_end: Optional[int] = None
    source_bbox: Optional[List[float]] = None
    source_anchor_text: Optional[str] = None
    source_confidence: Optional[float] = None
    image_refs: List[str] = []
    visual_refs: List[Dict[str, Any]] = []
    source: Optional[str] = None
    raw_text: Optional[str] = None
    parse_confidence: Optional[float] = None
    parse_warnings: List[str] = []


class Material(BaseModel):
    id: str
    content: str
    images: List[QuestionImage] = []
    page_range: Optional[List[int]] = None
    image_refs: List[str] = []
    raw_text: Optional[str] = None
    parse_warnings: List[str] = []


class ParseStats(BaseModel):
    total_pages: int
    total_questions: int
    has_images: bool
    needs_review_count: int
    filtered_out: int = 0
    with_images: int = 0
    detection: Optional[Dict[str, Any]] = None
    strategy: Optional[str] = None
    suspected_bad_parse: bool = False
    warnings: List[str] = []
    debug_counts: Dict[str, int] = {}
    scanned_fallback_debug: Optional[Dict[str, Any]] = None


class ParseResult(BaseModel):
    questions: List[Question]
    materials: List[Material]
    stats: ParseStats


class ParseByUrlRequest(BaseModel):
    url: str
    ai_config: Optional[Dict[str, str]] = None
    callback_url: Optional[str] = None
    callback_token: Optional[str] = None
    callback_batch_size: int = 20


class ParseAnswerBookByUrlRequest(BaseModel):
    url: str
    mode: str = "auto"
    ai_config: Optional[Dict[str, str]] = None
