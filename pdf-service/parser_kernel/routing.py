from __future__ import annotations

from typing import Any


REVIEW_NOTE_HINTS = (
    "复盘笔记",
    "讲义复盘",
    "下册完结",
)
SCANNED_ANSWER_BOOK_HINTS = ("解析篇",)
SCANNED_QUESTION_BOOK_HINTS = ("题本篇",)


def filename_hint(file_name: str) -> str:
    normalized = file_name.strip()
    if any(hint in normalized for hint in REVIEW_NOTE_HINTS):
        return "textbook_hint"
    if any(hint in normalized for hint in SCANNED_ANSWER_BOOK_HINTS):
        return "answer_book_hint"
    if any(hint in normalized for hint in SCANNED_QUESTION_BOOK_HINTS):
        return "scanned_question_book_hint"
    return "unknown"


def should_use_question_book_kernel(file_name: str) -> bool:
    normalized = file_name.strip()
    return not any(hint in normalized for hint in REVIEW_NOTE_HINTS)


def build_page_reality_evidence(
    *,
    file_name: str,
    total_pages: int,
    text_lengths: list[int],
    page_reality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sampled_pages = max(len(text_lengths), 1)
    total_text = sum(text_lengths)
    avg_text = total_text / sampled_pages
    text_density = avg_text / 1200.0
    has_text_layer = total_text >= max(80, sampled_pages * 20)
    sparse_text = total_pages > 0 and total_text < max(80, sampled_pages * 10)
    page_reality = page_reality or {}
    return {
        "filenameHint": filename_hint(file_name),
        "hasTextLayer": has_text_layer,
        "textDensity": round(text_density, 4),
        "imageCoverage": 1.0 if sparse_text else 0.2,
        "questionLikeScore": float(page_reality.get("questionLikeScore") or (0.7 if sparse_text else 0.55)),
        "optionLikeScore": float(page_reality.get("optionLikeScore") or 0.0),
        "tableLikeScore": float(page_reality.get("tableLikeScore") or 0.0),
        "chartLikeScore": float(page_reality.get("chartLikeScore") or 0.0),
        "tocLikeScore": float(page_reality.get("tocLikeScore") or 0.0),
        "blankPageScore": float(page_reality.get("blankPageScore") or 0.0),
        "sparseText": sparse_text,
    }


def classify_pdf_kind(
    file_name: str,
    total_pages: int,
    text_lengths: list[int],
    page_reality: dict[str, Any] | None = None,
) -> str:
    normalized = file_name.strip()
    evidence = build_page_reality_evidence(
        file_name=file_name,
        total_pages=total_pages,
        text_lengths=text_lengths,
        page_reality=page_reality,
    )
    if any(hint in normalized for hint in REVIEW_NOTE_HINTS):
        return "answer_note"
    if any(hint in normalized for hint in SCANNED_ANSWER_BOOK_HINTS):
        return "scanned_answer_book" if evidence["sparseText"] else "answer_note"
    if evidence["blankPageScore"] >= 0.85:
        return "unknown"
    if evidence["tocLikeScore"] >= 0.75 and evidence["questionLikeScore"] < 0.55:
        return "unknown"
    if not evidence["hasTextLayer"] and evidence["questionLikeScore"] >= 0.5:
        return "scanned_question_book"
    if evidence["hasTextLayer"] and evidence["questionLikeScore"] >= 0.5:
        if max(evidence["tableLikeScore"], evidence["chartLikeScore"]) >= 0.35:
            return "hybrid_question_book"
        return "text_layer_book"
    if evidence["sparseText"]:
        return "scanned_question_book"
    return "unknown"


def routing_decision(
    file_name: str,
    total_pages: int,
    text_lengths: list[int],
    page_reality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence = build_page_reality_evidence(
        file_name=file_name,
        total_pages=total_pages,
        text_lengths=text_lengths,
        page_reality=page_reality,
    )
    actual_kind = classify_pdf_kind(
        file_name=file_name,
        total_pages=total_pages,
        text_lengths=text_lengths,
        page_reality=page_reality,
    )
    if actual_kind == "scanned_question_book":
        strategy = "scanned_kernel"
    elif actual_kind == "hybrid_question_book":
        strategy = "hybrid"
    elif actual_kind in {"text_layer_book", "answer_note"}:
        strategy = "text_first"
    elif actual_kind in {"scanned_answer_book"}:
        strategy = "scanned_kernel"
    elif evidence["blankPageScore"] >= 0.85 or evidence["tocLikeScore"] >= 0.75:
        strategy = "skip_page"
    else:
        strategy = "needs_manual_route"
    return {
        "filenameHint": evidence["filenameHint"],
        "pageRealityEvidence": evidence,
        "actualKind": actual_kind,
        "recommendedStrategy": strategy,
        "reason": "filename is a hint only; actual kind is based on text density and page reality evidence",
    }
