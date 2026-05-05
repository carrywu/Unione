from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import fitz

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ai_client
from commercial_ocr.adapters import provider_registry
from commercial_ocr.data_analysis import evaluate_data_analysis_quality_gate, questions_for_group
from commercial_ocr.quality_gate import evaluate_parse_quality
from commercial_ocr.semantic_assembler import assemble_semantic_result
from commercial_ocr.types import (
    DataAnalysisQualityGate,
    DataAnalysisUnderstandingResult,
    DataAnalysisVisualContext,
    MaterialGroup,
    ProviderOCRRequest,
)
from extractor import PDFExtractor
from scripts.data_analysis_local_ocr import (
    LOCAL_OCR_PROVIDER,
    build_local_group_from_start_page,
    stitched_page_image_b64,
)
from scripts.data_analysis_real_smoke_lib import (
    call_ark_vision_json,
    call_openai_vision_json,
    call_text_json,
    ensure_dir,
    load_project_env,
    project_relative_path,
    read_json,
    read_prompt,
    resolve_text_model_config,
    text_key_presence,
    timestamp_slug,
    write_json,
)


VISUAL_PROMPT = read_prompt(ROOT / "commercial_ocr" / "prompts" / "data_analysis_visual_context_zh.md")
TEXT_PROMPT = read_prompt(ROOT / "commercial_ocr" / "prompts" / "data_analysis_question_understanding_zh.md")
WORKBENCH_TEMPLATE_FIXTURE = ROOT / "tests" / "fixtures" / "commercial_ocr" / "shared_material_17_20_complete_blocks.json"


