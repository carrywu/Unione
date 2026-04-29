from __future__ import annotations

import os

import ai_client
from answer_models import AnswerBookMode, AnswerBookParseResult
from extractor import PDFExtractor
from parser_kernel.routing import classify_pdf_kind
from strategies.answer_image_strategy import ImageAnswerStrategy
from strategies.answer_text_strategy import TextAnswerStrategy


def parse_answer_book(
    pdf_path: str,
    mode: AnswerBookMode = "auto",
    ai_config: dict[str, str] | None = None,
) -> AnswerBookParseResult:
    extractor = PDFExtractor(pdf_path)
    try:
        with ai_client.use_config(ai_config):
            resolved_mode = detect_answer_book_mode(extractor) if mode == "auto" else mode
            strategy = TextAnswerStrategy() if resolved_mode == "text" else ImageAnswerStrategy()
            candidates = strategy.parse(extractor)
        return AnswerBookParseResult(
            mode=resolved_mode,
            candidates=candidates,
            stats={
                "total_pages": extractor.total_pages,
                "total_candidates": len(candidates),
                "avg_confidence": round(
                    sum(item.confidence for item in candidates) / len(candidates), 1
                )
                if candidates
                else 0,
            },
        )
    finally:
        extractor.close()


def detect_answer_book_mode(extractor: PDFExtractor) -> str:
    file_name = os.path.basename(getattr(extractor, "pdf_path", "") or "")
    total_chars = 0
    keyword_hits = 0
    image_pages = 0
    keywords = ("答案", "解析", "参考答案")
    text_lengths: list[int] = []
    for page_num in range(extractor.total_pages):
        text = extractor.get_page_text(page_num)
        stripped = text.strip()
        text_len = len(stripped)
        text_lengths.append(text_len)
        total_chars += text_len
        keyword_hits += sum(text.count(keyword) for keyword in keywords)
        if extractor.get_page_images(page_num):
            image_pages += 1

    pdf_kind = classify_pdf_kind(file_name, extractor.total_pages, text_lengths)
    if pdf_kind in {"scanned_answer_book", "answer_note"}:
        return "image"

    image_ratio = image_pages / extractor.total_pages if extractor.total_pages else 0
    if keyword_hits > 20 and total_chars > 5000:
        return "text"
    if image_ratio > 0.5 or total_chars < 1000:
        return "image"
    return "image"
