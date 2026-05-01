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
    visual_parse_status: Optional[str] = None
    visual_summary: Optional[str] = None
    visual_confidence: Optional[float] = None
    visual_error: Optional[str] = None
    belongs_to_question: Optional[bool] = None
    linked_question_no: Optional[int] = None
    linked_question_id: Optional[str] = None
    linked_by: Optional[str] = None
    visual_role: Optional[str] = None
    link_reason: Optional[str] = None
    visual_parse_input: Optional[dict] = None


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
    raw_bbox: Optional[List[float]] = None
    expanded_bbox: Optional[List[float]] = None
    absorbed_texts: List[Dict[str, Any]] = []
    same_visual_group_id: Optional[str] = None
    child_visual_ids: List[str] = []
    assignment_confidence: Optional[float] = None
    ai_desc: Optional[str] = None
    visual_parse_status: Optional[str] = None
    visual_summary: Optional[str] = None
    visual_confidence: Optional[float] = None
    visual_error: Optional[str] = None
    belongs_to_question: Optional[bool] = None
    linked_question_no: Optional[int] = None
    linked_question_id: Optional[str] = None
    linked_by: Optional[str] = None
    link_reason: Optional[str] = None


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
    ai_corrections: List[Dict[str, Any]] = []
    ai_confidence: Optional[float] = None
    ai_provider: Optional[str] = None
    ai_review_notes: Optional[str] = None
    ai_candidate_answer: Optional[str] = None
    ai_candidate_analysis: Optional[str] = None
    ai_answer_confidence: Optional[float] = None
    ai_reasoning_summary: Optional[str] = None
    ai_knowledge_points: List[str] = []
    ai_risk_flags: List[str] = []
    ai_solver_provider: Optional[str] = None
    ai_solver_model: Optional[str] = None
    ai_solver_first_model: Optional[str] = None
    ai_solver_final_model: Optional[str] = None
    ai_solver_rechecked: Optional[bool] = None
    ai_solver_recheck_reason: Optional[str] = None
    ai_solver_recheck_result: Optional[Dict[str, Any]] = None
    ai_solver_created_at: Optional[str] = None
    ai_answer_conflict: Optional[bool] = None
    visual_summary: Optional[str] = None
    visual_confidence: Optional[float] = None
    visual_parse_status: Optional[str] = None
    visual_error: Optional[str] = None
    visual_risk_flags: List[str] = []
    has_visual_context: Optional[bool] = None
    answer_unknown_reason: Optional[str] = None
    analysis_unknown_reason: Optional[str] = None
    ai_audit_status: Optional[str] = None
    ai_audit_verdict: Optional[str] = None
    ai_audit_summary: Optional[str] = None
    ai_can_understand_question: Optional[bool] = None
    ai_can_solve_question: Optional[bool] = None
    ai_reviewed_before_human: Optional[bool] = None
    ai_review_error: Optional[str] = None
    question_quality: Optional[Dict[str, Any]] = None


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
