from __future__ import annotations

from typing import Any

from commercial_ocr.config import compact_dict
from commercial_ocr.data_analysis import build_data_analysis_visual_context
from commercial_ocr.types import ParseQualityGateResult, SemanticAssemblyResult


def build_visual_understanding_summary(
    assembly: SemanticAssemblyResult,
    *,
    quality_gate: ParseQualityGateResult,
    provider_name: str,
    provider_trace_ref: str | None,
    fallback_used: bool,
) -> dict[str, Any]:
    trigger_reasons = _trigger_reasons(
        assembly=assembly,
        quality_gate=quality_gate,
        fallback_used=fallback_used,
    )
    if not trigger_reasons:
        return {
            "triggered": False,
            "mode": "mock",
            "provider": "mock_visual_understanding",
            "provider_name": provider_name,
            "provider_trace_ref": provider_trace_ref,
            "trigger_reasons": [],
            "visual_grouping_summary": "high_confidence_text_only_skip",
            "detected_diagram_elements": [],
            "table_structure_notes": [],
            "ocr_error_suspicions": [],
            "material_ownership_assessment": [],
            "cross_page_suspicion": False,
            "answer_consistency_check": {"status": "skipped", "reason": "visual_understanding_not_triggered"},
            "confidence": 0.98,
            "data_analysis_visual_context": None,
            "warnings": [],
        }

    data_analysis_visual_context = build_data_analysis_visual_context(assembly)
    diagram_elements: list[dict[str, Any]] = []
    table_notes: list[str] = []
    ocr_suspicions: list[str] = []
    ownership_assessment: list[dict[str, Any]] = []
    warnings: list[str] = []
    cross_page_suspicion = False

    for group in assembly.material_groups:
        asset_types = sorted({str(asset.get("block_type") or "unknown") for asset in group.shared_assets})
        has_chart_or_table = any(asset_type in {"chart", "table"} for asset_type in asset_types)
        if group.source_page_span and len(group.source_page_span) == 2 and group.source_page_span[0] != group.source_page_span[1]:
            cross_page_suspicion = True
        ownership_assessment.append(
            compact_dict(
                {
                    "material_id": group.material_id,
                    "group_type": group.group_type,
                    "question_range": group.question_range,
                    "shared_asset_types": asset_types,
                    "assessment": "shared_material_confirmed" if group.grouping_confidence and group.grouping_confidence >= 0.8 else "shared_material_uncertain",
                    "needs_human_review": group.needs_human_review,
                }
            )
        )
        if has_chart_or_table:
            diagram_elements.append(
                compact_dict(
                    {
                        "material_id": group.material_id,
                        "question_range": group.question_range,
                        "asset_types": asset_types,
                        "source_page_span": group.source_page_span,
                    }
                )
            )
        for asset in group.shared_assets:
            asset_type = str(asset.get("block_type") or "unknown")
            asset_text = str(asset.get("text") or "").strip()
            if asset_type == "table":
                table_notes.append(
                    f"{group.material_id}:table:{asset_text or 'table_header_missing'}"
                )
            if asset_type == "chart" and not asset_text:
                warnings.append("missing_chart_title")
            if asset_type == "table" and not asset_text:
                warnings.append("missing_table_header")

    for question in assembly.normalized_questions:
        if question.question_role == "standalone_question" and question.group_type == "standalone" and question.confidence and question.confidence >= 0.9:
            continue
        if not question.bbox:
            ocr_suspicions.append(f"q{question.question_no}:bbox_missing")
        if question.answer in {None, ""}:
            ocr_suspicions.append(f"q{question.question_no}:answer_missing")
        if str(question.analysis or "").strip().lower() == "unknown":
            ocr_suspicions.append(f"q{question.question_no}:analysis_unknown")
        if question.validation_warnings:
            ocr_suspicions.extend(
                f"q{question.question_no}:{warning}" for warning in question.validation_warnings
            )

    for item in quality_gate.per_question_status:
        if item.get("warnings"):
            ocr_suspicions.extend(
                f"q{item.get('question_no')}:{warning}" for warning in item.get("warnings") or []
            )

    if fallback_used:
        warnings.append("provider_fallback_visual_review_required")
    if quality_gate.blocking_reasons:
        warnings.extend(str(reason) for reason in quality_gate.blocking_reasons)
    if data_analysis_visual_context is not None:
        warnings.extend(data_analysis_visual_context.warnings)
        warnings.extend(data_analysis_visual_context.suspected_crop_errors)
        warnings.extend(data_analysis_visual_context.suspected_ocr_errors)

    return {
        "triggered": True,
        "mode": "mock",
        "provider": "mock_visual_understanding",
        "provider_name": provider_name,
        "provider_trace_ref": provider_trace_ref,
        "trigger_reasons": trigger_reasons,
        "visual_grouping_summary": _grouping_summary(
            assembly=assembly,
            quality_gate=quality_gate,
            trigger_reasons=trigger_reasons,
        ),
        "detected_diagram_elements": diagram_elements,
        "table_structure_notes": list(dict.fromkeys(table_notes)),
        "ocr_error_suspicions": list(dict.fromkeys(ocr_suspicions)),
        "material_ownership_assessment": ownership_assessment,
        "cross_page_suspicion": cross_page_suspicion,
        "answer_consistency_check": {
            "status": "skipped",
            "reason": "mock_visual_understanding_does_not_run_answer_verification",
        },
        "confidence": _confidence_from_signals(
            trigger_reasons=trigger_reasons,
            quality_gate=quality_gate,
        ),
        "data_analysis_visual_context": data_analysis_visual_context.to_dict() if data_analysis_visual_context else None,
        "chart_title_present": data_analysis_visual_context.chart_title_present if data_analysis_visual_context else None,
        "table_header_present": data_analysis_visual_context.table_header_present if data_analysis_visual_context else None,
        "unit_present": data_analysis_visual_context.unit_present if data_analysis_visual_context else None,
        "legend_present": data_analysis_visual_context.legend_present if data_analysis_visual_context else None,
        "critical_data_points_visible": data_analysis_visual_context.critical_data_points_visible if data_analysis_visual_context else [],
        "visual_summary": data_analysis_visual_context.visual_summary if data_analysis_visual_context else "",
        "warnings": list(dict.fromkeys(warnings)),
    }


