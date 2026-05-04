from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from commercial_ocr.normalizer import extract_question_no, flatten_blocks, is_valid_bbox
from commercial_ocr.types import MaterialGroup, NormalizedOCRBlock, NormalizedQuestion, ProviderPageResult, SemanticAssemblyResult


EXPLICIT_RANGE_PATTERNS = [
    re.compile(r"(根据以下资料|根据所给资料|阅读以下材料)[^0-9]{0,12}回答\s*(\d{1,3})\s*[-~—至到]\s*(\d{1,3})\s*题"),
    re.compile(r"(根据以下资料|根据所给资料|阅读以下材料)[^0-9]{0,12}回答(\d{1,3})\s*[-~—至到]\s*(\d{1,3})题"),
]
AMBIGUOUS_PATTERNS = [
    re.compile(r"(根据以下资料|根据所给资料|阅读以下材料).{0,20}(回答下列问题|回答下列各题)"),
]
DATA_ANALYSIS_PATTERNS = ("根据以下资料", "根据所给资料", "阅读以下材料", "同比", "环比", "增长率", "比重", "百分点", "倍数")
OPTION_RE = re.compile(r"^\s*([A-H])[.．、:：)]\s*(.+)$")


def assemble_semantic_result(
    page_results: list[ProviderPageResult],
    *,
    provider_name: str,
    provider_trace_ref: str | None = None,
) -> SemanticAssemblyResult:
    blocks = flatten_blocks(page_results)
    if not blocks:
        return SemanticAssemblyResult(warnings=["no_ocr_blocks"])

    block_positions = {block.block_id: index for index, block in enumerate(blocks)}
    buckets = _build_question_buckets(blocks)
    material_groups, material_by_question = _build_material_groups(blocks, block_positions, buckets)
    normalized_questions = _build_normalized_questions(
        blocks=blocks,
        buckets=buckets,
        material_groups=material_groups,
        material_by_question=material_by_question,
        provider_name=provider_name,
        provider_trace_ref=provider_trace_ref,
    )
    question_groups = _build_question_groups(normalized_questions)
    warnings = _collect_global_warnings(material_groups, normalized_questions)
    return SemanticAssemblyResult(
        material_groups=material_groups,
        question_groups=question_groups,
        normalized_questions=normalized_questions,
        warnings=warnings,
    )


def _build_question_buckets(blocks: list[NormalizedOCRBlock]) -> dict[int, dict[str, Any]]:
    buckets: dict[int, dict[str, Any]] = {}
    current_question_no: int | None = None
    for block in blocks:
        candidate_question_no = _infer_question_no(block)
        if candidate_question_no is not None:
            current_question_no = candidate_question_no
        attach_question_no = candidate_question_no if candidate_question_no is not None else current_question_no
        if attach_question_no is None:
            continue
        if block.block_type == "material_intro" and candidate_question_no is None:
            continue
        bucket = buckets.setdefault(
            attach_question_no,
            {
                "question_no": attach_question_no,
                "blocks": [],
                "warnings": [],
            },
        )
        bucket["blocks"].append(block)
        bucket["warnings"].extend(block.warnings)
    return dict(sorted(buckets.items()))


