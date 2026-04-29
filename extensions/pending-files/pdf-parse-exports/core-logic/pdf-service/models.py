from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class Region(BaseModel):
    type: str
    bbox: List[float]
    base64: str


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
    source: Optional[str] = None
    raw_text: Optional[str] = None
    parse_confidence: Optional[float] = None


class Material(BaseModel):
    id: str
    content: str
    images: List[QuestionImage] = []


class ParseStats(BaseModel):
    total_pages: int
    total_questions: int
    has_images: bool
    needs_review_count: int
    filtered_out: int = 0
    with_images: int = 0
    detection: Optional[Dict[str, Any]] = None
    strategy: Optional[str] = None


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
