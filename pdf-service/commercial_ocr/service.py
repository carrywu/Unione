from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import fitz

from commercial_ocr.config import get_flag, get_config_value
from commercial_ocr.adapters import provider_registry
from commercial_ocr.data_analysis import (
    apply_data_analysis_gate_to_parse_quality,
    build_data_analysis_understanding_results,
    build_data_analysis_visual_context,
    evaluate_data_analysis_quality_gate,
)
from commercial_ocr.quality_gate import evaluate_parse_quality
from commercial_ocr.semantic_assembler import assemble_semantic_result
from commercial_ocr.types import (
    CommercialOCRExecution,
    DataAnalysisQualityGate,
    DataAnalysisUnderstandingResult,
    DataAnalysisVisualContext,
    MaterialGroup,
    ProviderOCRRequest,
    ProviderOCRResult,
)
from commercial_ocr.visual_understanding import build_visual_understanding_summary
from commercial_ocr.mimo_reviewer import review_text_payload, mimo_review_status
from models import PageContent, Region, TextBlock


logger = logging.getLogger(__name__)

LOCAL_PARSER_PROVIDER = "local_parser"
DEFAULT_PRIMARY_PROVIDER = "mock_commercial_ocr"


def commercial_ocr_enabled() -> bool:
    return get_flag("commercial_ocr_enabled", "COMMERCIAL_OCR_ENABLED", default=False)


def primary_provider_name() -> str:
    return (
        get_config_value(
            "pdf_parse_primary_provider",
            "PDF_PARSE_PRIMARY_PROVIDER",
            DEFAULT_PRIMARY_PROVIDER,
        )
        or DEFAULT_PRIMARY_PROVIDER
    )


def fallback_provider_names() -> list[str]:
    raw = get_config_value(
        "pdf_parse_fallback_providers",
        "PDF_PARSE_FALLBACK_PROVIDERS",
        "local_parser,mock_commercial_ocr",
    )
    return [item.strip() for item in raw.split(",") if item.strip()]


def provider_trace_enabled() -> bool:
    return get_flag("ocr_provider_trace_enabled", "OCR_PROVIDER_TRACE_ENABLED", default=False)


def build_provider_request(
    extractor: Any,
    *,
    total_pages: int,
    debug_dir: str | None,
) -> ProviderOCRRequest:
    pdf_path = str(getattr(extractor, "pdf_path", "") or "")
    source_document_id = source_document_id_for_path(pdf_path)
    task_id = task_id_from_debug_dir(debug_dir) or source_document_id
    return ProviderOCRRequest(
        extractor=extractor,
        pdf_path=pdf_path,
        source_document_id=source_document_id,
        task_id=task_id,
        page_numbers=list(range(1, total_pages + 1)),
        debug_dir=debug_dir,
        trace_enabled=provider_trace_enabled(),
    )