def _build_material_groups(
    blocks: list[NormalizedOCRBlock],
    block_positions: dict[str, int],
    buckets: dict[int, dict[str, Any]],
) -> tuple[list[MaterialGroup], dict[int, MaterialGroup]]:
    question_numbers = sorted(buckets)
    material_groups: list[MaterialGroup] = []
    material_by_question: dict[int, MaterialGroup] = {}

    for block in blocks:
        if block.block_type not in {"material_intro", "title", "header", "text"}:
            continue
        text = block.text.strip()
        if not text:
            continue
        explicit_match = _match_explicit_material_range(text)
        if explicit_match is not None:
            start_no, end_no, evidence = explicit_match
            group = _build_material_group_from_range(
                blocks=blocks,
                block_positions=block_positions,
                buckets=buckets,
                anchor_block=block,
                question_numbers=question_numbers,
                start_no=start_no,
                end_no=end_no,
                evidence=evidence,
            )
            if group is not None:
                material_groups.append(group)
                for question_no in group.question_range:
                    if question_no in buckets:
                        material_by_question[question_no] = group
            continue

        if _matches_ambiguous_material_intro(text):
            group = _build_ambiguous_material_group(
                blocks=blocks,
                block_positions=block_positions,
                buckets=buckets,
                anchor_block=block,
                question_numbers=question_numbers,
            )
            if group is not None:
                material_groups.append(group)
                for question_no in group.question_range:
                    if question_no in buckets and question_no not in material_by_question:
                        material_by_question[question_no] = group

    deduped_groups: list[MaterialGroup] = []
    seen_group_ids: set[str] = set()
    for group in material_groups:
        if group.material_id in seen_group_ids:
            continue
        seen_group_ids.add(group.material_id)
        deduped_groups.append(group)
    return deduped_groups, material_by_question


def _build_material_group_from_range(
    *,
    blocks: list[NormalizedOCRBlock],
    block_positions: dict[str, int],
    buckets: dict[int, dict[str, Any]],
    anchor_block: NormalizedOCRBlock,
    question_numbers: list[int],
    start_no: int,
    end_no: int,
    evidence: list[str],
) -> MaterialGroup | None:
    if end_no < start_no:
        start_no, end_no = end_no, start_no
    explicit_range = list(range(start_no, end_no + 1))
    present_range = [question_no for question_no in explicit_range if question_no in buckets]
    if not present_range:
        return None
    first_position = min(_first_question_position(buckets[question_no]["blocks"], block_positions) for question_no in present_range)
    last_position = max(_last_question_position(buckets[question_no]["blocks"], block_positions) for question_no in present_range)
    shared_stem_blocks = [
        block
        for block in blocks
        if block_positions[anchor_block.block_id] <= block_positions[block.block_id] < first_position
        and block.block_type in {"material_intro", "title", "header", "text"}
    ]
    shared_stem = "\n".join(dict.fromkeys(block.text.strip() for block in shared_stem_blocks if block.text.strip())).strip()
    shared_assets = _shared_assets_between(blocks, block_positions, start_position=block_positions[anchor_block.block_id], end_position=last_position)
    missing = [question_no for question_no in explicit_range if question_no not in buckets]
    warnings = []
    needs_human_review = False
    if missing:
        warnings.append(f"material_group_missing_questions:{','.join(str(item) for item in missing)}")
        needs_human_review = True
    if _contains_data_analysis_signal(shared_stem) and not shared_assets:
        warnings.append("shared_assets_missing")
        needs_human_review = True
    source_blocks = [block.block_id for block in shared_stem_blocks] + [asset["asset_id"] for asset in shared_assets]
    source_blocks.extend(block.block_id for question_no in present_range for block in buckets[question_no]["blocks"])
    page_span = sorted({block.page_no for question_no in present_range for block in buckets[question_no]["blocks"]} | {anchor_block.page_no})
    return MaterialGroup(
        material_id=f"material-{start_no}-{end_no}-p{anchor_block.page_no}",
        group_type="shared_material",
        question_range=explicit_range,
        shared_stem=shared_stem or anchor_block.text.strip(),
        shared_assets=shared_assets,
        source_page_span=[page_span[0], page_span[-1]] if page_span else [anchor_block.page_no, anchor_block.page_no],
        source_blocks=list(dict.fromkeys(source_blocks)),
        grouping_evidence=evidence + [f"anchor_block:{anchor_block.block_id}"],
        grouping_confidence=0.95 if not missing else 0.72,
        needs_human_review=needs_human_review,
        warnings=warnings,
    )


