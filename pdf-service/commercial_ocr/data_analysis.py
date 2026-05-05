from __future__ import annotations

import re
from typing import Any

from commercial_ocr.types import (
    DataAnalysisQualityGate,
    DataAnalysisUnderstandingResult,
    DataAnalysisVisualContext,
    MaterialGroup,
    ParseQualityGateResult,
    SemanticAssemblyResult,
)


UNIT_TOKENS = ("单位", "亿元", "万元", "%", "人", "家", "吨", "平方米", "公里")
LEGEND_TOKENS = ("图例", "系列", "同比", "规模")
DATA_ANALYSIS_MODELS = {
    "visual_provider": "mock",
    "visual_model": "qwen-vl-mock",
    "text_provider": "mock",
    "text_model": "qwen-text-mock",
}


def build_data_analysis_visual_context(
    assembly: SemanticAssemblyResult,
) -> DataAnalysisVisualContext | None:
    group = primary_data_analysis_group(assembly)
    if group is None:
        return None

    chart_blocks = list(group.chart_blocks)
    table_blocks = list(group.table_blocks)
    material_texts = _material_texts(group)
    questions = questions_for_group(assembly, group)
    question_numbers = [question.question_no for question in questions if question.question_no is not None]

    source_material_complete = bool(group.shared_stem.strip()) and bool(group.shared_assets) and bool(question_numbers)
    chart_title_present = not chart_blocks or all(_has_text(block) for block in chart_blocks)
    table_header_present = not table_blocks or all(_has_text(block) for block in table_blocks)
    unit_present = _contains_any(material_texts, UNIT_TOKENS)
    legend_present = not chart_blocks or _contains_any(material_texts, LEGEND_TOKENS)
    table_or_chart_readable = bool(chart_blocks or table_blocks) and all(block.get("bbox") for block in group.shared_assets)
    material_group_visual_consistent = len({question.material_id for question in questions if question.material_id}) == 1

    suspected_crop_errors: list[str] = []
    suspected_ocr_errors: list[str] = []
    warnings: list[str] = []

    if not source_material_complete:
        suspected_crop_errors.append("source_material_incomplete")
    if chart_blocks and not chart_title_present:
        suspected_ocr_errors.append("chart_title_missing")
    if table_blocks and not table_header_present:
        suspected_ocr_errors.append("table_header_missing")
    if (chart_blocks or table_blocks) and not unit_present:
        suspected_ocr_errors.append("unit_missing")
    if chart_blocks and not legend_present:
        warnings.append("legend_absent_or_not_needed")
    if not material_group_visual_consistent:
        warnings.append("material_group_visual_inconsistent")
    if group.needs_human_review:
        warnings.extend(group.warnings)

    critical_data_points_visible = _critical_data_points(group)
    visual_summary = (
        f"资料分析材料覆盖题号 {group.question_range[0]}-{group.question_range[-1]}，"
        f"图表标题={'完整' if chart_title_present else '缺失'}，"
        f"表头={'完整' if table_header_present else '缺失'}，"
        f"单位={'完整' if unit_present else '缺失'}。"
    )

    return DataAnalysisVisualContext(
        model_provider=DATA_ANALYSIS_MODELS["visual_provider"],
        model_name=DATA_ANALYSIS_MODELS["visual_model"],
        source_material_complete=source_material_complete,
        chart_title_present=chart_title_present,
        table_header_present=table_header_present,
        unit_present=unit_present,
        legend_present=legend_present,
        table_or_chart_readable=table_or_chart_readable,
        material_group_visual_consistent=material_group_visual_consistent,
        suspected_crop_errors=list(dict.fromkeys(suspected_crop_errors)),
        suspected_ocr_errors=list(dict.fromkeys(suspected_ocr_errors)),
        critical_data_points_visible=critical_data_points_visible,
        visual_summary=visual_summary,
        warnings=list(dict.fromkeys(warnings)),
    )