def run_commercial_ocr_pipeline(
    extractor: Any,
    *,
    total_pages: int,
    debug_dir: str | None = None,
) -> CommercialOCRExecution:
    primary = primary_provider_name()
    execution = CommercialOCRExecution(requested_primary_provider=primary)
    if not commercial_ocr_enabled() and primary != LOCAL_PARSER_PROVIDER:
        execution.warnings.append("commercial_ocr_disabled")
        execution.should_use_local_parser = True
        execution.effective_provider = LOCAL_PARSER_PROVIDER
        execution.attempted_providers.append({"provider": primary, "status": "skipped_disabled"})
        return execution

    request = build_provider_request(extractor, total_pages=total_pages, debug_dir=debug_dir)
    order = _dedupe_order([primary, *fallback_provider_names()])
    providers = provider_registry()

    for provider_name in order:
        if provider_name == LOCAL_PARSER_PROVIDER:
            execution.should_use_local_parser = True
            execution.attempted_providers.append({"provider": provider_name, "status": "selected_local_parser"})
            if execution.effective_provider is None:
                execution.effective_provider = provider_name
            return execution

        provider = providers.get(provider_name)
        if provider is None:
            execution.attempted_providers.append({"provider": provider_name, "status": "skipped_unknown_provider"})
            execution.warnings.append(f"unknown_provider:{provider_name}")
            continue

        available, missing = provider.is_available()
        if not available:
            execution.attempted_providers.append({"provider": provider_name, "status": "skipped_unavailable", "reasons": missing})
            execution.warnings.extend(missing)
            continue

        result = provider.analyze_document(request)
        assembly = None
        quality_gate = None
        data_analysis_visual_context = None
        data_analysis_understanding_results = []
        data_analysis_quality_gate = None
        precomputed_import = _load_precomputed_data_analysis(result.raw_response_ref)
        if result.provider_status == "ok" and result.page_results:
            assembly = assemble_semantic_result(
                result.page_results,
                provider_name=result.provider_name,
                provider_trace_ref=result.raw_response_ref,
            )
            quality_gate = evaluate_parse_quality(
                assembly,
                fallback_used=provider_name != primary,
                provider_error=result.provider_error,
            )
            data_analysis_visual_context = build_data_analysis_visual_context(assembly)
            data_analysis_understanding_results = build_data_analysis_understanding_results(
                assembly,
                data_analysis_visual_context,
            )
            data_analysis_quality_gate = evaluate_data_analysis_quality_gate(
                assembly,
                quality_gate,
                data_analysis_visual_context,
                data_analysis_understanding_results,
                fallback_used=provider_name != primary,
            )
            quality_gate = apply_data_analysis_gate_to_parse_quality(
                quality_gate,
                data_analysis_quality_gate,
            )
            if precomputed_import is not None:
                data_analysis_visual_context = _coerce_data_analysis_visual_context(
                    precomputed_import.get("data_analysis_visual_context"),
                    fallback=data_analysis_visual_context,
                )
                data_analysis_understanding_results = _coerce_data_analysis_understanding_results(
                    precomputed_import.get("data_analysis_understanding_results"),
                    fallback=data_analysis_understanding_results,
                )
                data_analysis_quality_gate = _coerce_data_analysis_quality_gate(
                    precomputed_import.get("data_analysis_quality_gate"),
                    fallback=data_analysis_quality_gate,
                )
                quality_gate = apply_data_analysis_gate_to_parse_quality(
                    quality_gate,
                    data_analysis_quality_gate,
                )
        visual_understanding = None
        if assembly is not None and quality_gate is not None:
            visual_understanding = build_visual_understanding_summary(
                assembly,
                quality_gate=quality_gate,
                provider_name=result.provider_name,
                provider_trace_ref=result.raw_response_ref,
                fallback_used=provider_name != primary,
            )

        # MiMo text review (optional, degrades to mock/skipped)
        mimo_text_review = None
        if assembly is not None and quality_gate is not None:
            try:
                mimo_text_review = review_text_payload(
                    payload={
                        "material_groups": [g.to_dict() for g in assembly.material_groups],
                        "normalized_questions": [q.to_dict() for q in assembly.normalized_questions],
                        "quality_gate": quality_gate.to_dict(),
                        "provider_name": result.provider_name,
                        "fallback_used": provider_name != primary,
                    },
                    context=f"provider={result.provider_name}, primary={primary}",
                )
            except Exception as e:
                logger.warning("MiMo text review failed: %s", e)

        attempt_payload = {
            "provider": provider_name,
            "status": result.provider_status,
            "raw_response_ref": result.raw_response_ref,
            "provider_error": result.provider_error,
            "warnings": result.warnings,
            "quality_gate": quality_gate.to_dict() if quality_gate else None,
            "visual_understanding": visual_understanding,
            "data_analysis_visual_context": data_analysis_visual_context.to_dict() if data_analysis_visual_context else None,
            "data_analysis_understanding_results": [item.to_dict() for item in data_analysis_understanding_results],
            "data_analysis_quality_gate": data_analysis_quality_gate.to_dict() if data_analysis_quality_gate else None,
            "import_metadata": precomputed_import.get("import_metadata") if isinstance(precomputed_import, dict) else None,
            "mimo_text_review": mimo_text_review,
        }
        execution.attempted_providers.append(attempt_payload)

        if result.provider_status == "ok" and result.page_results and _provider_has_structured_text(result):
            execution.provider_result = result
            execution.semantic_assembly = assembly
            execution.quality_gate = quality_gate
            execution.visual_understanding = visual_understanding
            execution.data_analysis_visual_context = data_analysis_visual_context
            execution.data_analysis_understanding_results = data_analysis_understanding_results
            execution.data_analysis_quality_gate = data_analysis_quality_gate
            execution.import_metadata = (
                precomputed_import.get("import_metadata")
                if isinstance(precomputed_import, dict)
                else None
            )
            execution.mimo_text_review = mimo_text_review
            execution.effective_provider = provider_name
            execution.fallback_used = provider_name != primary
            result.fallback_used = execution.fallback_used
            execution.warnings.extend(result.warnings)
            return execution

        if result.provider_status == "ok" and result.page_results:
            execution.warnings.append(f"provider_output_requires_fallback:{provider_name}")
        execution.warnings.extend(result.warnings)

    execution.should_use_local_parser = True
    if execution.effective_provider is None:
        execution.effective_provider = LOCAL_PARSER_PROVIDER
    return execution


