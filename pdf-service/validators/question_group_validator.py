from __future__ import annotations

import re
from typing import Any

TEACHING_TEXT_RE = re.compile(r"(考法[一二三四五六七八九十\d]+|问法[一二三四五六七八九十\d]+|专项讲解|思路点拨|知识点|核心提示|方法技巧|易错点)")
QUESTION_ANCHOR_RE = re.compile(r"^\s*(?:(?:【\s*)?例\s*\d+\s*】?|第\s*\d+\s*题|\d{1,3}(?:[．、]|[.](?!\d))|[（(]\d{1,3}[）)])")
VISUAL_REQUIRED_RE = re.compile(r"(根据.*?(资料|图|表)|上图|上表|下图|下表|图中|表中)")


def validate_parse_result(materials: list[dict[str, Any]], questions: list[dict[str, Any]], visuals: list[Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    warnings: dict[str, list[dict[str, Any]]] = {"question": [], "material": [], "visual": []}
    material_ids = {material.get("temp_id") or material.get("id") for material in materials}
    visual_ids = {getattr(visual, "id", None) for visual in visuals}
    seen_indexes: set[int] = set()

    for question in questions:
        question_warnings = list(question.get("parse_warnings") or [])
        index = question.get("index")
        if index in seen_indexes:
            question_warnings.append("duplicate_question_index")
        if index is not None:
            seen_indexes.add(index)
        options = question.get("options") or {}
        if question.get("type") == "single" and len(options) < 4:
            question_warnings.append("options_incomplete")
        if not question.get("content"):
            question_warnings.append("content_empty")
        material_id = question.get("material_id")
        if material_id and material_id not in material_ids:
            question_warnings.append("material_missing")
        for image_ref in question.get("image_refs") or []:
            if image_ref not in visual_ids:
                question_warnings.append("image_ref_missing")
        if not question.get("raw_text"):
            question_warnings.append("raw_text_empty")
        raw_text = question.get("raw_text") or ""
        if len([line for line in raw_text.splitlines() if QUESTION_ANCHOR_RE.match(line.strip())]) > 1:
            question_warnings.append("multiple_question_anchors")
        if TEACHING_TEXT_RE.search(raw_text):
            question_warnings.append("teaching_text_mixed")
        page_num = question.get("page_num")
        page_range = question.get("page_range") or []
        if page_num and page_range and not (page_range[0] <= page_num <= page_range[-1]):
            question_warnings.append("page_range_mismatch")
        content = question.get("content") or ""
        if VISUAL_REQUIRED_RE.search(content) and not question.get("image_refs") and not material_id:
            question_warnings.append("visual_hint_without_image")
        question["parse_confidence"] = _score_confidence(question, question_warnings)
        question["confidence"] = question["parse_confidence"]
        if question["parse_confidence"] < 0.85:
            question["needs_review"] = True
        if question_warnings:
            question["parse_warnings"] = sorted(set(question_warnings))
            question["needs_review"] = True
            warnings["question"].append({"index": index, "warnings": question["parse_warnings"]})

    for visual in visuals:
        if getattr(visual, "warnings", None):
            warnings["visual"].append({"visual_id": visual.id, "warnings": visual.warnings})

    return materials, questions, warnings


def _score_confidence(question: dict[str, Any], warnings: list[str]) -> float:
    options = question.get("options") or {}
    content = (question.get("content") or "").strip()
    score = 0.0
    score += 0.2 if question.get("index") is not None else 0.0
    score += 0.2 if len(content) >= 12 else 0.08
    if question.get("type") == "single":
        score += 0.2 if len(options) >= 4 else 0.1 if len(options) >= 2 else 0.0
    else:
        score += 0.2 if question.get("answer") in ("对", "错", "正确", "错误") else 0.1
    if not VISUAL_REQUIRED_RE.search(content) or question.get("image_refs") or question.get("material_id"):
        score += 0.2
    if question.get("source_bbox") or question.get("page_num"):
        score += 0.1
    if not warnings:
        score += 0.1

    unique_warnings = set(warnings)
    if "multiple_question_anchors" in unique_warnings:
        score = min(score, 0.4)
    if "options_incomplete" in unique_warnings:
        score = min(score, 0.6)
    if "teaching_text_mixed" in unique_warnings:
        score = min(score, 0.7)
    if "visual_hint_without_image" in unique_warnings or "material_or_visual_missing" in unique_warnings:
        score = min(score, 0.65)
    page_range = question.get("page_range") or []
    if len(page_range) >= 2 and page_range[-1] - page_range[0] > 1:
        score = min(score, 0.6)
    score -= min(0.2, 0.04 * len(unique_warnings))
    return max(0.0, min(1.0, round(score, 2)))