def build_data_analysis_understanding_results(
    assembly: SemanticAssemblyResult,
    visual_context: DataAnalysisVisualContext | None,
) -> list[DataAnalysisUnderstandingResult]:
    group = primary_data_analysis_group(assembly)
    if group is None or visual_context is None:
        return []

    dataset = _extract_dataset(group)
    results: list[DataAnalysisUnderstandingResult] = []
    for question in questions_for_group(assembly, group):
        if question.question_no is None:
            continue
        results.append(
            _solve_data_analysis_question(
                question=question,
                dataset=dataset,
                visual_context=visual_context,
            )
        )
    return results


def evaluate_data_analysis_quality_gate(
    assembly: SemanticAssemblyResult,
    quality_gate: ParseQualityGateResult,
    visual_context: DataAnalysisVisualContext | None,
    understanding_results: list[DataAnalysisUnderstandingResult],
    *,
    fallback_used: bool,
) -> DataAnalysisQualityGate | None:
    group = primary_data_analysis_group(assembly)
    if group is None or visual_context is None:
        return None

    questions = questions_for_group(assembly, group)
    question_numbers = [question.question_no for question in questions if question.question_no is not None]
    valid_range = bool(group.question_range) and group.question_range == list(range(group.question_range[0], group.question_range[-1] + 1))
    children_share_same_material_id = len({question.material_id for question in questions if question.material_id}) == 1
    shared_assets_preserved = bool(group.shared_assets) and quality_gate.visual_assets_preserved
    local_stem_not_polluted = all(group.shared_stem.strip() not in (question.local_stem or "") for question in questions if group.shared_stem.strip())
    llm_can_understand_material = bool(understanding_results) and all(result.can_understand_material for result in understanding_results)
    llm_can_solve_question = bool(understanding_results) and all(result.can_solve_question for result in understanding_results)
    calculation_reasoning_present = bool(understanding_results) and all(bool(result.calculation_reasoning.strip()) for result in understanding_results)
    answer_conflict = any(result.conflict_with_ocr_answer for result in understanding_results)
    comprehension_confidence = round(
        min((result.comprehension_confidence for result in understanding_results), default=0.0),
        4,
    )

    blocking_reasons: list[str] = []
    warnings: list[str] = []

    if not question_numbers:
        blocking_reasons.append("shared_material_missing")
    if not valid_range:
        blocking_reasons.append("invalid_question_range")
    if not children_share_same_material_id:
        blocking_reasons.append("children_not_sharing_material_id")
    if any(not question.provider_bbox for question in questions):
        blocking_reasons.append("ocr_bbox_missing")
    if any(question.layout_only for question in questions):
        blocking_reasons.append("layout_only_used_as_complete_result")
    if not shared_assets_preserved:
        blocking_reasons.append("shared_assets_missing")
    if group.chart_blocks and not visual_context.chart_title_present:
        blocking_reasons.append("chart_title_missing")
    if group.table_blocks and not visual_context.table_header_present:
        blocking_reasons.append("table_header_missing")
    if (group.table_blocks or group.chart_blocks) and not visual_context.unit_present:
        blocking_reasons.append("unit_missing")
    if not llm_can_understand_material:
        blocking_reasons.append("llm_cannot_understand_material")
    if not llm_can_solve_question:
        blocking_reasons.append("llm_cannot_solve_question")
    if not calculation_reasoning_present:
        blocking_reasons.append("calculation_reasoning_missing")
    if answer_conflict:
        blocking_reasons.append("ocr_answer_conflict")
    if not local_stem_not_polluted:
        blocking_reasons.append("local_stem_polluted_by_shared_stem")

    if fallback_used:
        warnings.append("provider_fallback_used")
    if comprehension_confidence < 0.9:
        warnings.append("comprehension_confidence_below_threshold")
    warnings.extend(visual_context.warnings)
    warnings.extend(result_warning for result in understanding_results for result_warning in result.warnings)

    review_ready = not blocking_reasons and comprehension_confidence >= 0.9 and not fallback_used
    needs_human_review = (
        fallback_used
        or quality_gate.needs_human_review
        or bool(blocking_reasons)
        or comprehension_confidence < 0.9
    )

    return DataAnalysisQualityGate(
        has_shared_material=bool(question_numbers),
        has_valid_question_range=valid_range,
        children_share_same_material_id=children_share_same_material_id,
        shared_assets_preserved=shared_assets_preserved,
        table_header_complete=visual_context.table_header_present,
        unit_complete=visual_context.unit_present,
        chart_title_complete=visual_context.chart_title_present,
        local_stem_not_polluted=local_stem_not_polluted,
        llm_can_understand_material=llm_can_understand_material,
        llm_can_solve_question=llm_can_solve_question,
        calculation_reasoning_present=calculation_reasoning_present,
        answer_conflict=answer_conflict,
        comprehension_confidence=comprehension_confidence,
        review_ready=review_ready,
        needs_human_review=needs_human_review,
        blocking_reasons=list(dict.fromkeys(blocking_reasons)),
        warnings=list(dict.fromkeys(warnings)),
    )