def provider_result_to_page_contents(
    extractor: Any,
    result: ProviderOCRResult,
) -> list[PageContent]:
    page_contents: list[PageContent] = []
    for page_result in result.page_results:
        ordered_blocks = sorted(
            page_result.blocks,
            key=lambda block: (block.reading_order, block.bbox[1] if len(block.bbox) >= 2 else 0.0),
        )
        text_blocks = [
            TextBlock(
                bbox=block.bbox or [0.0, float(index * 14), 1000.0, float(index * 14 + 10)],
                text=_to_page_text(block.text, block.block_type),
            )
            for index, block in enumerate(ordered_blocks, start=1)
            if block.text.strip() and block.block_type != "bbox_only"
        ]
        regions = [
            region
            for block in ordered_blocks
            if block.block_type in {"table", "figure", "chart"}
            for region in [_region_for_block(extractor, page_result.page_no - 1, block)]
            if region is not None
        ]
        page_text = "\n".join(block.text for block in text_blocks if block.text.strip())
        page_contents.append(
            PageContent(
                page_num=page_result.page_no,
                text=page_text,
                blocks=text_blocks,
                regions=regions,
            )
        )
    return page_contents


def execution_summary(execution: CommercialOCRExecution | None) -> dict[str, Any] | None:
    if execution is None:
        return None
    provider_result = execution.provider_result
    return {
        "requested_primary_provider": execution.requested_primary_provider,
        "effective_provider": execution.effective_provider,
        "fallback_used": execution.fallback_used,
        "should_use_local_parser": execution.should_use_local_parser,
        "attempted_providers": execution.attempted_providers,
        "warnings": execution.warnings,
        "provider_result": provider_result.to_dict() if provider_result else None,
        "semantic_assembly": execution.semantic_assembly.to_dict() if execution.semantic_assembly else None,
        "quality_gate": execution.quality_gate.to_dict() if execution.quality_gate else None,
        "visual_understanding": execution.visual_understanding,
        "data_analysis_visual_context": execution.data_analysis_visual_context.to_dict() if execution.data_analysis_visual_context else None,
        "data_analysis_understanding_results": [item.to_dict() for item in execution.data_analysis_understanding_results],
        "data_analysis_quality_gate": execution.data_analysis_quality_gate.to_dict() if execution.data_analysis_quality_gate else None,
        "import_metadata": execution.import_metadata,
        "mimo_text_review": execution.mimo_text_review,
        "mimo_reviewer_status": mimo_review_status(),
    }