def _build_ambiguous_material_group(
    *,
    blocks: list[NormalizedOCRBlock],
    block_positions: dict[str, int],
    buckets: dict[int, dict[str, Any]],
    anchor_block: NormalizedOCRBlock,
    question_numbers: list[int],
) -> MaterialGroup | None:
    if not question_numbers:
        return None
    anchor_position = block_positions[anchor_block.block_id]
    following = [question_no for question_no in question_numbers if _first_question_position(buckets[question_no]["blocks"], block_positions) > anchor_position]
    if not following:
        return None
    contiguous = [following[0]]
    for question_no in following[1:]:
        if question_no == contiguous[-1] + 1 and len(contiguous) < 4:
            contiguous.append(question_no)
        else:
            break
    if len(contiguous) < 2:
        return None
    last_position = max(_last_question_position(buckets[question_no]["blocks"], block_positions) for question_no in contiguous)
    shared_assets = _shared_assets_between(blocks, block_positions, start_position=anchor_position, end_position=last_position)
    source_blocks = [anchor_block.block_id] + [asset["asset_id"] for asset in shared_assets]
    source_blocks.extend(block.block_id for question_no in contiguous for block in buckets[question_no]["blocks"])
    page_span = sorted({block.page_no for question_no in contiguous for block in buckets[question_no]["blocks"]} | {anchor_block.page_no})
    return MaterialGroup(
        material_id=f"material-ambiguous-{contiguous[0]}-{contiguous[-1]}-p{anchor_block.page_no}",
        group_type="shared_material",
        question_range=list(contiguous),
        shared_stem=anchor_block.text.strip(),
        shared_assets=shared_assets,
        source_page_span=[page_span[0], page_span[-1]] if page_span else [anchor_block.page_no, anchor_block.page_no],
        source_blocks=list(dict.fromkeys(source_blocks)),
        grouping_evidence=["ambiguous_material_intro", f"anchor_block:{anchor_block.block_id}"],
        grouping_confidence=0.58,
        needs_human_review=True,
        warnings=["material_group_range_uncertain"],
    )