def bool_value(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return bool(value)


def list_of_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def truncate_text(value: Any, limit: int = 500) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[:limit] + "..."


def question_value(question: Any, name: str, default: Any = None) -> Any:
    if isinstance(question, dict):
        return question.get(name, default)
    return getattr(question, name, default)


def material_groups_for_page(assembly: Any) -> list[MaterialGroup]:
    return [
        group
        for group in assembly.material_groups
        if group.group_type in {"data_analysis_material", "shared_material"}
        and len(group.question_range) >= 2
    ]


def provider_page_summary(
    *,
    candidate: dict[str, Any],
    provider_name: str,
    provider_status: str,
    provider_latency_ms: int,
    assembly: Any | None,
    result: Any | None,
    warnings: list[str],
) -> dict[str, Any]:
    groups = material_groups_for_page(assembly) if assembly is not None else []
    questions = list(assembly.normalized_questions) if assembly is not None else []
    bbox_count = sum(1 for item in questions if (item.provider_bbox or item.bbox))
    return {
        "provider": provider_name,
        "page_no": int(candidate.get("page_no") or 0),
        "status": provider_status,
        "latency_ms": provider_latency_ms,
        "question_count": len(questions),
        "bbox_count": bbox_count,
        "material_group_candidates": [
            {
                "material_id": group.material_id,
                "group_type": group.group_type,
                "question_range": list(group.question_range),
                "source_page_span": list(group.source_page_span),
                "shared_assets_count": len(group.shared_assets),
                "warnings": list(group.warnings),
            }
            for group in groups
        ],
        "likely_question_range": candidate.get("likely_question_range") or [],
        "has_table_or_chart": any(group.table_blocks or group.chart_blocks for group in groups),
        "has_answer_candidate": any(bool(item.ocr_answer_candidate) for item in questions),
        "has_analysis_candidate": any(bool(item.ocr_analysis_candidate) for item in questions),
        "warnings": warnings,
        "raw_response_ref": getattr(result, "raw_response_ref", None),
    }


def score_provider_page(summary: dict[str, Any]) -> tuple[int, int, int, int]:
    groups = summary.get("material_group_candidates") or []
    best_group_size = max((len(item.get("question_range") or []) for item in groups), default=0)
    group_count = len(groups)
    has_visual = 1 if summary.get("has_table_or_chart") else 0
    bbox_count = int(summary.get("bbox_count") or 0)
    status = str(summary.get("status") or "")
    status_score = 100 if status == "ok" else 10 if status == "partial" else 0
    return (status_score, best_group_size, group_count + has_visual, bbox_count)


def local_provider_page_summary(
    *,
    candidate: dict[str, Any],
    local_group: dict[str, Any],
) -> dict[str, Any]:
    return {
        "provider": LOCAL_OCR_PROVIDER,
        "page_no": int(candidate.get("page_no") or 0),
        "status": "ok_local_fallback",
        "latency_ms": 0,
        "question_count": len(local_group.get("questions") or []),
        "bbox_count": 0,
        "material_group_candidates": [
            {
                "material_id": f"local-ocr-{local_group['question_range'][0]}-{local_group['question_range'][-1]}-p{local_group['page_no']}",
                "group_type": "data_analysis_material",
                "question_range": list(local_group.get("question_range") or []),
                "source_page_span": list(local_group.get("source_page_span") or []),
                "shared_assets_count": 0,
                "warnings": list(local_group.get("warnings") or []),
            }
        ],
        "likely_question_range": candidate.get("likely_question_range") or list(local_group.get("question_range") or []),
        "has_table_or_chart": True,
        "has_answer_candidate": False,
        "has_analysis_candidate": False,
        "warnings": list(local_group.get("warnings") or []),
        "raw_response_ref": None,
    }


def run_provider_on_page(
    *,
    extractor: PDFExtractor,
    provider_name: str,
    page_no: int,
    output_dir: Path,
) -> dict[str, Any]:
    providers = provider_registry()
    provider = providers.get(provider_name)
    if provider is None:
        return {
            "provider_name": provider_name,
            "provider_status": "skipped",
            "warnings": [f"unknown_provider:{provider_name}"],
            "assembly": None,
            "quality_gate": None,
            "provider_result": None,
        }
    available, missing = provider.is_available()
    if not available:
        return {
            "provider_name": provider_name,
            "provider_status": "skipped_unavailable",
            "warnings": list(missing),
            "assembly": None,
            "quality_gate": None,
            "provider_result": None,
        }
    request = ProviderOCRRequest(
        extractor=extractor,
        pdf_path=extractor.pdf_path,
        source_document_id=f"real-data-analysis-{Path(extractor.pdf_path).stem}",
        task_id=f"{provider_name}-p{page_no}",
        page_numbers=[page_no],
        debug_dir=str(output_dir),
        trace_enabled=True,
    )
    result = provider.analyze_document(request)
    assembly = None
    quality_gate = None
    if result.provider_status == "ok" and result.page_results:
        assembly = assemble_semantic_result(
            result.page_results,
            provider_name=result.provider_name,
            provider_trace_ref=result.raw_response_ref,
        )
        quality_gate = evaluate_parse_quality(
            assembly,
            fallback_used=False,
            provider_error=result.provider_error,
        )
    return {
        "provider_name": result.provider_name,
        "provider_status": result.provider_status,
        "warnings": list(result.warnings),
        "assembly": assembly,
        "quality_gate": quality_gate,
        "provider_result": result,
    }


def build_group_crop(
    *,
    extractor: PDFExtractor,
    group: MaterialGroup,
    questions: list[Any],
) -> tuple[str, int, list[float] | None]:
    page_no = int(group.source_page_span[0] if group.source_page_span else (questions[0].source_page_span[0] if questions and questions[0].source_page_span else 1))
    bboxes: list[list[float]] = []
    for asset in group.shared_assets:
        bbox = asset.get("bbox")
        if isinstance(bbox, list) and len(bbox) == 4:
            bboxes.append([float(item) for item in bbox])
    for question in questions:
        bbox = question.provider_bbox or question.bbox
        if isinstance(bbox, list) and len(bbox) == 4:
            bboxes.append([float(item) for item in bbox])
    if not bboxes:
        return extractor.get_page_screenshot(page_no - 1, dpi=140, max_side=1600), page_no, None
    rect = fitz.Rect(
        min(item[0] for item in bboxes),
        min(item[1] for item in bboxes),
        max(item[2] for item in bboxes),
        max(item[3] for item in bboxes),
    )
    return extractor.get_region_screenshot(page_no - 1, rect, padding=28), page_no, [rect.x0, rect.y0, rect.x1, rect.y1]


def build_visual_prompt(group: MaterialGroup, questions: list[Any], page_no: int, ocr_provider: str) -> str:
    context = {
        "ocr_provider": ocr_provider,
        "page_no": page_no,
        "question_range": list(group.question_range),
        "shared_stem": group.shared_stem,
        "shared_assets": [
            {
                "block_type": asset.get("block_type"),
                "page_no": asset.get("page_no"),
                "text": truncate_text(asset.get("text"), 300),
                "bbox": asset.get("bbox"),
            }
            for asset in group.shared_assets[:8]
        ],
        "questions": [
            {
                "question_no": question.question_no,
                "stem": truncate_text(question.full_stem or question.local_stem, 220),
            }
            for question in questions
        ],
    }
    return f"{VISUAL_PROMPT}\n\nOCR 已识别的结构化上下文如下。你只能做视觉完整性核对，不要重做 OCR：\n{json.dumps(context, ensure_ascii=False, indent=2)}"


def build_local_visual_prompt(local_group: dict[str, Any]) -> str:
    context = {
        "ocr_provider": LOCAL_OCR_PROVIDER,
        "page_no": int(local_group.get("page_no") or 0),
        "question_range": list(local_group.get("question_range") or []),
        "shared_stem": local_group.get("shared_stem") or "",
        "material_text": truncate_text(local_group.get("material_text"), 1200),
        "questions": [
            {
                "question_no": question_value(question, "question_no"),
                "stem": truncate_text(question_value(question, "full_stem") or question_value(question, "local_stem"), 220),
            }
            for question in local_group.get("questions") or []
        ],
        "warnings": list(local_group.get("warnings") or []),
    }
    return f"{VISUAL_PROMPT}\n\n这是本地 OCR fallback 提供的真实题本上下文。你只能做视觉完整性核对，不要编造缺失数据：\n{json.dumps(context, ensure_ascii=False, indent=2)}"


def run_visual_context_with_strategy(
    *,
    image_b64: str,
    prompt: str,
    output_dir: Path,
    group_key: str,
) -> tuple[DataAnalysisVisualContext, dict[str, Any]]:
    configs = ai_client.vision_provider_configs()
    attempts: list[dict[str, Any]] = []
    qwen_timeout = 12.0
    hard_timeout = 45.0

    qwen_config = configs.get("qwen_vl") or {}
    if qwen_config.get("configured"):
        started = time.perf_counter()
        try:
            payload, meta = call_openai_vision_json(
                provider_config=qwen_config,
                prompt=prompt,
                image_b64=image_b64,
                timeout_seconds=qwen_timeout,
            )
            attempts.append({"provider": "qwen_vl", "status": "ok", **meta})
            write_json(output_dir / f"{group_key}-visual-qwen.json", payload)
            return coerce_visual_context(payload, provider="qwen_vl", model=meta["model"]), {
                "selected_provider": "qwen_vl",
                "selected_model": meta["model"],
                "attempts": attempts,
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
            }
        except Exception as exc:  # pragma: no cover - runtime integration path
            attempts.append(
                {
                    "provider": "qwen_vl",
                    "status": "failed",
                    "elapsed_ms": int((time.perf_counter() - started) * 1000),
                    "error_type": ai_client._vision_provider_error_type(str(exc), type(exc).__name__),
                    "error_message": str(exc),
                }
            )

    ark_config = configs.get("volcengine_ark_vl") or {}
    if ark_config.get("configured"):
        started = time.perf_counter()
        try:
            payload, meta = call_ark_vision_json(
                provider_config=ark_config,
                prompt=prompt,
                image_b64=image_b64,
                timeout_seconds=hard_timeout,
            )
            attempts.append({"provider": "volcengine_ark_vl", "status": "ok", **meta})
            write_json(output_dir / f"{group_key}-visual-ark.json", payload)
            return coerce_visual_context(payload, provider="volcengine_ark_vl", model=meta["model"]), {
                "selected_provider": "volcengine_ark_vl",
                "selected_model": meta["model"],
                "attempts": attempts,
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                "fallback_used": any(item.get("provider") == "qwen_vl" and item.get("status") != "ok" for item in attempts),
            }
        except Exception as exc:  # pragma: no cover - runtime integration path
            attempts.append(
                {
                    "provider": "volcengine_ark_vl",
                    "status": "failed",
                    "elapsed_ms": int((time.perf_counter() - started) * 1000),
                    "error_type": ai_client._vision_provider_error_type(str(exc), type(exc).__name__),
                    "error_message": str(exc),
                }
            )

    mimo_config = configs.get("mimo_vl") or {}
    if mimo_config.get("configured"):
        attempts.append(
            {
                "provider": "mimo_vl",
                "status": "skipped",
                "error_type": "deprioritized",
                "error_message": "mimo_vl is deprioritized for data-analysis real smoke unless qwen and ark are both unavailable",
            }
        )
    raise RuntimeError(json.dumps({"group_key": group_key, "attempts": attempts}, ensure_ascii=False))


def coerce_visual_context(payload: dict[str, Any], *, provider: str, model: str) -> DataAnalysisVisualContext:
    return DataAnalysisVisualContext(
        model_provider=provider,
        model_name=model,
        source_material_complete=bool_value(payload.get("source_material_complete")),
        chart_title_present=bool_value(payload.get("chart_title_present")),
        table_header_present=bool_value(payload.get("table_header_present")),
        unit_present=bool_value(payload.get("unit_present")),
        legend_present=bool_value(payload.get("legend_present"), default=True),
        table_or_chart_readable=bool_value(payload.get("table_or_chart_readable")),
        material_group_visual_consistent=bool_value(payload.get("material_group_visual_consistent"), default=True),
        suspected_crop_errors=list_of_strings(payload.get("suspected_crop_errors")),
        suspected_ocr_errors=list_of_strings(payload.get("suspected_ocr_errors")),
        critical_data_points_visible=list_of_strings(payload.get("critical_data_points_visible")),
        visual_summary=str(payload.get("visual_summary") or ""),
        warnings=list_of_strings(payload.get("warnings")),
    )


def build_text_prompt(question: Any, group: Any, visual_context: DataAnalysisVisualContext) -> str:
    if isinstance(group, dict):
        shared_material = str(group.get("material_text") or group.get("shared_stem") or "")
        table_blocks = []
        chart_blocks = []
    else:
        shared_material = group.shared_stem
        table_blocks = [truncate_text(block.get("text"), 320) for block in group.table_blocks[:4]]
        chart_blocks = [truncate_text(block.get("text"), 320) for block in group.chart_blocks[:4]]
    payload = {
        "question_no": question_value(question, "question_no"),
        "question_stem": question_value(question, "full_stem") or question_value(question, "local_stem"),
        "options": dict(question_value(question, "options") or {}),
        "ocr_answer_candidate": question_value(question, "ocr_answer_candidate"),
        "ocr_analysis_candidate": question_value(question, "ocr_analysis_candidate"),
        "shared_material": shared_material,
        "table_blocks": table_blocks,
        "chart_blocks": chart_blocks,
        "visual_context": visual_context.to_dict(),
    }
    return f"{TEXT_PROMPT}\n\n以下是 OCR/VLM 已提供的上下文。你必须基于这些上下文判断能否理解并作答：\n{json.dumps(payload, ensure_ascii=False, indent=2)}"


def coerce_understanding_result(
    payload: dict[str, Any],
    *,
    provider: str,
    model: str,
    question_no: int,
) -> DataAnalysisUnderstandingResult:
    confidence = float(payload.get("comprehension_confidence") or 0.0)
    missing_information = list_of_strings(payload.get("missing_information"))
    conflict = bool_value(payload.get("conflict_with_ocr_answer"))
    needs_human_review = bool_value(payload.get("needs_human_review")) or confidence < 0.9 or conflict or bool(missing_information)
    return DataAnalysisUnderstandingResult(
        model_provider=provider,
        model_name=model,
        question_no=question_no,
        can_understand_material=bool_value(payload.get("can_understand_material")),
        can_solve_question=bool_value(payload.get("can_solve_question")),
        answer_suggestion=str(payload.get("answer_suggestion")).strip() if payload.get("answer_suggestion") is not None else None,
        calculation_reasoning=str(payload.get("calculation_reasoning") or ""),
        formula_used=str(payload.get("formula_used") or ""),
        data_points_used=list_of_strings(payload.get("data_points_used")),
        missing_information=missing_information,
        ocr_answer_agreement=str(payload.get("ocr_answer_agreement") or "no_ocr_answer"),
        conflict_with_ocr_answer=conflict,
        comprehension_confidence=confidence,
        needs_human_review=needs_human_review,
        warnings=list_of_strings(payload.get("warnings")),
    )


def build_local_quality_gate(
    *,
    local_group: dict[str, Any],
    visual_context: DataAnalysisVisualContext,
    understanding_results: list[DataAnalysisUnderstandingResult],
) -> DataAnalysisQualityGate:
    question_range = list(local_group.get("question_range") or [])
    expected_questions = question_range[-1] - question_range[0] + 1 if len(question_range) == 2 else len(question_range)
    confidence = round(min((item.comprehension_confidence for item in understanding_results), default=0.0), 4)
    llm_can_understand = bool(understanding_results) and all(item.can_understand_material for item in understanding_results)
    llm_can_solve = bool(understanding_results) and all(item.can_solve_question for item in understanding_results)
    reasoning_present = bool(understanding_results) and all(bool(item.calculation_reasoning.strip()) for item in understanding_results)
    answer_conflict = any(item.conflict_with_ocr_answer for item in understanding_results)
    blocking_reasons: list[str] = []
    warnings = list(dict.fromkeys([*(local_group.get("warnings") or []), "local_ocr_fallback_used", *visual_context.warnings]))

    if not local_group.get("material_text"):
        blocking_reasons.append("shared_material_missing")
    if len(question_range) != 2 or question_range[0] >= question_range[1]:
        blocking_reasons.append("invalid_question_range")
    if len(local_group.get("questions") or []) < expected_questions:
        blocking_reasons.append("local_ocr_questions_incomplete")
    if not visual_context.source_material_complete:
        blocking_reasons.append("source_material_incomplete")
    if not visual_context.table_header_present:
        blocking_reasons.append("table_header_missing")
    if not visual_context.unit_present:
        blocking_reasons.append("unit_missing")
    if not llm_can_understand:
        blocking_reasons.append("llm_cannot_understand_material")
    if not llm_can_solve:
        blocking_reasons.append("llm_cannot_solve_question")
    if not reasoning_present:
        blocking_reasons.append("calculation_reasoning_missing")
    if answer_conflict:
        blocking_reasons.append("ocr_answer_conflict")

    return DataAnalysisQualityGate(
        has_shared_material=bool(local_group.get("material_text")),
        has_valid_question_range=len(question_range) == 2 and question_range[0] < question_range[1],
        children_share_same_material_id=True,
        shared_assets_preserved=visual_context.table_or_chart_readable,
        table_header_complete=visual_context.table_header_present,
        unit_complete=visual_context.unit_present,
        chart_title_complete=visual_context.chart_title_present,
        local_stem_not_polluted=True,
        llm_can_understand_material=llm_can_understand,
        llm_can_solve_question=llm_can_solve,
        calculation_reasoning_present=reasoning_present,
        answer_conflict=answer_conflict,
        comprehension_confidence=confidence,
        review_ready=False,
        needs_human_review=True,
        blocking_reasons=list(dict.fromkeys(blocking_reasons)),
        warnings=warnings,
    )


def export_workbench_fixture(
    *,
    target: Path,
    provider_run: dict[str, Any],
    visual_context: DataAnalysisVisualContext,
    understanding_results: list[DataAnalysisUnderstandingResult],
    quality_gate: DataAnalysisQualityGate,
    bbox_source: str,
    import_metadata: dict[str, Any],
) -> None:
    result = provider_run["provider_result"]
    payload = {
        "provider_name": "mock_commercial_ocr",
        "provider_version": "real-smoke-import-v1",
        "provider_status": "ok",
        "provider_latency_ms": getattr(result, "provider_latency_ms", 0),
        "warnings": list(getattr(result, "warnings", []) or []),
        "page_results": [page.to_dict() for page in result.page_results],
        "precomputed_data_analysis": {
            "import_metadata": {
                **import_metadata,
                "bbox_source": bbox_source,
                "per_question": {
                    str(item.question_no): {"bbox_source": bbox_source}
                    for item in understanding_results
                },
            },
            "data_analysis_visual_context": visual_context.to_dict(),
            "data_analysis_understanding_results": [item.to_dict() for item in understanding_results],
            "data_analysis_quality_gate": quality_gate.to_dict(),
        },
    }
    write_json(target, payload)


def export_template_backed_workbench_fixture(
    *,
    target: Path,
    visual_context: DataAnalysisVisualContext,
    understanding_results: list[DataAnalysisUnderstandingResult],
    quality_gate: DataAnalysisQualityGate,
    bbox_source: str,
    import_metadata: dict[str, Any],
) -> None:
    payload = read_json(WORKBENCH_TEMPLATE_FIXTURE)
    if not isinstance(payload, dict):
        raise RuntimeError("invalid_workbench_template_fixture")
    payload["provider_name"] = "mock_commercial_ocr"
    payload["provider_version"] = "real-smoke-template-import-v1"
    payload["provider_status"] = "ok"
    payload["precomputed_data_analysis"] = {
        "import_metadata": {
            **import_metadata,
            "bbox_source": bbox_source,
            "per_question": {
                str(item.question_no): {"bbox_source": bbox_source}
                for item in understanding_results
            },
        },
        "data_analysis_visual_context": visual_context.to_dict(),
        "data_analysis_understanding_results": [item.to_dict() for item in understanding_results],
        "data_analysis_quality_gate": quality_gate.to_dict(),
    }
    write_json(target, payload)


def choose_fixture_group(group_entries: list[dict[str, Any]], max_questions_per_group: int) -> dict[str, Any] | None:
    eligible = [
        entry
        for entry in group_entries
        if len(entry.get("question_range") or []) >= 2
    ]
    for entry in eligible:
        question_numbers = {
            int(question_value(question, "question_no") or 0)
            for question in entry.get("questions") or []
        }
        if {17, 18, 19, 20}.issubset(question_numbers):
            return entry
    return eligible[0] if eligible else None


def select_fixture_questions(entry: dict[str, Any], max_questions_per_group: int) -> list[Any]:
    questions = list(entry.get("questions") or [])
    question_numbers = [int(question_value(item, "question_no") or 0) for item in questions]
    if {17, 18, 19, 20}.issubset(set(question_numbers)):
        chosen = [item for item in questions if int(question_value(item, "question_no") or 0) in {17, 18, 19, 20}]
        if len(chosen) == 4:
            return chosen
    return questions[:max_questions_per_group]


def load_candidate_pages(path: str | Path) -> list[dict[str, Any]]:
    payload = read_json(path)
    if isinstance(payload, dict):
        candidates = payload.get("candidates") or []
        return [item for item in candidates if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def run_batch_smoke(
    *,
    pdf_path: str,
    candidate_pages_path: str,
    providers: list[str],
    max_pages: int,
    max_questions_per_group: int,
    output_dir: Path,
) -> dict[str, Any]:
    candidates = load_candidate_pages(candidate_pages_path)[:max_pages]
    if any(provider.startswith("tencent_") for provider in providers):
        os.environ.setdefault("TENCENT_OCR_REAL_SMOKE", "true")
    extractor = PDFExtractor(pdf_path)
    raw_dir = ensure_dir(output_dir / "raw")
    fixture_dir = ensure_dir(output_dir / "workbench-import-fixtures")
    group_entries: list[dict[str, Any]] = []
    page_provider_summaries: list[dict[str, Any]] = []
    try:
        for candidate in candidates:
            page_runs: list[dict[str, Any]] = []
            for provider_name in providers:
                provider_run = run_provider_on_page(
                    extractor=extractor,
                    provider_name=provider_name,
                    page_no=int(candidate.get("page_no") or 0),
                    output_dir=output_dir,
                )
                summary = provider_page_summary(
                    candidate=candidate,
                    provider_name=provider_run["provider_name"],
                    provider_status=provider_run["provider_status"],
                    provider_latency_ms=int(getattr(provider_run["provider_result"], "provider_latency_ms", 0) or 0),
                    assembly=provider_run["assembly"],
                    result=provider_run["provider_result"],
                    warnings=list(provider_run["warnings"]),
                )
                provider_run["summary"] = summary
                page_runs.append(provider_run)
                page_provider_summaries.append(summary)
            successful_runs = [run for run in page_runs if run["assembly"] is not None and run["provider_result"] is not None]
            if not successful_runs:
                local_group = build_local_group_from_start_page(
                    extractor=extractor,
                    start_page_no=int(candidate.get("page_no") or 0),
                )
                if local_group is None:
                    continue
                local_summary = local_provider_page_summary(candidate=candidate, local_group=local_group)
                page_provider_summaries.append(local_summary)
                group_key = f"page{int(candidate.get('page_no') or 0):03d}-local-group1"
                image_b64 = stitched_page_image_b64(
                    extractor=extractor,
                    page_numbers=list(local_group.get("source_pages") or [int(candidate.get("page_no") or 0)]),
                )
                try:
                    visual_context, visual_meta = run_visual_context_with_strategy(
                        image_b64=image_b64,
                        prompt=build_local_visual_prompt(local_group),
                        output_dir=raw_dir,
                        group_key=group_key,
                    )
                except Exception as exc:  # pragma: no cover - runtime integration path
                    visual_context = DataAnalysisVisualContext(
                        model_provider="unavailable",
                        model_name="unavailable",
                        source_material_complete=False,
                        chart_title_present=False,
                        table_header_present=False,
                        unit_present=False,
                        legend_present=False,
                        table_or_chart_readable=False,
                        material_group_visual_consistent=False,
                        suspected_crop_errors=["visual_provider_failed"],
                        suspected_ocr_errors=[],
                        critical_data_points_visible=[],
                        visual_summary="visual provider failed",
                        warnings=[str(exc)],
                    )
                    visual_meta = {
                        "selected_provider": "unavailable",
                        "selected_model": "unavailable",
                        "attempts": [],
                        "error_message": str(exc),
                    }
                group_entries.append(
                    {
                        "group_key": group_key,
                        "page_no": int(candidate.get("page_no") or 0),
                        "ocr_provider": LOCAL_OCR_PROVIDER,
                        "question_range": list(local_group.get("question_range") or []),
                        "source_page_span": list(local_group.get("source_page_span") or []),
                        "shared_stem_preview": truncate_text(local_group.get("material_text") or local_group.get("shared_stem"), 180),
                        "visual_context": visual_context.to_dict(),
                        "visual_meta": visual_meta,
                        "crop_page_no": int(candidate.get("page_no") or 0),
                        "crop_bbox": None,
                        "provider_run": None,
                        "group": local_group,
                        "questions": list(local_group.get("questions") or []),
                    }
                )
                continue
            best_run = sorted(successful_runs, key=lambda item: score_provider_page(item["summary"]), reverse=True)[0]
            groups = material_groups_for_page(best_run["assembly"])
            for index, group in enumerate(groups, start=1):
                questions = questions_for_group(best_run["assembly"], group)
                image_b64, crop_page_no, crop_bbox = build_group_crop(
                    extractor=extractor,
                    group=group,
                    questions=questions,
                )
                group_key = f"page{int(candidate.get('page_no') or 0):03d}-group{index}"
                visual_prompt = build_visual_prompt(
                    group=group,
                    questions=questions[:max_questions_per_group],
                    page_no=crop_page_no,
                    ocr_provider=best_run["provider_name"],
                )
                try:
                    visual_context, visual_meta = run_visual_context_with_strategy(
                        image_b64=image_b64,
                        prompt=visual_prompt,
                        output_dir=raw_dir,
                        group_key=group_key,
                    )
                except Exception as exc:  # pragma: no cover - runtime integration path
                    visual_context = DataAnalysisVisualContext(
                        model_provider="unavailable",
                        model_name="unavailable",
                        source_material_complete=False,
                        chart_title_present=False,
                        table_header_present=False,
                        unit_present=False,
                        legend_present=False,
                        table_or_chart_readable=False,
                        material_group_visual_consistent=False,
                        suspected_crop_errors=["visual_provider_failed"],
                        suspected_ocr_errors=[],
                        critical_data_points_visible=[],
                        visual_summary="visual provider failed",
                        warnings=[str(exc)],
                    )
                    visual_meta = {
                        "selected_provider": "unavailable",
                        "selected_model": "unavailable",
                        "attempts": [],
                        "error_message": str(exc),
                    }
                group_entries.append(
                    {
                        "group_key": group_key,
                        "page_no": int(candidate.get("page_no") or 0),
                        "ocr_provider": best_run["provider_name"],
                        "question_range": list(group.question_range),
                        "source_page_span": list(group.source_page_span),
                        "shared_stem_preview": truncate_text(group.shared_stem, 180),
                        "visual_context": visual_context.to_dict(),
                        "visual_meta": visual_meta,
                        "crop_page_no": crop_page_no,
                        "crop_bbox": crop_bbox,
                        "provider_run": best_run,
                        "group": group,
                        "questions": questions,
                    }
                )

        fixture_group = choose_fixture_group(group_entries, max_questions_per_group)
        fixture_manifest: list[dict[str, Any]] = []
        if fixture_group is not None:
            text_config = resolve_text_model_config()
            text_results: list[DataAnalysisUnderstandingResult] = []
            selected_questions = select_fixture_questions(fixture_group, max_questions_per_group)
            for question in selected_questions:
                prompt = build_text_prompt(
                    question=question,
                    group=fixture_group["group"],
                    visual_context=coerce_visual_context(
                        fixture_group["visual_context"],
                        provider=str(fixture_group["visual_meta"].get("selected_provider") or "unknown"),
                        model=str(fixture_group["visual_meta"].get("selected_model") or "unknown"),
                    ),
                )
                try:
                    payload, meta = call_text_json(
                        prompt=prompt,
                        timeout_seconds=90.0,
                        model_config=text_config,
                    )
                    write_json(
                        raw_dir / f"{fixture_group['group_key']}-q{int(question_value(question, 'question_no') or 0)}-text.json",
                        payload,
                    )
                    text_results.append(
                        coerce_understanding_result(
                            payload,
                            provider=str(meta["provider"]),
                            model=str(meta["model"]),
                            question_no=int(question_value(question, "question_no") or 0),
                        )
                    )
                except Exception as exc:  # pragma: no cover - runtime integration path
                    text_results.append(
                        DataAnalysisUnderstandingResult(
                            model_provider=str(text_config.get("provider") or "unavailable"),
                            model_name=str(text_config.get("model") or "unavailable"),
                            question_no=int(question_value(question, "question_no") or 0),
                            can_understand_material=False,
                            can_solve_question=False,
                            answer_suggestion=None,
                            calculation_reasoning="text provider failed",
                            formula_used="",
                            data_points_used=[],
                            missing_information=["text_provider_failed"],
                            ocr_answer_agreement="uncertain",
                            conflict_with_ocr_answer=False,
                            comprehension_confidence=0.0,
                            needs_human_review=True,
                            warnings=[str(exc)],
                        )
                    )

            visual_context = coerce_visual_context(
                fixture_group["visual_context"],
                provider=str(fixture_group["visual_meta"].get("selected_provider") or "unknown"),
                model=str(fixture_group["visual_meta"].get("selected_model") or "unknown"),
            )
            if fixture_group["provider_run"] is not None:
                quality_gate = evaluate_data_analysis_quality_gate(
                    fixture_group["provider_run"]["assembly"],
                    fixture_group["provider_run"]["quality_gate"],
                    visual_context,
                    text_results,
                    fallback_used=False,
                )
                if quality_gate is None:
                    raise RuntimeError("failed_to_build_data_analysis_quality_gate")
            else:
                quality_gate = build_local_quality_gate(
                    local_group=fixture_group["group"],
                    visual_context=visual_context,
                    understanding_results=text_results,
                )
            fixture_name = f"{fixture_group['group_key']}-import.json"
            import_metadata = {
                "source": "real_data_analysis_batch_smoke",
                "pdf_ref": project_relative_path(pdf_path),
                "page_no": fixture_group["page_no"],
                "question_range": [int(question_value(item, "question_no") or 0) for item in selected_questions],
                "visual_provider": visual_context.model_provider,
                "visual_model": visual_context.model_name,
                "text_provider": text_results[0].model_provider if text_results else "",
                "text_model": text_results[0].model_name if text_results else "",
            }
            if fixture_group["provider_run"] is not None:
                export_workbench_fixture(
                    target=fixture_dir / fixture_name,
                    provider_run=fixture_group["provider_run"],
                    visual_context=visual_context,
                    understanding_results=text_results,
                    quality_gate=quality_gate,
                    bbox_source=str(fixture_group["ocr_provider"]),
                    import_metadata=import_metadata,
                )
            else:
                export_template_backed_workbench_fixture(
                    target=fixture_dir / fixture_name,
                    visual_context=visual_context,
                    understanding_results=text_results,
                    quality_gate=quality_gate,
                    bbox_source=str(fixture_group["ocr_provider"]),
                    import_metadata=import_metadata,
                )
            fixture_manifest.append(
                {
                    "fixture_name": fixture_name,
                    "fixture_path": project_relative_path(fixture_dir / fixture_name),
                    "bbox_source": fixture_group["ocr_provider"],
                    "question_range": [int(question_value(item, "question_no") or 0) for item in selected_questions],
                    "visual_provider": visual_context.model_provider,
                    "text_model": text_results[0].model_name if text_results else "",
                    "needs_human_review": quality_gate.needs_human_review,
                }
            )
            fixture_group["text_results"] = [item.to_dict() for item in text_results]
            fixture_group["data_analysis_quality_gate"] = quality_gate.to_dict()
        return {
            "generated_at": timestamp_slug(),
            "pdf_ref": project_relative_path(pdf_path),
            "candidate_pages_ref": project_relative_path(candidate_pages_path),
            "providers": providers,
            "provider_strategy": {
                "preferred": "qwen_vl",
                "soft_timeout_seconds": 12.0,
                "hedge_fallback": "volcengine_ark_vl",
                "skip_deprioritize": "mimo_vl when quota is exhausted or ark is available",
            },
            "text_model_key_presence": text_key_presence(),
            "page_provider_runs": page_provider_summaries,
            "group_summaries": [
                {
                    "group_key": item["group_key"],
                    "page_no": item["page_no"],
                    "ocr_provider": item["ocr_provider"],
                    "question_range": item["question_range"],
                    "source_page_span": item["source_page_span"],
                    "shared_stem_preview": item["shared_stem_preview"],
                    "crop_page_no": item["crop_page_no"],
                    "crop_bbox": item["crop_bbox"],
                    "visual_context": item["visual_context"],
                    "visual_meta": item["visual_meta"],
                    "text_results": item.get("text_results") or [],
                    "data_analysis_quality_gate": item.get("data_analysis_quality_gate"),
                }
                for item in group_entries
            ],
            "workbench_import_fixtures": fixture_manifest,
        }
    finally:
        extractor.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run limited real multi-page data-analysis smoke.")
    parser.add_argument("pdf_path", help="Path to the source PDF")
    parser.add_argument("candidate_pages_json", help="Path to candidate-pages.json")
    parser.add_argument(
        "--providers",
        default="baidu_paper_cut_edu,tencent_question_split,tencent_question_split_layout",
        help="Comma-separated OCR providers",
    )
    parser.add_argument("--max-pages", type=int, default=3, help="Maximum number of candidate pages to execute")
    parser.add_argument("--max-questions-per-group", type=int, default=4, help="Maximum questions for real text validation and import fixture export")
    parser.add_argument(
        "--output-dir",
        default=str(ROOT.parent / "debug" / "real-data-data-analysis" / timestamp_slug()),
        help="Directory used for batch-ocr-summary.json and debug payloads",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    load_project_env()
    args = build_parser().parse_args(argv)
    output_dir = ensure_dir(Path(args.output_dir).expanduser().resolve())
    summary = run_batch_smoke(
        pdf_path=str(Path(args.pdf_path).expanduser().resolve()),
        candidate_pages_path=str(Path(args.candidate_pages_json).expanduser().resolve()),
        providers=[item.strip() for item in str(args.providers).split(",") if item.strip()],
        max_pages=max(1, int(args.max_pages)),
        max_questions_per_group=max(1, int(args.max_questions_per_group)),
        output_dir=output_dir,
    )
    target = output_dir / "batch-ocr-summary.json"
    write_json(target, summary)
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
