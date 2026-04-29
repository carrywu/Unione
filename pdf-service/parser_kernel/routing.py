from __future__ import annotations


REVIEW_NOTE_HINTS = (
    "复盘笔记",
    "讲义复盘",
    "下册完结",
)
SCANNED_ANSWER_BOOK_HINTS = ("解析篇",)
SCANNED_QUESTION_BOOK_HINTS = ("题本篇",)


def should_use_question_book_kernel(file_name: str) -> bool:
    normalized = file_name.strip()
    return not any(hint in normalized for hint in REVIEW_NOTE_HINTS)


def classify_pdf_kind(file_name: str, total_pages: int, text_lengths: list[int]) -> str:
    normalized = file_name.strip()
    total_text = sum(text_lengths)
    sparse_text = total_pages > 0 and total_text < max(80, total_pages * 10)
    if any(hint in normalized for hint in REVIEW_NOTE_HINTS):
        return "answer_note"
    if any(hint in normalized for hint in SCANNED_ANSWER_BOOK_HINTS):
        return "scanned_answer_book"
    if any(hint in normalized for hint in SCANNED_QUESTION_BOOK_HINTS):
        return "scanned_question_book"
    if sparse_text:
        return "scanned_question_book"
    return "text_layer_book"
