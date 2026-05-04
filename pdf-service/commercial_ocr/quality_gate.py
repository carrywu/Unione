from __future__ import annotations

from typing import Any

from commercial_ocr.types import ParseQualityGateResult, SemanticAssemblyResult


def evaluate_parse_quality(
    assembly: SemanticAssemblyResult,
    *,
    fallback_used: bool = False,
    provider_error: dict[str, Any] | None = None,
) -> ParseQualityGateResult:
    questions = assembly.normalized_questions
    material_groups = assembly.material_groups
    blocking_reasons: list[str] = []
    warnings: list[str] = []
    per_question_status: list[dict[str, Any]] = []

    extraction_complete = _is_extraction_complete(questions)
    if not extraction_complete:
        blocking_reasons.append("question_objects_missing_or_non_contiguous")

    ocr_complete = True
    visual_assets_preserved = True
    semantic_consistent = True
    extracted_but_incomplete = False
    needs_human_review = fallback_used or provider_error is not None

    if fallback_used:
        warnings.append("provider_fallback_used")
    if provider_error is not None:
        warnings.append("provider_error_present")

    material_by_id = {group.material_id: group for group in material_groups}

    for question in questions:
        question_missing = list(question.missing_fields)
        question_warnings = list(question.validation_warnings)
        question_visual_ok = True
        question_ocr_ok = True
        question_semantic_ok = True
        question_blocking: list[str] = []

        if not question.full_stem.strip():
            question_ocr_ok = False
            question_blocking.append("full_stem_missing")
        if not question.options and "layout_only_requires_followup" not in question.validation_warnings:
            question_ocr_ok = False
            question_blocking.append("options_missing")
        if question.answer in {None, ""}:
            extracted_but_incomplete = True
            question_blocking.append("answer_missing")
        if question.analysis in {None, ""}:
            extracted_but_incomplete = True
            question_blocking.append("analysis_missing")
        elif str(question.analysis).strip().lower() == "unknown":
            extracted_but_incomplete = True
            question_blocking.append("analysis_unknown")
        if not question.bbox:
            extracted_but_incomplete = True
            needs_human_review = True
            question_visual_ok = False
            question_blocking.append("bbox_missing")

        material_group = material_by_id.get(question.material_id or "")
        requires_shared_visual = bool(material_group) or question.category == "资料分析"
        has_visual_asset = bool(question.question_image_ref)
        if material_group and material_group.shared_assets:
            has_visual_asset = True
        if requires_shared_visual and not has_visual_asset:
            visual_assets_preserved = False
            question_visual_ok = False
            extracted_but_incomplete = True
            question_blocking.append("visual_assets_missing")

        if material_group:
            if question.group_type != material_group.group_type:
                semantic_consistent = False
                question_semantic_ok = False
                question_blocking.append("group_type_mismatch")
            if question.question_role != "child_question":
                semantic_consistent = False
                question_semantic_ok = False
                question_blocking.append("question_role_invalid")
            if question.question_no not in material_group.question_range:
                semantic_consistent = False
                question_semantic_ok = False
                question_blocking.append("question_range_mismatch")
            if material_group.shared_stem and material_group.shared_stem in question.local_stem:
                semantic_consistent = False
                question_semantic_ok = False
                question_blocking.append("shared_stem_duplicated_in_local_stem")
            if material_group.needs_human_review:
                needs_human_review = True
        elif question.group_type == "shared_material":
            semantic_consistent = False
            question_semantic_ok = False
            question_blocking.append("missing_material_group")

        if "layout_only_requires_followup" in question.validation_warnings:
            visual_assets_preserved = False
            semantic_consistent = False
            question_visual_ok = False
            question_semantic_ok = False
            extracted_but_incomplete = True
            needs_human_review = True
            question_blocking.append("layout_only_result")

        if question.needs_human_review:
            needs_human_review = True

        if question_blocking:
            warnings.extend(question_blocking)
        ocr_complete = ocr_complete and question_ocr_ok and "answer_missing" not in question_blocking and "analysis_missing" not in question_blocking and "analysis_unknown" not in question_blocking
        visual_assets_preserved = visual_assets_preserved and question_visual_ok
        semantic_consistent = semantic_consistent and question_semantic_ok
        per_question_status.append(
            {
                "question_id": question.question_id,
                "question_no": question.question_no,
                "group_type": question.group_type,
                "complete": not question_blocking,
                "ocr_complete": question_ocr_ok,
                "visual_assets_preserved": question_visual_ok,
                "semantic_consistent": question_semantic_ok,
                "needs_human_review": question.needs_human_review or bool(question_blocking),
                "missing_fields": question_missing,
                "warnings": list(dict.fromkeys(question_warnings + question_blocking)),
            }
        )

    for group in material_groups:
        if group.needs_human_review:
            needs_human_review = True
        expected = set(group.question_range)
        actual = {question.question_no for question in questions if question.material_id == group.material_id and question.question_no is not None}
        if expected != actual:
            semantic_consistent = False
            blocking_reasons.append(f"material_group_range_incomplete:{group.material_id}")
        if _is_visual_group(group) and not group.shared_assets:
            visual_assets_preserved = False
            blocking_reasons.append(f"shared_assets_missing:{group.material_id}")

    if not ocr_complete:
        blocking_reasons.append("ocr_content_incomplete")
    if not visual_assets_preserved:
        blocking_reasons.append("visual_assets_not_preserved")
    if not semantic_consistent:
        blocking_reasons.append("semantic_grouping_inconsistent")
    if any(question.answer in {None, ""} for question in questions):
        blocking_reasons.append("answer_missing")
    if any(str(question.analysis or "").strip().lower() == "unknown" for question in questions):
        blocking_reasons.append("analysis_unknown")
    if any(not question.bbox for question in questions):
        blocking_reasons.append("bbox_missing")

    reasoning_verified = False
    warnings.append("reasoning_verification_skipped")
    review_ready = extraction_complete and ocr_complete and visual_assets_preserved and semantic_consistent and not blocking_reasons
    return ParseQualityGateResult(
        extraction_complete=extraction_complete,
        ocr_complete=ocr_complete,
        visual_assets_preserved=visual_assets_preserved,
        semantic_consistent=semantic_consistent,
        reasoning_verified=reasoning_verified,
        review_ready=review_ready,
        extracted_but_incomplete=extracted_but_incomplete,
        needs_human_review=needs_human_review or bool(blocking_reasons),
        blocking_reasons=list(dict.fromkeys(blocking_reasons)),
        warnings=list(dict.fromkeys(warnings + assembly.warnings)),
        per_question_status=per_question_status,
    )


def _is_extraction_complete(questions: list[Any]) -> bool:
    if not questions:
        return False
    numbers = [question.question_no for question in questions if question.question_no is not None]
    if len(numbers) != len(questions):
        return False
    ordered = sorted(numbers)
    return ordered == list(range(ordered[0], ordered[-1] + 1))


def _is_visual_group(group: Any) -> bool:
    if group.group_type in {"chart_group", "shared_material"}:
        return True
    return any(token in group.shared_stem for token in ("图", "表", "同比", "环比", "增长率"))