def _build_normalized_questions(
    *,
    blocks: list[NormalizedOCRBlock],
    buckets: dict[int, dict[str, Any]],
    material_groups: list[MaterialGroup],
    material_by_question: dict[int, MaterialGroup],
    provider_name: str,
    provider_trace_ref: str | None,
) -> list[NormalizedQuestion]:
    normalized_questions: list[NormalizedQuestion] = []
    for question_no, bucket in buckets.items():
        question_blocks = list(bucket["blocks"])
        material_group = material_by_question.get(question_no)
        stem_blocks = [block for block in question_blocks if block.block_type in {"stem", "text"}]
        option_blocks = [block for block in question_blocks if block.block_type == "option"]
        answer_blocks = [block for block in question_blocks if block.block_type == "answer"]
        analysis_blocks = [block for block in question_blocks if block.block_type == "analysis"]
        visual_blocks = [block for block in question_blocks if block.block_type in {"figure", "chart", "table"}]
        local_stem = "\n".join(block.text.strip() for block in stem_blocks if block.text.strip()).strip()
        shared_stem = material_group.shared_stem.strip() if material_group else ""
        if shared_stem and local_stem.startswith(shared_stem):
            local_stem = local_stem[len(shared_stem) :].lstrip()
        if shared_stem and local_stem:
            full_stem = f"{shared_stem}\n{local_stem}".strip()
        else:
            full_stem = local_stem or shared_stem
        options = _parse_options(option_blocks)
        answer = _first_non_empty(answer_blocks)
        analysis = _first_non_empty(analysis_blocks)
        bbox = _union_bbox(question_blocks)
        confidence = _average_confidence(question_blocks)
        missing_fields = []
        validation_warnings = list(dict.fromkeys(bucket.get("warnings") or []))
        if not full_stem:
            missing_fields.append("full_stem")
        if not options and not any(block.block_type == "bbox_only" for block in question_blocks):
            missing_fields.append("options")
        if not bbox:
            missing_fields.append("bbox")
            validation_warnings.append("bbox_missing")
        if answer in {None, ""}:
            missing_fields.append("answer")
        if analysis in {None, ""}:
            missing_fields.append("analysis")
        if str(analysis or "").strip().lower() == "unknown":
            validation_warnings.append("analysis_unknown")
        group_type = material_group.group_type if material_group else "standalone"
        question_role = "child_question" if material_group else "standalone_question"
        question_image_ref = visual_blocks[0].block_id if visual_blocks else None
        if not question_image_ref and material_group and material_group.shared_assets:
            question_image_ref = None
        needs_human_review = bool(material_group and material_group.needs_human_review)
        if "bbox" in missing_fields or "options" in missing_fields or "analysis" in missing_fields:
            needs_human_review = True
        if any(block.block_type == "bbox_only" for block in question_blocks):
            needs_human_review = True
            validation_warnings.append("layout_only_requires_followup")
        normalized_questions.append(
            NormalizedQuestion(
                question_id=f"q-{question_no}",
                question_no=question_no,
                material_id=material_group.material_id if material_group else None,
                parent_group_id=material_group.material_id if material_group else f"question-group-{question_no}",
                group_type=group_type,
                question_role=question_role,
                question_range=list(material_group.question_range) if material_group else [question_no],
                shared_stem_ref=material_group.material_id if material_group else None,
                local_stem=local_stem,
                full_stem=full_stem,
                options=options,
                answer=answer,
                analysis=analysis,
                category=_classify_question_category(shared_stem, local_stem, material_group),
                subtype=None,
                source_page_span=_page_span(question_blocks),
                bbox=bbox,
                question_image_ref=question_image_ref,
                provider=provider_name,
                provider_trace_ref=provider_trace_ref,
                confidence=confidence,
                needs_human_review=needs_human_review,
                missing_fields=list(dict.fromkeys(missing_fields)),
                validation_warnings=list(dict.fromkeys(validation_warnings + (material_group.warnings if material_group else []))),
                grouping_evidence=list(material_group.grouping_evidence) if material_group else ["standalone_question"],
                grouping_confidence=material_group.grouping_confidence if material_group else 0.9,
            )
        )
    return normalized_questions


