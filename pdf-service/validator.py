from __future__ import annotations

import re
from typing import Any


JUDGE_KEYWORDS = [
    "是否",
    "对错",
    "正确的是",
    "说法正确",
    "说法错误",
    "符合",
    "不符合",
    "下列说法",
    "判断正误",
]

TOC_LINE_PATTERN = re.compile(r"^.{1,60}\.{4,}\s*\d+\s*$")
HEADER_FOOTER_NOISE_RE = re.compile(r"(资料分析题库|夸夸刷|第七章)")
QUESTION_ANCHOR_RE = re.compile(r"(?:【\s*)?例\s*\d+\s*】?")
VISUAL_PLACEHOLDER_RE = re.compile(
    r"\[?\s*(?:page\s*\d+\s*)?visual\s+parse\s+(?:unavailable|failed|error)[^\]\n\r]*\]?",
    re.I,
)
UNAVAILABLE_LINE_RE = re.compile(r"^\s*\[?\s*unavailable\s*\]?\s*$", re.I)


def validate_and_clean(
    questions: list[dict[str, Any]],
    materials: list[dict[str, Any]],
) -> dict[str, Any]:
    valid_questions: list[dict[str, Any]] = []
    rejected_candidates: list[dict[str, Any]] = []
    for question in questions:
        cleaned, rejected = _clean_question_with_meta(question)
        if cleaned:
            valid_questions.append(cleaned)
        elif rejected:
            rejected_candidates.append(rejected)

    used_material_ids = {
        question.get("material_temp_id")
        for question in valid_questions
        if question.get("material_temp_id")
    }
    valid_materials = [
        material for material in materials if material.get("temp_id") in used_material_ids
    ]

    return {
        "questions": valid_questions,
        "materials": valid_materials,
        "rejected_candidates": rejected_candidates,
        "stats": {
            "total": len(valid_questions),
            "needs_review": sum(1 for q in valid_questions if q.get("needs_review")),
            "filtered_out": len(questions) - len(valid_questions),
            "with_images": sum(1 for q in valid_questions if q.get("images")),
        },
    }


def _clean_question(question: dict[str, Any]) -> dict[str, Any] | None:
    cleaned, _ = _clean_question_with_meta(question)
    return cleaned


def _clean_question_with_meta(question: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    question = dict(question)
    original_content = (question.get("content") or "").strip()
    content = (question.get("content") or "").strip()
    placeholder_filtered = _has_visual_placeholder(content) or _has_visual_placeholder(question.get("analysis"))
    content = re.sub(r"^\s*\d{1,3}[．.、]\s*", "", content)
    content = _remove_visual_placeholders(content)
    content = _strip_orphan_corner_brackets(content)

    content_too_short = len(content) < 8
    if len(content) < 4:
        return None, _rejected_candidate(question, "content_too_short", original_content)
    if TOC_LINE_PATTERN.match(content):
        return None, _rejected_candidate(question, "toc_line", original_content)
    if content.startswith("第") and len(content) < 15 and "章" in content:
        return None, _rejected_candidate(question, "chapter_heading", original_content)

    options = question.get("options") if isinstance(question.get("options"), dict) else {}
    for letter, key in [("A", "option_a"), ("B", "option_b"), ("C", "option_c"), ("D", "option_d")]:
        if not question.get(key) and options:
            question[key] = options.get(letter) or options.get(letter.lower())
        value = (question.get(key) or "").strip()
        placeholder_filtered = placeholder_filtered or _has_visual_placeholder(value)
        value = _remove_visual_placeholders(value)
        value = re.sub(r"^[ABCD][．.、。]\s*", "", value).strip()
        question[key] = value or None

    if question.get("analysis"):
        question["analysis"] = _remove_visual_placeholders(question.get("analysis"))

    has_options = any(question.get(key) for key in ["option_a", "option_b", "option_c", "option_d"])
    is_judge = any(keyword in content for keyword in JUDGE_KEYWORDS)
    is_material_sub = bool(question.get("material_temp_id"))

    if not has_options and not is_judge and not is_material_sub:
        question["needs_review"] = True

    parse_stage = question.get("parse_stage") or "question_parse"
    missing_options = not has_options and not is_judge
    material_suspected = bool(question.get("material_suspected"))
    answer_missing_in_answer_stage = parse_stage == "answer_match" and not question.get("answer")
    question["needs_review"] = bool(
        question.get("needs_review")
        or missing_options
        or content_too_short
        or material_suspected
        or answer_missing_in_answer_stage
    )
    parse_warnings = list(question.get("parse_warnings") or [])
    if placeholder_filtered:
        parse_warnings.append("placeholder_filtered")
        question["needs_review"] = True
    if HEADER_FOOTER_NOISE_RE.search(content):
        parse_warnings.append("header_footer_blacklist_hit")
        question["needs_review"] = True
    if len(QUESTION_ANCHOR_RE.findall(content)) > 1:
        parse_warnings.append("question_boundary_conflict")
        question["needs_review"] = True
    if missing_options:
        parse_warnings.append("options_missing")
    low_confidence_images = [
        image
        for image in question.get("images") or []
        if isinstance(image, dict)
        and _safe_float(image.get("assignment_confidence")) is not None
        and (_safe_float(image.get("assignment_confidence")) or 0) < 0.65
    ]
    if low_confidence_images:
        parse_warnings.append("visual_assignment_low_confidence")
        question["needs_review"] = True
    if len(question.get("images") or []) > 4:
        parse_warnings.append("abnormal_image_count")
        question["needs_review"] = True
    if parse_warnings:
        question["parse_warnings"] = sorted(set(parse_warnings))

    if is_judge and not has_options:
        question["type"] = "judge"
        question.setdefault("option_a", "对")
        question.setdefault("option_b", "错")
    elif question.get("type") not in {"single", "judge", "material_sub"}:
        question["type"] = "single"

    question["content"] = content
    return question, None


def _strip_orphan_corner_brackets(text: str) -> str:
    lines = [line for line in text.splitlines() if line.strip() not in {"【", "】"}]
    text = "\n".join(lines).strip()
    text = re.sub(r"^\s*】+", "", text).strip()
    text = re.sub(r"【+\s*$", "", text).strip()
    return text


def _has_visual_placeholder(value: Any) -> bool:
    text = str(value or "")
    return bool(VISUAL_PLACEHOLDER_RE.search(text) or UNAVAILABLE_LINE_RE.search(text))


def _remove_visual_placeholders(value: Any) -> str:
    lines = []
    for line in str(value or "").splitlines():
        cleaned = VISUAL_PLACEHOLDER_RE.sub("", line).strip()
        if not cleaned or UNAVAILABLE_LINE_RE.match(cleaned):
            continue
        lines.append(cleaned)
    return "\n".join(lines).strip()


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _rejected_candidate(question: dict[str, Any], reason: str, original_content: str) -> dict[str, Any]:
    return {
        "index": question.get("index"),
        "page_num": question.get("page_num"),
        "source": question.get("source"),
        "reason": reason,
        "content_preview": original_content[:200],
        "raw_question": question,
    }