def build_question_enrichment_payloads(
    execution: CommercialOCRExecution | None,
) -> dict[int, dict[str, Any]]:
    if (
        execution is None
        or execution.semantic_assembly is None
        or execution.provider_result is None
    ):
        return {}

    material_by_id = {
        group.material_id: group for group in execution.semantic_assembly.material_groups
    }
    understanding_by_no = {
        item.question_no: item for item in execution.data_analysis_understanding_results
    }
    payloads: dict[int, dict[str, Any]] = {}
    for question in execution.semantic_assembly.normalized_questions:
        if question.question_no is None:
            continue
        material_group = material_by_id.get(question.material_id or "")
        understanding = understanding_by_no.get(question.question_no)
        bbox_source = _bbox_source_for_question(
            execution=execution,
            question=question,
        )
        parse_warnings = list(
            dict.fromkeys(
                [
                    *question.validation_warnings,
                    *(material_group.warnings if material_group else []),
                    *(execution.quality_gate.blocking_reasons if execution.quality_gate else []),
                    *(execution.data_analysis_quality_gate.warnings if execution.data_analysis_quality_gate else []),
                ]
            )
        )
        visual_confidence = None
        if understanding is not None:
            visual_confidence = understanding.comprehension_confidence
        elif execution.data_analysis_quality_gate is not None:
            visual_confidence = execution.data_analysis_quality_gate.comprehension_confidence
        elif execution.visual_understanding is not None:
            visual_confidence = execution.visual_understanding.get("confidence")

        ai_status = "warning"
        ai_verdict = "需复核"
        ai_summary = "资料分析链路未完成"
        if execution.data_analysis_quality_gate is not None:
            if execution.data_analysis_quality_gate.review_ready:
                ai_status = "passed"
                ai_verdict = "审核通过"
                ai_summary = "资料分析 OCR/VLM/LLM 闭环通过。"
            elif execution.data_analysis_quality_gate.needs_human_review:
                ai_status = "warning"
                ai_verdict = "需复核"
                ai_summary = "；".join(execution.data_analysis_quality_gate.blocking_reasons or execution.data_analysis_quality_gate.warnings[:3]) or "资料分析需人工复核。"
            else:
                ai_status = "failed"
                ai_verdict = "待审核"
                ai_summary = "资料分析链路尚未达到审核通过标准。"

        payloads[int(question.question_no)] = {
            "parse_confidence": visual_confidence or question.provider_confidence or question.confidence,
            "parse_warnings": parse_warnings,
            "source_bbox": question.provider_bbox or question.bbox,
            "source_page_start": question.source_page_span[0] if question.source_page_span else None,
            "source_page_end": question.source_page_span[-1] if question.source_page_span else None,
            "source_confidence": question.provider_confidence or question.confidence,
            "bbox_source": bbox_source,
            "material_group_id": material_group.material_id if material_group else question.material_id,
            "material_group_question_indexes": list(material_group.question_range) if material_group else list(question.question_range),
            "material_group_confidence": material_group.grouping_confidence if material_group else question.grouping_confidence,
            "material_group_reason": " | ".join(material_group.grouping_evidence) if material_group else " | ".join(question.grouping_evidence),
            "shared_material": bool(material_group),
            "visual_summary": _visual_summary_for_question(execution, material_group),
            "visual_confidence": visual_confidence,
            "visual_parse_status": "success" if execution.data_analysis_visual_context and execution.data_analysis_visual_context.table_or_chart_readable else "warning",
            "visual_error": None if execution.data_analysis_visual_context and execution.data_analysis_visual_context.table_or_chart_readable else "visual_context_incomplete",
            "visual_risk_flags": _visual_risk_flags(execution, material_group),
            "has_visual_context": bool(material_group and material_group.shared_assets),
            "answer_unknown_reason": None if understanding and understanding.answer_suggestion else "llm_answer_unavailable",
            "analysis_unknown_reason": None if understanding and understanding.calculation_reasoning else "llm_reasoning_unavailable",
            "ai_candidate_answer": understanding.answer_suggestion if understanding else question.ocr_answer_candidate,
            "ai_candidate_analysis": understanding.calculation_reasoning if understanding else question.ocr_analysis_candidate,
            "ai_answer_confidence": understanding.comprehension_confidence if understanding else visual_confidence,
            "ai_reasoning_summary": understanding.calculation_reasoning if understanding else (question.ocr_analysis_candidate or ""),
            "ai_knowledge_points": list(understanding.data_points_used) if understanding else [],
            "ai_risk_flags": _ai_risk_flags(execution, understanding),
            "ai_solver_provider": understanding.model_provider if understanding else None,
            "ai_solver_model": understanding.model_name if understanding else None,
            "ai_answer_conflict": bool(understanding.conflict_with_ocr_answer) if understanding else False,
            "ai_audit_status": ai_status,
            "ai_audit_verdict": ai_verdict,
            "ai_audit_summary": ai_summary,
            "ai_can_understand_question": bool(understanding.can_understand_material) if understanding else False,
            "ai_can_solve_question": bool(understanding.can_solve_question) if understanding else False,
            "ai_reviewed_before_human": True,
            "needs_review": bool(
                question.needs_human_review
                or (execution.data_analysis_quality_gate and execution.data_analysis_quality_gate.needs_human_review)
                or (understanding and understanding.needs_human_review)
            ),
            "question_quality": {
                "needs_review": bool(
                    question.needs_human_review
                    or (execution.data_analysis_quality_gate and execution.data_analysis_quality_gate.needs_human_review)
                ),
                "commercial_ocr": {
                    "effective_provider": execution.effective_provider,
                    "fallback_used": execution.fallback_used,
                    "bbox_source": bbox_source,
                    "provider_result": {
                        "provider_name": execution.provider_result.provider_name,
                        "provider_version": execution.provider_result.provider_version,
                        "provider_status": execution.provider_result.provider_status,
                        "provider_latency_ms": execution.provider_result.provider_latency_ms,
                        "provider_trace_ref": execution.provider_result.raw_response_ref,
                    },
                    "quality_gate": execution.quality_gate.to_dict() if execution.quality_gate else None,
                    "visual_understanding": execution.visual_understanding,
                    "data_analysis_visual_context": execution.data_analysis_visual_context.to_dict() if execution.data_analysis_visual_context else None,
                    "data_analysis_understanding_result": understanding.to_dict() if understanding else None,
                    "data_analysis_quality_gate": execution.data_analysis_quality_gate.to_dict() if execution.data_analysis_quality_gate else None,
                    "material_group": material_group.to_dict() if material_group else None,
                    "import_metadata": execution.import_metadata,
                    "bbox_overlay": _bbox_overlay_payload(
                        execution=execution,
                        material_group=material_group,
                        question_no=int(question.question_no),
                        question_bbox=question.provider_bbox or question.bbox,
                    ),
                },
            },
        }
    return payloads