def _build_question_groups(normalized_questions: list[NormalizedQuestion]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for question in normalized_questions:
        group_id = str(question.parent_group_id or f"question-group-{question.question_no}")
        payload = grouped.setdefault(
            group_id,
            {
                "group_id": group_id,
                "group_type": question.group_type or "standalone",
                "material_id": question.material_id,
                "question_ids": [],
                "question_numbers": [],
                "needs_human_review": False,
            },
        )
        payload["question_ids"].append(question.question_id)
        if question.question_no is not None:
            payload["question_numbers"].append(question.question_no)
        payload["needs_human_review"] = payload["needs_human_review"] or question.needs_human_review
    return list(grouped.values())


def _collect_global_warnings(material_groups: list[MaterialGroup], normalized_questions: list[NormalizedQuestion]) -> list[str]:
    warnings: list[str] = []
    if not normalized_questions:
        warnings.append("no_normalized_questions")
    if any(question.group_type == "shared_material" for question in normalized_questions) and not material_groups:
        warnings.append("shared_material_questions_without_material_group")
    if any(question.needs_human_review for question in normalized_questions):
        warnings.append("questions_require_manual_review")
    return list(dict.fromkeys(warnings))


def _match_explicit_material_range(text: str) -> tuple[int, int, list[str]] | None:
    for pattern in EXPLICIT_RANGE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        start_no = int(match.group(2))
        end_no = int(match.group(3))
        return start_no, end_no, [f"explicit_range:{start_no}-{end_no}", f"material_intro:{match.group(1)}"]
    return None


def _matches_ambiguous_material_intro(text: str) -> bool:
    return any(pattern.search(text) for pattern in AMBIGUOUS_PATTERNS)


def _shared_assets_between(
    blocks: list[NormalizedOCRBlock],
    block_positions: dict[str, int],
    *,
    start_position: int,
    end_position: int,
) -> list[dict[str, Any]]:
    assets = []
    for block in blocks:
        position = block_positions[block.block_id]
        if position < start_position or position > end_position:
            continue
        if block.block_type not in {"figure", "chart", "table"}:
            continue
        assets.append(
            {
                "asset_id": block.block_id,
                "block_type": block.block_type,
                "page_no": block.page_no,
                "bbox": list(block.bbox),
                "text": block.text,
            }
        )
    return assets


def _first_non_empty(blocks: list[NormalizedOCRBlock]) -> str | None:
    for block in blocks:
        text = block.text.strip()
        if text:
            return text
    return None


def _parse_options(option_blocks: list[NormalizedOCRBlock]) -> dict[str, str]:
    options: dict[str, str] = {}
    for block in option_blocks:
        match = OPTION_RE.match(block.text)
        if match:
            options[match.group(1)] = match.group(2).strip()
            continue
        key = chr(ord("A") + len(options))
        options[key] = block.text.strip()
    return options


def _page_span(blocks: list[NormalizedOCRBlock]) -> list[int]:
    if not blocks:
        return []
    pages = sorted({block.page_no for block in blocks})
    return [pages[0], pages[-1]]


def _union_bbox(blocks: list[NormalizedOCRBlock]) -> list[float]:
    boxes = [block.bbox for block in blocks if is_valid_bbox(block.bbox)]
    if not boxes:
        return []
    xs0 = [bbox[0] for bbox in boxes]
    ys0 = [bbox[1] for bbox in boxes]
    xs1 = [bbox[2] for bbox in boxes]
    ys1 = [bbox[3] for bbox in boxes]
    return [min(xs0), min(ys0), max(xs1), max(ys1)]


def _average_confidence(blocks: list[NormalizedOCRBlock]) -> float | None:
    values = [block.confidence for block in blocks if block.confidence is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _infer_question_no(block: NormalizedOCRBlock) -> int | None:
    if block.block_type == "question_no":
        return extract_question_no(f"{block.text}.") if block.text.isdigit() else extract_question_no(block.text)
    if block.block_type in {"stem", "bbox_only"}:
        number = extract_question_no(block.text)
        if number is not None:
            return number
    provider_match = re.search(r"question:(\d{1,3})", block.provider_ref)
    if provider_match:
        return int(provider_match.group(1))
    return None


def _provider_ref_question_no(provider_ref: str) -> int | None:
    match = re.search(r"question:(\d{1,3})", provider_ref)
    if not match:
        return None
    return int(match.group(1))


def _first_question_position(blocks: list[NormalizedOCRBlock], block_positions: dict[str, int]) -> int:
    return min(block_positions[block.block_id] for block in blocks)


def _last_question_position(blocks: list[NormalizedOCRBlock], block_positions: dict[str, int]) -> int:
    return max(block_positions[block.block_id] for block in blocks)


def _contains_data_analysis_signal(*texts: str) -> bool:
    joined = "\n".join(text for text in texts if text)
    return any(token in joined for token in DATA_ANALYSIS_PATTERNS)


def _classify_question_category(shared_stem: str, local_stem: str, material_group: MaterialGroup | None) -> str:
    text = "\n".join(item for item in (shared_stem, local_stem) if item)
    if material_group or _contains_data_analysis_signal(text):
        return "资料分析"
    if any(token in text for token in ("文段", "词语", "语句", "阅读理解")):
        return "言语理解"
    if any(token in text for token in ("图形", "推理", "定义判断", "逻辑")):
        return "判断推理"
    if any(token in text for token in ("方程", "计算", "数列", "工程", "利润")):
        return "数量关系"
    if any(token in text for token in ("法律", "历史", "地理", "科技", "人文")):
        return "常识判断"
    return "未知"