def apply_data_analysis_gate_to_parse_quality(
    quality_gate: ParseQualityGateResult,
    data_gate: DataAnalysisQualityGate | None,
) -> ParseQualityGateResult:
    if data_gate is None:
        return quality_gate

    quality_gate.reasoning_verified = data_gate.calculation_reasoning_present and data_gate.llm_can_solve_question
    quality_gate.review_ready = quality_gate.review_ready and data_gate.review_ready
    quality_gate.needs_human_review = quality_gate.needs_human_review or data_gate.needs_human_review
    quality_gate.extracted_but_incomplete = quality_gate.extracted_but_incomplete or not data_gate.shared_assets_preserved
    quality_gate.blocking_reasons = list(
        dict.fromkeys([*quality_gate.blocking_reasons, *data_gate.blocking_reasons])
    )
    quality_gate.warnings = list(dict.fromkeys([*quality_gate.warnings, *data_gate.warnings]))
    return quality_gate


def primary_data_analysis_group(assembly: SemanticAssemblyResult) -> MaterialGroup | None:
    groups = [
        group
        for group in assembly.material_groups
        if group.group_type in {"data_analysis_material", "shared_material"}
        and len(group.question_range) >= 2
    ]
    if not groups:
        return None
    return sorted(
        groups,
        key=lambda group: (len(group.question_range), group.grouping_confidence or 0.0),
        reverse=True,
    )[0]


def questions_for_group(
    assembly: SemanticAssemblyResult,
    group: MaterialGroup,
) -> list[Any]:
    return [
        question
        for question in assembly.normalized_questions
        if question.material_id == group.material_id and question.question_no in group.question_range
    ]