def source_document_id_for_path(pdf_path: str) -> str:
    path = Path(pdf_path)
    stat = path.stat() if path.exists() else None
    signature = f"{path.name}:{getattr(stat, 'st_size', 0)}:{int(getattr(stat, 'st_mtime', 0) or 0)}"
    return hashlib.sha1(signature.encode("utf-8")).hexdigest()[:16]


def task_id_from_debug_dir(debug_dir: str | None) -> str | None:
    if not debug_dir:
        return None
    parts = Path(debug_dir).parts
    if "pdf-ai-preaudit" in parts:
        index = parts.index("pdf-ai-preaudit")
        if index + 1 < len(parts):
            task_id = str(parts[index + 1]).strip()
            if task_id:
                return task_id
    return Path(debug_dir).name.strip() or None


def _provider_has_structured_text(result: ProviderOCRResult) -> bool:
    meaningful_types = {"stem", "option", "answer", "analysis", "material_intro", "text"}
    for page in result.page_results:
        for block in page.blocks:
            if block.block_type in meaningful_types and block.text.strip():
                return True
    return False


def _dedupe_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _load_precomputed_data_analysis(raw_response_ref: str | None) -> dict[str, Any] | None:
    ref = str(raw_response_ref or "").strip()
    if not ref.endswith(".json"):
        return None
    path = Path(ref)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive only
        logger.warning("Failed to read precomputed data-analysis summary from %s: %s", path, exc)
        return None
    data = payload.get("precomputed_data_analysis")
    return data if isinstance(data, dict) else None