def _trigger_reasons(
    *,
    assembly: SemanticAssemblyResult,
    quality_gate: ParseQualityGateResult,
    fallback_used: bool,
) -> list[str]:
    reasons: list[str] = []
    if fallback_used:
        reasons.append("provider_fallback")
    if any(group.group_type in {"shared_material", "data_analysis_material"} for group in assembly.material_groups):
        reasons.append("shared_material_detected")
    if any(group.shared_assets for group in assembly.material_groups):
        reasons.append("shared_visual_assets_present")
    if any(group.needs_human_review for group in assembly.material_groups):
        reasons.append("material_group_uncertain")
    if not quality_gate.visual_assets_preserved:
        reasons.append("visual_assets_missing")
    if not quality_gate.semantic_consistent:
        reasons.append("semantic_inconsistency")
    if quality_gate.extracted_but_incomplete:
        reasons.append("content_incomplete")
    if any(not question.bbox for question in assembly.normalized_questions):
        reasons.append("bbox_missing")
    if any((question.confidence or 1.0) < 0.8 for question in assembly.normalized_questions):
        reasons.append("low_ocr_confidence")
    if any(question.question_image_ref is None and question.group_type == "shared_material" for question in assembly.normalized_questions):
        reasons.append("question_image_missing")
    if any(question.category == "资料分析" for question in assembly.normalized_questions):
        reasons.append("data_analysis_question")
    return list(dict.fromkeys(reasons))


def _grouping_summary(
    *,
    assembly: SemanticAssemblyResult,
    quality_gate: ParseQualityGateResult,
    trigger_reasons: list[str],
) -> str:
    if not assembly.material_groups:
        return "no_shared_material_visual_review"
    group_count = len(assembly.material_groups)
    question_count = len(assembly.normalized_questions)
    status = "consistent" if quality_gate.semantic_consistent else "needs_review"
    return (
        f"visual_grouping_{status}:groups={group_count};questions={question_count};"
        f"triggers={','.join(trigger_reasons)}"
    )


def _confidence_from_signals(
    *,
    trigger_reasons: list[str],
    quality_gate: ParseQualityGateResult,
) -> float:
    confidence = 0.84
    if quality_gate.semantic_consistent:
        confidence += 0.06
    if quality_gate.visual_assets_preserved:
        confidence += 0.04
    if quality_gate.extracted_but_incomplete:
        confidence -= 0.12
    if "material_group_uncertain" in trigger_reasons:
        confidence -= 0.08
    if "bbox_missing" in trigger_reasons:
        confidence -= 0.08
    return max(0.35, min(0.98, round(confidence, 4)))