def _solve_data_analysis_question(
    *,
    question: Any,
    dataset: dict[str, dict[str, float]],
    visual_context: DataAnalysisVisualContext,
) -> DataAnalysisUnderstandingResult:
    question_text = str(question.full_stem or question.local_stem or "").strip()
    missing_information: list[str] = []
    warnings: list[str] = []
    answer_suggestion: str | None = None
    calculation_reasoning = ""
    formula_used = ""
    data_points_used: list[str] = []
    can_understand_material = bool(question_text) and visual_context.source_material_complete and visual_context.table_or_chart_readable
    can_solve_question = False

    if not visual_context.chart_title_present:
        missing_information.append("chart_title")
    if not visual_context.table_header_present:
        missing_information.append("table_header")
    if not visual_context.unit_present:
        missing_information.append("unit")

    city = _extract_city_name(question_text)
    options = dict(question.options or {})

    if dataset:
        if "同比增长" in question_text and city and city in dataset:
            row = dataset[city]
            yoy = row.get("yoy")
            base = row.get("base")
            current = row.get("current")
            if yoy is not None and base is not None and current is not None:
                answer_suggestion = _closest_numeric_option(options, yoy, suffix="%")
                calculation_reasoning = (
                    f"{city}2023年规模为 {base:g}，2024年规模为 {current:g}，"
                    f"同比增速=({current:g}-{base:g})/{base:g}={yoy:g}%。"
                )
                formula_used = "(现期-基期)/基期"
                data_points_used = [
                    f"{city}2023规模={base:g}",
                    f"{city}2024规模={current:g}",
                    f"{city}同比={yoy:g}%",
                ]
                can_solve_question = answer_suggestion is not None
        elif "占" in question_text and "比重" in question_text and city and city in dataset:
            total = sum(row.get("current", 0.0) for row in dataset.values())
            current = dataset[city].get("current")
            if total > 0 and current is not None:
                ratio = round(current / total * 100, 1)
                answer_suggestion = _closest_numeric_option(options, ratio, suffix="%")
                calculation_reasoning = f"四市总规模={total:g}，{city}规模={current:g}，占比={current:g}/{total:g}={ratio:g}%。"
                formula_used = "部分/整体"
                data_points_used = [f"四市总规模={total:g}", f"{city}规模={current:g}", f"{city}占比={ratio:g}%"]
                can_solve_question = answer_suggestion is not None
        elif "同比增速最高" in question_text:
            winner = max(dataset.items(), key=lambda item: item[1].get("yoy", float("-inf")))
            winner_city = winner[0]
            winner_yoy = winner[1].get("yoy")
            if winner_yoy is not None:
                answer_suggestion = _match_city_option(options, winner_city)
                calculation_reasoning = f"比较四市同比增速，{winner_city}最高，为 {winner_yoy:g}%。"
                formula_used = "同比增速比较"
                data_points_used = [f"{name}同比={row.get('yoy', 0.0):g}%" for name, row in dataset.items()]
                can_solve_question = answer_suggestion is not None
        elif "位列第几" in question_text and city and city in dataset:
            ranking = sorted(dataset.items(), key=lambda item: item[1].get("yoy", float("-inf")), reverse=True)
            ordered_names = [name for name, _row in ranking]
            if city in ordered_names:
                rank = ordered_names.index(city) + 1
                answer_suggestion = _match_rank_option(options, rank)
                calculation_reasoning = f"按同比增速从高到低排序为 {' > '.join(ordered_names)}，{city}位列第 {rank}。"
                formula_used = "同比增速排序"
                data_points_used = [f"{name}同比={row.get('yoy', 0.0):g}%" for name, row in ranking]
                can_solve_question = answer_suggestion is not None

    if not can_solve_question:
        ocr_answer = str(question.ocr_answer_candidate or question.answer or "").strip() or None
        ocr_analysis = str(question.ocr_analysis_candidate or question.analysis or "").strip()
        if ocr_answer:
            answer_suggestion = ocr_answer
            calculation_reasoning = ocr_analysis or "OCR 提供了答案候选，但缺少足够结构化数据支撑计算过程。"
            formula_used = _formula_hint(question_text)
            if not ocr_analysis:
                missing_information.append("calculation_reasoning")
            can_understand_material = can_understand_material and bool(ocr_analysis or visual_context.critical_data_points_visible)
            can_solve_question = bool(ocr_answer and ocr_analysis)
        else:
            missing_information.append("ocr_answer_candidate")
            warnings.append("unable_to_derive_answer_from_material")

    answer_suggestion = answer_suggestion or None
    ocr_answer = str(question.ocr_answer_candidate or question.answer or "").strip() or None
    if answer_suggestion and ocr_answer:
        ocr_answer_agreement = "agree" if answer_suggestion == ocr_answer else "disagree"
    elif ocr_answer:
        ocr_answer_agreement = "uncertain"
    else:
        ocr_answer_agreement = "no_ocr_answer"

    conflict_with_ocr_answer = ocr_answer_agreement == "disagree"
    confidence = _confidence_score(
        can_understand_material=can_understand_material,
        can_solve_question=can_solve_question,
        missing_information=missing_information,
        conflict_with_ocr_answer=conflict_with_ocr_answer,
        used_dataset=bool(dataset and can_solve_question),
    )

    if conflict_with_ocr_answer:
        warnings.append("ocr_answer_conflict")
    needs_human_review = confidence < 0.9 or conflict_with_ocr_answer or bool(missing_information)

    return DataAnalysisUnderstandingResult(
        model_provider=DATA_ANALYSIS_MODELS["text_provider"],
        model_name=DATA_ANALYSIS_MODELS["text_model"],
        question_no=int(question.question_no),
        can_understand_material=can_understand_material,
        can_solve_question=can_solve_question,
        answer_suggestion=answer_suggestion,
        calculation_reasoning=calculation_reasoning,
        formula_used=formula_used,
        data_points_used=data_points_used,
        missing_information=list(dict.fromkeys(missing_information)),
        ocr_answer_agreement=ocr_answer_agreement,
        conflict_with_ocr_answer=conflict_with_ocr_answer,
        comprehension_confidence=confidence,
        needs_human_review=needs_human_review,
        warnings=list(dict.fromkeys(warnings)),
    )