def _coerce_data_analysis_visual_context(
    payload: Any,
    *,
    fallback: Any,
):
    if not isinstance(payload, dict):
        return fallback
    try:
        return DataAnalysisVisualContext(
            model_provider=str(payload.get("model_provider") or getattr(fallback, "model_provider", "real_smoke_import")),
            model_name=str(payload.get("model_name") or getattr(fallback, "model_name", "real-smoke-vlm")),
            source_material_complete=bool(payload.get("source_material_complete")),
            chart_title_present=bool(payload.get("chart_title_present")),
            table_header_present=bool(payload.get("table_header_present")),
            unit_present=bool(payload.get("unit_present")),
            legend_present=bool(payload.get("legend_present")),
            table_or_chart_readable=bool(payload.get("table_or_chart_readable")),
            material_group_visual_consistent=bool(payload.get("material_group_visual_consistent")),
            suspected_crop_errors=[str(item) for item in payload.get("suspected_crop_errors") or [] if str(item).strip()],
            suspected_ocr_errors=[str(item) for item in payload.get("suspected_ocr_errors") or [] if str(item).strip()],
            critical_data_points_visible=[str(item) for item in payload.get("critical_data_points_visible") or [] if str(item).strip()],
            visual_summary=str(payload.get("visual_summary") or ""),
            warnings=[str(item) for item in payload.get("warnings") or [] if str(item).strip()],
        )
    except Exception as exc:  # pragma: no cover - defensive only
        logger.warning("Failed to coerce precomputed visual context: %s", exc)
        return fallback


def _coerce_data_analysis_understanding_results(
    payload: Any,
    *,
    fallback: list[Any],
) -> list[Any]:
    if not isinstance(payload, list):
        return fallback
    results: list[DataAnalysisUnderstandingResult] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            results.append(
                DataAnalysisUnderstandingResult(
                    model_provider=str(item.get("model_provider") or "real_smoke_import"),
                    model_name=str(item.get("model_name") or "real-smoke-llm"),
                    question_no=int(item.get("question_no") or 0),
                    can_understand_material=bool(item.get("can_understand_material")),
                    can_solve_question=bool(item.get("can_solve_question")),
                    answer_suggestion=str(item.get("answer_suggestion")).strip() if item.get("answer_suggestion") is not None else None,
                    calculation_reasoning=str(item.get("calculation_reasoning") or ""),
                    formula_used=str(item.get("formula_used") or ""),
                    data_points_used=[str(value) for value in item.get("data_points_used") or [] if str(value).strip()],
                    missing_information=[str(value) for value in item.get("missing_information") or [] if str(value).strip()],
                    ocr_answer_agreement=str(item.get("ocr_answer_agreement") or "no_ocr_answer"),
                    conflict_with_ocr_answer=bool(item.get("conflict_with_ocr_answer")),
                    comprehension_confidence=float(item.get("comprehension_confidence") or 0.0),
                    needs_human_review=bool(item.get("needs_human_review")),
                    warnings=[str(value) for value in item.get("warnings") or [] if str(value).strip()],
                )
            )
        except Exception as exc:  # pragma: no cover - defensive only
            logger.warning("Failed to coerce precomputed understanding result: %s", exc)
    return results or fallback


