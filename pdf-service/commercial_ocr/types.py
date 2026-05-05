from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


OCRBlockType = Literal[
    "text",
    "title",
    "question_no",
    "stem",
    "option",
    "answer",
    "analysis",
    "material_intro",
    "table",
    "figure",
    "chart",
    "header",
    "footer",
    "bbox_only",
    "unknown",
]

ProviderStatus = Literal["ok", "partial", "error", "skipped"]


@dataclass
class NormalizedOCRBlock:
    block_id: str
    provider_ref: str
    page_no: int
    text: str
    bbox: list[float] = field(default_factory=list)
    block_type: OCRBlockType = "unknown"
    confidence: float | None = None
    reading_order: int = 0
    parent_block_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProviderPageResult:
    page_no: int
    blocks: list[NormalizedOCRBlock] = field(default_factory=list)
    figures: list[dict[str, Any]] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["blocks"] = [block.to_dict() for block in self.blocks]
        return payload


@dataclass
class ProviderOCRResult:
    provider_name: str
    provider_version: str
    source_document_id: str
    task_id: str
    page_results: list[ProviderPageResult] = field(default_factory=list)
    raw_response_ref: str | None = None
    provider_latency_ms: int = 0
    provider_status: ProviderStatus = "ok"
    provider_error: dict[str, Any] | None = None
    fallback_used: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["page_results"] = [page.to_dict() for page in self.page_results]
        return payload


@dataclass
class MaterialGroup:
    material_id: str
    group_type: str
    question_range: list[int] = field(default_factory=list)
    shared_stem: str = ""
    shared_assets: list[dict[str, Any]] = field(default_factory=list)
    source_page_span: list[int] = field(default_factory=list)
    source_blocks: list[str] = field(default_factory=list)
    grouping_evidence: list[str] = field(default_factory=list)
    grouping_confidence: float | None = None
    needs_human_review: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NormalizedQuestion:
    question_id: str
    question_no: int | None = None
    material_id: str | None = None
    parent_group_id: str | None = None
    group_type: str | None = None
    question_role: str | None = None
    question_range: list[int] = field(default_factory=list)
    shared_stem_ref: str | None = None
    local_stem: str = ""
    full_stem: str = ""
    options: dict[str, str] = field(default_factory=dict)
    answer: str | None = None
    analysis: str | None = None
    category: str | None = None
    subtype: str | None = None
    source_page_span: list[int] = field(default_factory=list)
    bbox: list[float] = field(default_factory=list)
    question_image_ref: str | None = None
    provider: str | None = None
    provider_trace_ref: str | None = None
    confidence: float | None = None
    needs_human_review: bool = False
    missing_fields: list[str] = field(default_factory=list)
    validation_warnings: list[str] = field(default_factory=list)
    grouping_evidence: list[str] = field(default_factory=list)
    grouping_confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SemanticAssemblyResult:
    material_groups: list[MaterialGroup] = field(default_factory=list)
    question_groups: list[dict[str, Any]] = field(default_factory=list)
    normalized_questions: list[NormalizedQuestion] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "material_groups": [group.to_dict() for group in self.material_groups],
            "question_groups": list(self.question_groups),
            "normalized_questions": [question.to_dict() for question in self.normalized_questions],
            "warnings": list(self.warnings),
        }


@dataclass
class ParseQualityGateResult:
    extraction_complete: bool
    ocr_complete: bool
    visual_assets_preserved: bool
    semantic_consistent: bool
    reasoning_verified: bool
    review_ready: bool
    extracted_but_incomplete: bool
    needs_human_review: bool
    blocking_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    per_question_status: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProviderOCRRequest:
    extractor: Any
    pdf_path: str
    source_document_id: str
    task_id: str
    page_numbers: list[int]
    debug_dir: str | None = None
    trace_enabled: bool = False


@dataclass
class CommercialOCRExecution:
    requested_primary_provider: str
    attempted_providers: list[dict[str, Any]] = field(default_factory=list)
    effective_provider: str | None = None
    provider_result: ProviderOCRResult | None = None
    fallback_used: bool = False
    should_use_local_parser: bool = False
    semantic_assembly: SemanticAssemblyResult | None = None
    quality_gate: ParseQualityGateResult | None = None
    visual_understanding: dict[str, Any] | None = None
    mimo_text_review: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_primary_provider": self.requested_primary_provider,
            "attempted_providers": self.attempted_providers,
            "effective_provider": self.effective_provider,
            "provider_result": self.provider_result.to_dict() if self.provider_result else None,
            "fallback_used": self.fallback_used,
            "should_use_local_parser": self.should_use_local_parser,
            "semantic_assembly": self.semantic_assembly.to_dict() if self.semantic_assembly else None,
            "quality_gate": self.quality_gate.to_dict() if self.quality_gate else None,
            "visual_understanding": self.visual_understanding,
            "mimo_text_review": self.mimo_text_review,
            "warnings": list(self.warnings),
        }
