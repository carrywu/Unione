from __future__ import annotations

import logging
from typing import Any

import ai_client
from detector import PDFDetector
from extractor import PDFExtractor
from models import Material, ParseResult, ParseStats, Question, QuestionImage
from strategies.text_strategy import TextStrategy
from strategies.universal_question_strategy import UniversalQuestionStrategy
from strategies.visual_strategy import VisualStrategy
from validator import validate_and_clean


logger = logging.getLogger(__name__)

STRATEGIES = {
    "pure_text": UniversalQuestionStrategy(),
    "visual_heavy": UniversalQuestionStrategy(),
    "textbook": UniversalQuestionStrategy(),
    "exam_paper": UniversalQuestionStrategy(),
    "unknown": UniversalQuestionStrategy(),
}


async def parse_pdf(
    pdf_path: str,
    pdf_url: str | None = None,
    ai_config: dict[str, str] | None = None,
) -> ParseResult:
    """Parse PDF using type detection, strategy dispatch, validation, and fallback.

    The optional pdf_url parameter is kept for backwards compatibility with
    main.py and the NestJS service contract.
    """
    extractor = PDFExtractor(pdf_path)
    try:
        detector = PDFDetector()
        detection = detector.detect(extractor)
        pdf_type = detection.get("type", "unknown")
        logger.info("PDF 类型检测结果: %s，置信度: %s", pdf_type, detection.get("confidence"))
        logger.info("PDF 检测统计: %s", detection.get("stats"))

        with ai_client.use_config(ai_config):
            strategy = STRATEGIES.get(pdf_type, STRATEGIES["unknown"])
            raw_result = strategy.parse(extractor, ai_client)
            final_result = validate_and_clean(
                raw_result.get("questions", []),
                raw_result.get("materials", []),
            )
            strategy_name = strategy.__class__.__name__

            # UniversalQuestionStrategy is the primary text-first parser.
            # Only fall back to visual parsing when rule extraction is too sparse.
            if final_result["stats"]["total"] < 3 and extractor.total_pages <= 50:
                alternate = VisualStrategy()
                logger.warning(
                    "%s produced only %s questions; retrying with %s",
                    strategy_name,
                    final_result["stats"]["total"],
                    alternate.__class__.__name__,
                )
                alternate_raw = alternate.parse(extractor, ai_client)
                alternate_result = validate_and_clean(
                    alternate_raw.get("questions", []),
                    alternate_raw.get("materials", []),
                )
                if alternate_result["stats"]["total"] >= final_result["stats"]["total"]:
                    final_result = alternate_result
                    strategy_name = alternate.__class__.__name__

        return _to_parse_result(
            final_result,
            total_pages=extractor.total_pages,
            detection=detection,
            strategy_name=strategy_name,
        )
    finally:
        extractor.close()


def _to_parse_result(
    result: dict[str, Any],
    total_pages: int,
    detection: dict[str, Any],
    strategy_name: str,
) -> ParseResult:
    materials = [
        Material(
            id=str(material.get("temp_id") or material.get("id") or f"m{index + 1}"),
            content=material.get("content") or "",
            images=_normalize_images(material.get("images") or []),
        )
        for index, material in enumerate(result.get("materials", []))
    ]

    questions: list[Question] = []
    for fallback_index, raw_question in enumerate(result.get("questions", []), start=1):
        index = _safe_int(raw_question.get("index")) or fallback_index
        options = _normalize_options(raw_question)
        question_type = raw_question.get("type") or ("single" if options else "judge")
        if question_type == "material_sub":
            question_type = "single"

        questions.append(
            Question(
                index=index,
                type=question_type,
                content=raw_question.get("content") or "",
                options=options or None,
                answer=raw_question.get("answer"),
                analysis=raw_question.get("analysis"),
                images=_normalize_images(raw_question.get("images") or []),
                material_id=raw_question.get("material_temp_id") or raw_question.get("material_id"),
                needs_review=bool(raw_question.get("needs_review")),
                page_num=_safe_int(raw_question.get("page_num")),
                source=raw_question.get("source"),
                raw_text=raw_question.get("raw_text"),
                parse_confidence=raw_question.get("parse_confidence"),
            )
        )

    stats = result.get("stats", {})
    parse_stats = ParseStats(
        total_pages=total_pages,
        total_questions=len(questions),
        has_images=any(question.images for question in questions)
        or any(material.images for material in materials),
        needs_review_count=sum(1 for question in questions if question.needs_review),
        filtered_out=int(stats.get("filtered_out") or 0),
        with_images=int(stats.get("with_images") or 0),
        detection=detection,
        strategy=strategy_name,
    )
    return ParseResult(questions=questions, materials=materials, stats=parse_stats)


def _normalize_options(raw_question: dict[str, Any]) -> dict[str, str]:
    if isinstance(raw_question.get("options"), dict):
        return {
            str(key).upper(): str(value)
            for key, value in raw_question["options"].items()
            if value
        }

    options: dict[str, str] = {}
    for letter in ["a", "b", "c", "d"]:
        value = raw_question.get(f"option_{letter}")
        if value:
            options[letter.upper()] = str(value)
    return options


def _normalize_images(images: list[Any]) -> list[QuestionImage]:
    normalized: list[QuestionImage] = []
    for image in images:
        if isinstance(image, str):
            normalized.append(QuestionImage(base64=image))
        elif isinstance(image, dict):
            normalized.append(
                QuestionImage(
                    base64=image.get("base64") or image.get("url") or "",
                    ai_desc=image.get("ai_desc") or image.get("description"),
                )
            )
    return [image for image in normalized if image.base64]


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