def _coerce_data_analysis_quality_gate(
    payload: Any,
    *,
    fallback: Any,
):
    if not isinstance(payload, dict):
        return fallback
    try:
        return DataAnalysisQualityGate(
            has_shared_material=bool(payload.get("has_shared_material")),
            has_valid_question_range=bool(payload.get("has_valid_question_range")),
            children_share_same_material_id=bool(payload.get("children_share_same_material_id")),
            shared_assets_preserved=bool(payload.get("shared_assets_preserved")),
            table_header_complete=bool(payload.get("table_header_complete")),
            unit_complete=bool(payload.get("unit_complete")),
            chart_title_complete=bool(payload.get("chart_title_complete")),
            local_stem_not_polluted=bool(payload.get("local_stem_not_polluted")),
            llm_can_understand_material=bool(payload.get("llm_can_understand_material")),
            llm_can_solve_question=bool(payload.get("llm_can_solve_question")),
            calculation_reasoning_present=bool(payload.get("calculation_reasoning_present")),
            answer_conflict=bool(payload.get("answer_conflict")),
            comprehension_confidence=float(payload.get("comprehension_confidence") or 0.0),
            review_ready=bool(payload.get("review_ready")),
            needs_human_review=bool(payload.get("needs_human_review")),
            blocking_reasons=[str(item) for item in payload.get("blocking_reasons") or [] if str(item).strip()],
            warnings=[str(item) for item in payload.get("warnings") or [] if str(item).strip()],
        )
    except Exception as exc:  # pragma: no cover - defensive only
        logger.warning("Failed to coerce precomputed quality gate: %s", exc)
        return fallback


def _to_page_text(text: str, block_type: str) -> str:
    normalized = text.strip()
    if not normalized:
        return ""
    prefixes = {
        "answer": "答案：",
        "analysis": "解析：",
    }
    prefix = prefixes.get(block_type)
    if prefix and not normalized.startswith(prefix):
        return f"{prefix}{normalized}"
    return normalized


def _region_for_block(extractor: Any, page_index: int, block: Any) -> Region | None:
    if len(block.bbox) != 4:
        return None
    try:
        rect = fitz.Rect(*block.bbox)
        page_rect = extractor.doc[page_index].rect
        clipped = fitz.Rect(
            max(rect.x0, page_rect.x0),
            max(rect.y0, page_rect.y0),
            min(rect.x1, page_rect.x1),
            min(rect.y1, page_rect.y1),
        )
        if clipped.width <= 0 or clipped.height <= 0:
            return None
        return Region(
            type=block.block_type,
            bbox=[float(clipped.x0), float(clipped.y0), float(clipped.x1), float(clipped.y1)],
            base64=extractor.get_region_screenshot(page_index, clipped),
            page=page_index + 1,
        )
    except Exception as exc:  # pragma: no cover - defensive only
        logger.warning("Failed to build OCR region for page=%s block=%s reason=%s", page_index + 1, block.block_id, exc)
        return None


def _bbox_overlay_payload(
    *,
    execution: CommercialOCRExecution,
    material_group: MaterialGroup | None,
    question_no: int,
    question_bbox: list[float],
) -> dict[str, Any]:
    highlights: list[dict[str, Any]] = []
    if question_bbox and len(question_bbox) == 4:
        highlights.append(
            {
                "page": _page_for_bbox(question_bbox, material_group),
                "bbox": list(question_bbox),
                "label": f"{question_no}题",
                "kind": "question",
            }
        )
    if material_group is not None:
        material_bbox = _union_bbox([asset.get("bbox") for asset in material_group.shared_assets])
        if material_bbox:
            highlights.append(
                {
                    "page": material_group.source_page_span[0] if material_group.source_page_span else 1,
                    "bbox": material_bbox,
                    "label": f"{material_group.question_range[0]}-{material_group.question_range[-1]}共享材料",
                    "kind": "shared_material",
                }
            )
        for asset in material_group.chart_blocks + material_group.table_blocks:
            bbox = asset.get("bbox")
            if not isinstance(bbox, list) or len(bbox) != 4:
                continue
            label = "图表 bbox" if asset in material_group.chart_blocks else "表格 bbox"
            highlights.append(
                {
                    "page": int(asset.get("page_no") or material_group.source_page_span[0] or 1),
                    "bbox": list(bbox),
                    "label": label,
                    "kind": str(asset.get("block_type") or "visual"),
                }
            )
        for sibling in execution.semantic_assembly.normalized_questions:
            if sibling.material_id != material_group.material_id or sibling.question_no is None:
                continue
            sibling_bbox = sibling.provider_bbox or sibling.bbox
            if sibling.question_no == question_no or len(sibling_bbox) != 4:
                continue
            highlights.append(
                {
                    "page": sibling.source_page_span[0] if sibling.source_page_span else 1,
                    "bbox": list(sibling_bbox),
                    "label": f"{sibling.question_no}题",
                    "kind": "sibling_question",
                }
            )
    return {"highlights": highlights}