def _material_texts(group: MaterialGroup) -> list[str]:
    texts = [str(group.shared_stem or "").strip()]
    texts.extend(str(asset.get("text") or "").strip() for asset in group.shared_assets)
    return [text for text in texts if text]


def _critical_data_points(group: MaterialGroup) -> list[str]:
    critical: list[str] = []
    for text in _material_texts(group):
        for line in text.splitlines():
            normalized = line.strip()
            if normalized and re.search(r"\d", normalized):
                critical.append(normalized)
    return list(dict.fromkeys(critical[:12]))


def _contains_any(texts: list[str], tokens: tuple[str, ...]) -> bool:
    joined = "\n".join(texts)
    return any(token in joined for token in tokens)


def _has_text(block: dict[str, Any]) -> bool:
    return bool(str(block.get("text") or "").strip())


def _extract_dataset(group: MaterialGroup) -> dict[str, dict[str, float]]:
    dataset: dict[str, dict[str, float]] = {}
    for block in group.table_blocks:
        for raw_line in str(block.get("text") or "").splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            if not line or line.startswith(("单位", "图例")):
                continue
            if any(token in line for token in ("城市", "2023规模", "2024规模", "同比")):
                continue
            match = re.match(
                r"(?P<city>[\u4e00-\u9fffA-Za-z0-9]+市?)\s+(?P<base>\d+(?:\.\d+)?)\s+(?P<current>\d+(?:\.\d+)?)\s+(?P<yoy>\d+(?:\.\d+)?)%?$",
                line,
            )
            if not match:
                continue
            dataset[match.group("city")] = {
                "base": float(match.group("base")),
                "current": float(match.group("current")),
                "yoy": float(match.group("yoy")),
            }
    return dataset


def _extract_city_name(text: str) -> str | None:
    match = re.search(r"([甲乙丙丁戊己庚辛壬癸A-Za-z0-9一二三四五六七八九十]+市)", text)
    return match.group(1) if match else None


def _closest_numeric_option(
    options: dict[str, str],
    value: float,
    *,
    suffix: str,
) -> str | None:
    best_label: str | None = None
    best_distance = float("inf")
    for label, text in options.items():
        match = re.search(r"(-?\d+(?:\.\d+)?)", str(text))
        if not match:
            continue
        distance = abs(float(match.group(1)) - value)
        if distance < best_distance:
            best_distance = distance
            best_label = label
    return best_label


def _match_city_option(options: dict[str, str], city: str) -> str | None:
    for label, text in options.items():
        if city in str(text):
            return label
    return None


def _match_rank_option(options: dict[str, str], rank: int) -> str | None:
    rank_text = f"第{rank}"
    for label, text in options.items():
        normalized = str(text)
        if rank_text in normalized or str(rank) in normalized:
            return label
    return None


def _formula_hint(question_text: str) -> str:
    if "同比" in question_text:
        return "(现期-基期)/基期"
    if "比重" in question_text:
        return "部分/整体"
    if "排序" in question_text:
        return "排序比较"
    return ""


def _confidence_score(
    *,
    can_understand_material: bool,
    can_solve_question: bool,
    missing_information: list[str],
    conflict_with_ocr_answer: bool,
    used_dataset: bool,
) -> float:
    if not can_understand_material:
        return 0.42
    confidence = 0.78
    if can_solve_question:
        confidence += 0.08
    if used_dataset:
        confidence += 0.12
    if missing_information:
        confidence -= min(0.18, len(missing_information) * 0.05)
    if conflict_with_ocr_answer:
        confidence -= 0.25
    return max(0.35, min(0.98, round(confidence, 4)))