def _visual_summary_for_question(
    execution: CommercialOCRExecution,
    material_group: MaterialGroup | None,
) -> str | None:
    if execution.data_analysis_visual_context is not None:
        return execution.data_analysis_visual_context.visual_summary
    if execution.visual_understanding is not None:
        return execution.visual_understanding.get("visual_summary") or execution.visual_understanding.get("visual_grouping_summary")
    if material_group is not None:
        return material_group.shared_stem
    return None


def _visual_risk_flags(
    execution: CommercialOCRExecution,
    material_group: MaterialGroup | None,
) -> list[str]:
    flags: list[str] = []
    if execution.data_analysis_visual_context is not None:
        flags.extend(execution.data_analysis_visual_context.suspected_crop_errors)
        flags.extend(execution.data_analysis_visual_context.suspected_ocr_errors)
        flags.extend(execution.data_analysis_visual_context.warnings)
    if material_group is not None:
        flags.extend(material_group.warnings)
    return list(dict.fromkeys(flag for flag in flags if flag))


def _ai_risk_flags(
    execution: CommercialOCRExecution,
    understanding: Any,
) -> list[str]:
    flags: list[str] = []
    if execution.data_analysis_quality_gate is not None:
        flags.extend(execution.data_analysis_quality_gate.blocking_reasons)
        flags.extend(execution.data_analysis_quality_gate.warnings)
    if understanding is not None:
        flags.extend(understanding.missing_information)
        flags.extend(understanding.warnings)
    return list(dict.fromkeys(flag for flag in flags if flag))


def _bbox_source_for_question(
    *,
    execution: CommercialOCRExecution,
    question: Any,
) -> str:
    import_metadata = execution.import_metadata if isinstance(execution.import_metadata, dict) else {}
    per_question = import_metadata.get("per_question") if isinstance(import_metadata.get("per_question"), dict) else {}
    question_import = per_question.get(str(question.question_no)) if isinstance(per_question, dict) else None
    if isinstance(question_import, dict):
        value = str(question_import.get("bbox_source") or "").strip()
        if value:
            return value
    shared_value = str(import_metadata.get("bbox_source") or "").strip()
    if shared_value:
        return shared_value
    question_provider = str(question.provider or "").strip()
    if question_provider:
        return question_provider
    provider_name = str(execution.provider_result.provider_name if execution.provider_result else execution.effective_provider or "").strip()
    return provider_name or LOCAL_PARSER_PROVIDER


def _union_bbox(items: list[Any]) -> list[float]:
    bboxes = [item for item in items if isinstance(item, list) and len(item) == 4]
    if not bboxes:
        return []
    return [
        min(bbox[0] for bbox in bboxes),
        min(bbox[1] for bbox in bboxes),
        max(bbox[2] for bbox in bboxes),
        max(bbox[3] for bbox in bboxes),
    ]


def _page_for_bbox(_bbox: list[float], material_group: MaterialGroup | None) -> int:
    if material_group and material_group.source_page_span:
        return int(material_group.source_page_span[0])
    return 1
