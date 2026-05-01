from __future__ import annotations

import logging
import os
import tempfile
from typing import Any

import ai_client
from ai_solver.enhancer import ai_solver_enabled, enhance_questions_with_ai_solver
from debug_writer import write_debug_bundle
from detector import PDFDetector
from extractor import PDFExtractor
from models import Material, ParseResult, ParseStats, Question, QuestionImage
from parser_kernel.adapter import parse_extractor_with_kernel
from parser_kernel.routing import routing_decision
from strategies.markdown_question_strategy import MarkdownQuestionStrategy
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
    preflight_routing = _preflight_routing(pdf_path, pdf_url)
    preflight_pdf_kind = preflight_routing.get("actualKind") if preflight_routing else None

    with ai_client.use_config(ai_config):
        if preflight_pdf_kind != "scanned_question_book":
            try:
                debug_dir = tempfile.mkdtemp(prefix="pdf-markdown-")
                markdown_raw = MarkdownQuestionStrategy().parse(
                    pdf_path,
                    output_dir=debug_dir,
                    ai_config=ai_config,
                )
                markdown_result = validate_and_clean(
                    markdown_raw.get("questions", []),
                    markdown_raw.get("materials", []),
                )
                _merge_debug_stats(markdown_result, markdown_raw.get("stats", {}))
                _maybe_apply_ai_solver(markdown_result)
                if markdown_result["stats"]["total"] > 0:
                    detection = {
                        "type": "markdown_layout",
                        "confidence": 0.8,
                        "stats": {
                            "debug_dir": debug_dir,
                            "extractor": markdown_raw.get("stats", {}).get("extractor"),
                        },
                    }
                    return _to_parse_result(
                        markdown_result,
                        total_pages=_safe_total_pages(pdf_path),
                        detection=detection,
                        strategy_name="MarkdownQuestionStrategy",
                    )
            except Exception as exc:
                logger.exception("MarkdownQuestionStrategy failed; falling back to legacy strategies: %s", exc)

    extractor = PDFExtractor(pdf_path)
    try:
        detector = PDFDetector()
        detection = detector.detect(extractor)
        kernel_routing = preflight_routing or _routing_for_kernel(extractor, pdf_url)
        kernel_pdf_kind = kernel_routing.get("actualKind") or _classify_for_kernel(extractor, pdf_url)
        detection.setdefault("stats", {})["kernel_pdf_kind"] = kernel_pdf_kind
        detection.setdefault("stats", {})["kernel_routing_decision"] = kernel_routing
        pdf_type = detection.get("type", "unknown")
        logger.info("PDF 类型检测结果: %s，置信度: %s", pdf_type, detection.get("confidence"))
        logger.info("PDF 检测统计: %s", detection.get("stats"))

        with ai_client.use_config(ai_config):
            if kernel_pdf_kind == "scanned_question_book":
                kernel_result = parse_extractor_with_kernel(extractor)
                final_result = validate_and_clean(
                    kernel_result.get("questions", []),
                    kernel_result.get("materials", []),
                )
                _merge_debug_stats(final_result, kernel_result.get("stats", {}))
                _maybe_apply_ai_solver(final_result)
                kernel_debug = _kernel_scanned_fallback_debug(
                    kernel_pdf_kind=kernel_pdf_kind,
                    kernel_result=kernel_result,
                    final_result=final_result,
                )
                final_result["stats"]["scanned_fallback_debug"] = kernel_debug
                if kernel_result.get("debug_dir"):
                    detection.setdefault("stats", {})["kernel_debug_dir"] = kernel_result.get("debug_dir")
                return _to_parse_result(
                    final_result,
                    total_pages=extractor.total_pages,
                    detection=detection,
                    strategy_name="ParserKernelScannedQuestionBook",
                )

            strategy = STRATEGIES.get(pdf_type, STRATEGIES["unknown"])
            raw_result = strategy.parse(extractor, ai_client)
            final_result = validate_and_clean(
                raw_result.get("questions", []),
                raw_result.get("materials", []),
            )
            primary_result = final_result
            _merge_debug_stats(
                final_result,
                {
                    "pages_count": extractor.total_pages,
                    "question_candidates_count": len(raw_result.get("questions", [])),
                    "materials_count": len(raw_result.get("materials", [])),
                    "visuals_count": _count_raw_visuals(raw_result),
                },
            )
            strategy_name = strategy.__class__.__name__
            scanned_fallback_debug = _scanned_fallback_debug(
                kernel_pdf_kind=kernel_pdf_kind,
                total_pages=extractor.total_pages,
                text_strategy_name=strategy_name,
                visual_fallback_called=False,
                visual_result=None,
            )
            alternate_raw = None
            alternate_result = None

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
                _merge_debug_stats(
                    alternate_result,
                    {
                        "pages_count": extractor.total_pages,
                        "question_candidates_count": len(alternate_raw.get("questions", [])),
                        "materials_count": len(alternate_raw.get("materials", [])),
                        "visuals_count": _count_raw_visuals(alternate_raw),
                    },
                )
                scanned_fallback_debug = _scanned_fallback_debug(
                    kernel_pdf_kind=kernel_pdf_kind,
                    total_pages=extractor.total_pages,
                    text_strategy_name=strategy_name,
                    visual_fallback_called=True,
                    visual_result=alternate_result,
                )
                if alternate_result["stats"]["total"] >= final_result["stats"]["total"]:
                    final_result = alternate_result
                    strategy_name = alternate.__class__.__name__
            elif final_result["stats"]["total"] < 3:
                scanned_fallback_debug["legacy_visual_fallback_skip_reason"] = "page_count_gt_50"
                scanned_fallback_debug["legacy_visual_fallback_page_limit"] = 50
                scanned_fallback_debug["legacy_visual_fallback_called"] = False

            _maybe_apply_ai_solver(final_result)
            final_result["stats"]["scanned_fallback_debug"] = scanned_fallback_debug
            _write_scanned_debug_artifacts(
                kernel_pdf_kind=kernel_pdf_kind,
                total_pages=extractor.total_pages,
                detection=detection,
                primary_strategy_name=strategy.__class__.__name__,
                primary_raw=raw_result,
                primary_result=primary_result,
                visual_raw=alternate_raw,
                visual_result=alternate_result,
                selected_strategy_name=strategy_name,
                final_result=final_result,
            )

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
            page_range=material.get("page_range"),
            image_refs=material.get("image_refs") or [],
            raw_text=material.get("raw_text"),
            parse_warnings=material.get("parse_warnings") or [],
        )
        for index, material in enumerate(result.get("materials", []))
    ]

    questions: list[Question] = []
    for fallback_index, raw_question in enumerate(result.get("questions", []), start=1):
        index = _safe_int(raw_question.get("index")) or fallback_index
        raw_question = _with_ai_preaudit_defaults(raw_question)
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
                page_range=raw_question.get("page_range"),
                source_page_start=_safe_int(raw_question.get("source_page_start")),
                source_page_end=_safe_int(raw_question.get("source_page_end")),
                source_bbox=raw_question.get("source_bbox"),
                source_anchor_text=raw_question.get("source_anchor_text"),
                source_confidence=raw_question.get("source_confidence"),
                image_refs=raw_question.get("image_refs") or [],
                visual_refs=raw_question.get("visual_refs") or [],
                source=raw_question.get("source"),
                raw_text=raw_question.get("raw_text"),
                parse_confidence=raw_question.get("parse_confidence"),
                parse_warnings=raw_question.get("parse_warnings") or [],
                ai_corrections=raw_question.get("ai_corrections") or [],
                ai_confidence=raw_question.get("ai_confidence"),
                ai_provider=raw_question.get("ai_provider"),
                ai_review_notes=raw_question.get("ai_review_notes"),
                ai_candidate_answer=raw_question.get("ai_candidate_answer"),
                ai_candidate_analysis=raw_question.get("ai_candidate_analysis"),
                ai_answer_confidence=raw_question.get("ai_answer_confidence"),
                ai_reasoning_summary=raw_question.get("ai_reasoning_summary"),
                ai_knowledge_points=raw_question.get("ai_knowledge_points") or [],
                ai_risk_flags=raw_question.get("ai_risk_flags") or [],
                ai_solver_provider=raw_question.get("ai_solver_provider"),
                ai_solver_model=raw_question.get("ai_solver_model"),
                ai_solver_first_model=raw_question.get("ai_solver_first_model"),
                ai_solver_final_model=raw_question.get("ai_solver_final_model"),
                ai_solver_rechecked=raw_question.get("ai_solver_rechecked"),
                ai_solver_recheck_reason=raw_question.get("ai_solver_recheck_reason"),
                ai_solver_recheck_result=raw_question.get("ai_solver_recheck_result"),
                ai_solver_created_at=raw_question.get("ai_solver_created_at"),
                ai_answer_conflict=raw_question.get("ai_answer_conflict"),
                visual_summary=raw_question.get("visual_summary"),
                visual_confidence=raw_question.get("visual_confidence"),
                visual_parse_status=raw_question.get("visual_parse_status"),
                visual_error=raw_question.get("visual_error"),
                visual_risk_flags=raw_question.get("visual_risk_flags") or [],
                has_visual_context=raw_question.get("has_visual_context"),
                answer_unknown_reason=raw_question.get("answer_unknown_reason"),
                analysis_unknown_reason=raw_question.get("analysis_unknown_reason"),
                ai_audit_status=raw_question.get("ai_audit_status"),
                ai_audit_verdict=raw_question.get("ai_audit_verdict"),
                ai_audit_summary=raw_question.get("ai_audit_summary"),
                ai_can_understand_question=raw_question.get("ai_can_understand_question"),
                ai_can_solve_question=raw_question.get("ai_can_solve_question"),
                ai_reviewed_before_human=raw_question.get("ai_reviewed_before_human"),
                ai_review_error=raw_question.get("ai_review_error"),
                question_quality=raw_question.get("question_quality"),
            )
        )

    stats = result.get("stats", {})
    debug_counts = _debug_counts(stats, total_pages, len(result.get("questions", [])), len(materials))
    warnings = [str(item) for item in stats.get("warnings") or []]
    suspected_bad_parse = bool(stats.get("suspected_bad_parse")) or len(questions) == 0
    if len(questions) == 0 and "zero_questions_extracted" not in warnings:
        warnings.append("zero_questions_extracted")
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
        suspected_bad_parse=suspected_bad_parse,
        warnings=warnings,
        debug_counts=debug_counts,
        scanned_fallback_debug=stats.get("scanned_fallback_debug"),
    )
    return ParseResult(questions=questions, materials=materials, stats=parse_stats)


def _merge_debug_stats(result: dict[str, Any], debug_stats: dict[str, Any]) -> None:
    stats = result.setdefault("stats", {})
    for key, value in debug_stats.items():
        if value is not None:
            stats[key] = value
    accepted = int(stats.get("total") or 0)
    candidates = int(stats.get("question_candidates_count") or accepted + int(stats.get("filtered_out") or 0))
    stats["accepted_questions_count"] = accepted
    stats["question_candidates_count"] = candidates
    stats["rejected_questions_count"] = max(0, candidates - accepted)


def _maybe_apply_ai_solver(result: dict[str, Any]) -> None:
    if not ai_solver_enabled():
        return
    enhancement = enhance_questions_with_ai_solver(
        questions=result.get("questions", []),
        materials=result.get("materials", []),
    )
    result["questions"] = enhancement.questions
    stats = result.setdefault("stats", {})
    stats["ai_solver"] = enhancement.stats
    stats["needs_review"] = sum(1 for question in enhancement.questions if question.get("needs_review"))
    if enhancement.stats.get("warnings"):
        warnings = [str(item) for item in stats.get("warnings") or []]
        for warning in enhancement.stats["warnings"]:
            if warning not in warnings:
                warnings.append(str(warning))
        stats["warnings"] = warnings


def _debug_counts(
    stats: dict[str, Any],
    total_pages: int,
    accepted_questions: int,
    materials_count: int,
) -> dict[str, int]:
    candidates = _safe_int(stats.get("question_candidates_count"))
    if candidates is None:
        candidates = accepted_questions + int(stats.get("filtered_out") or 0)
    return {
        "pages_count": int(stats.get("pages_count") or total_pages or 0),
        "page_elements_count": int(stats.get("page_elements_count") or 0),
        "question_candidates_count": int(candidates or 0),
        "accepted_questions_count": int(stats.get("accepted_questions_count") or accepted_questions or 0),
        "rejected_questions_count": int(stats.get("rejected_questions_count") or max(0, candidates - accepted_questions)),
        "materials_count": int(stats.get("materials_count") or materials_count or 0),
        "visuals_count": int(stats.get("visuals_count") or 0),
    }


def _classify_for_kernel(extractor: PDFExtractor, pdf_url: str | None) -> str:
    return _routing_for_kernel(extractor, pdf_url).get("actualKind") or "unknown"


def _routing_for_kernel(extractor: PDFExtractor, pdf_url: str | None) -> dict[str, Any]:
    total_pages = getattr(extractor, "total_pages", 0)
    sample_pages = min(total_pages, 20)
    text_lengths = [
        len((extractor.get_page_text(page_index) or "").strip())
        for page_index in range(sample_pages)
    ]
    file_name = os.path.basename(pdf_url or getattr(extractor, "pdf_path", "") or "")
    return routing_decision(file_name=file_name, total_pages=total_pages, text_lengths=text_lengths)


def _preflight_routing(pdf_path: str, pdf_url: str | None) -> dict[str, Any] | None:
    extractor = None
    try:
        extractor = PDFExtractor(pdf_path)
        return _routing_for_kernel(extractor, pdf_url)
    except Exception as exc:
        logger.warning("PDF preflight classification failed; continuing with normal parse: %s", exc)
        return None
    finally:
        if extractor is not None:
            extractor.close()


def _scanned_fallback_debug(
    *,
    kernel_pdf_kind: str,
    total_pages: int,
    text_strategy_name: str,
    visual_fallback_called: bool,
    visual_result: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if kernel_pdf_kind != "scanned_question_book":
        return None
    visual_stats = visual_result.get("stats", {}) if visual_result else {}
    return {
        "pdf_kind": kernel_pdf_kind,
        "kernel_visual_fallback_called": False,
        "legacy_text_strategy": text_strategy_name,
        "legacy_visual_fallback_called": visual_fallback_called,
        "legacy_visual_fallback_questions": int(visual_stats.get("total") or 0),
        "pages_count": total_pages,
    }


def _kernel_scanned_fallback_debug(
    *,
    kernel_pdf_kind: str,
    kernel_result: dict[str, Any],
    final_result: dict[str, Any],
) -> dict[str, Any]:
    stats = kernel_result.get("stats") or {}
    return {
        "pdf_kind": kernel_pdf_kind,
        "kernel_visual_fallback_called": True,
        "kernel_questions": len(kernel_result.get("questions") or []),
        "kernel_accepted_questions": int(final_result.get("stats", {}).get("total") or 0),
        "kernel_rejected_questions": len(final_result.get("rejected_candidates") or []),
        "kernel_debug_dir": kernel_result.get("debug_dir") or stats.get("debug_dir"),
        "vision_ai": stats.get("vision_ai") or {},
        "legacy_text_strategy": None,
        "legacy_visual_fallback_called": False,
        "legacy_visual_fallback_questions": 0,
    }


def _write_scanned_debug_artifacts(
    *,
    kernel_pdf_kind: str,
    total_pages: int,
    detection: dict[str, Any],
    primary_strategy_name: str,
    primary_raw: dict[str, Any],
    primary_result: dict[str, Any],
    visual_raw: dict[str, Any] | None,
    visual_result: dict[str, Any] | None,
    selected_strategy_name: str,
    final_result: dict[str, Any],
) -> None:
    if kernel_pdf_kind != "scanned_question_book":
        return

    debug_dir = tempfile.mkdtemp(prefix="pdf-scanned-debug-")
    final_result.setdefault("stats", {})
    scanned_debug = final_result["stats"].setdefault("scanned_fallback_debug", {})
    scanned_debug["debug_dir"] = debug_dir

    raw_model_response = (visual_raw or {}).get("stats", {}).get("raw_model_response") or []
    rejected_candidates = {
        "final": final_result.get("rejected_candidates") or [],
        "primary_strategy": primary_result.get("rejected_candidates") or [],
        "visual_fallback": (visual_result or {}).get("rejected_candidates") or [],
    }
    page_parse_summary = {
        "detector": detection,
        "kernel_pdf_kind": kernel_pdf_kind,
        "total_pages": total_pages,
        "primary_strategy": {
            "name": primary_strategy_name,
            "question_candidates_count": len(primary_raw.get("questions", [])),
            "accepted_questions_count": int(primary_result.get("stats", {}).get("total") or 0),
            "rejected_questions_count": len(primary_result.get("rejected_candidates") or []),
        },
        "visual_fallback": {
            "called": visual_raw is not None,
            "strategy": "VisualStrategy" if visual_raw is not None else None,
            "question_candidates_count": len((visual_raw or {}).get("questions", []) or []),
            "accepted_questions_count": int((visual_result or {}).get("stats", {}).get("total") or 0),
            "rejected_questions_count": len((visual_result or {}).get("rejected_candidates") or []),
            "pages": (visual_raw or {}).get("stats", {}).get("page_parse_summary") or [],
        },
        "validator": {
            "filtered_out": int(final_result.get("stats", {}).get("filtered_out") or 0),
            "final_accepted_questions_count": int(final_result.get("stats", {}).get("total") or 0),
            "final_rejected_candidates_count": len(final_result.get("rejected_candidates") or []),
            "parse_quality_filter_active": False,
        },
        "adapter": {
            "selected_strategy": selected_strategy_name,
            "selected_raw_question_count": len(((visual_raw if selected_strategy_name == "VisualStrategy" else primary_raw) or {}).get("questions", []) or []),
            "drops_in_adapter": 0,
            "note": "adapter does not reject candidates by missing options or materials; validator decides final filtering",
        },
        "parser_kernel": {
            "used_in_primary_parse": False,
            "question_candidates_count": 0,
            "accepted_questions_count": 0,
            "rejected_questions_count": 0,
            "note": "scanned_question_book main path is still detector + legacy strategies + validator; parser_kernel is not the primary acceptance gate here",
        },
    }

    write_debug_bundle(
        debug_dir,
        raw_model_response=raw_model_response,
        rejected_candidates=rejected_candidates,
        page_parse_summary=page_parse_summary,
    )


def _count_raw_visuals(raw_result: dict[str, Any]) -> int:
    visuals = raw_result.get("visuals")
    if isinstance(visuals, list):
        return len(visuals)
    return sum(len(item.get("images") or []) for item in raw_result.get("questions", []))


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
                    base64=image.get("base64") or "",
                    url=image.get("url"),
                    ref=image.get("ref"),
                    caption=image.get("caption"),
                    page=_safe_int(image.get("page")),
                    role=image.get("role"),
                    image_role=image.get("image_role"),
                    image_order=_safe_int(image.get("image_order")),
                    insert_position=image.get("insert_position"),
                    bbox=image.get("bbox"),
                    raw_bbox=image.get("raw_bbox"),
                    expanded_bbox=image.get("expanded_bbox"),
                    absorbed_texts=image.get("absorbed_texts") or [],
                    same_visual_group_id=image.get("same_visual_group_id"),
                    child_visual_ids=image.get("child_visual_ids") or [],
                    assignment_confidence=image.get("assignment_confidence"),
                    ai_desc=image.get("ai_desc") or image.get("description"),
                    visual_parse_status=image.get("visual_parse_status"),
                    visual_summary=image.get("visual_summary"),
                    visual_confidence=image.get("visual_confidence"),
                    visual_error=image.get("visual_error"),
                    belongs_to_question=image.get("belongs_to_question"),
                    linked_question_no=_safe_int(image.get("linked_question_no")),
                    linked_question_id=image.get("linked_question_id"),
                    linked_by=image.get("linked_by"),
                    link_reason=image.get("link_reason"),
                )
            )
    return [image for image in normalized if image.base64 or image.url]


def _with_ai_preaudit_defaults(raw_question: dict[str, Any]) -> dict[str, Any]:
    question = dict(raw_question)
    has_visual = bool(question.get("images") or question.get("visual_refs") or question.get("image_refs"))
    risk_flags = [str(item) for item in question.get("ai_risk_flags") or [] if str(item)]

    if has_visual and not question.get("visual_parse_status"):
        visual_summaries: list[str] = []
        visual_errors: list[str] = []
        visual_confidences: list[float] = []
        for image in question.get("images") or []:
            if not isinstance(image, dict):
                continue
            if image.get("visual_summary"):
                visual_summaries.append(str(image["visual_summary"]))
            elif image.get("ai_desc") or image.get("caption"):
                visual_summaries.append(str(image.get("ai_desc") or image.get("caption")))
            if image.get("visual_error"):
                visual_errors.append(str(image["visual_error"]))
            confidence = _safe_float(image.get("visual_confidence") or image.get("assignment_confidence"))
            if confidence is not None:
                visual_confidences.append(confidence)
        if visual_summaries:
            question["visual_parse_status"] = "partial"
            question.setdefault("visual_summary", "\n".join(_dedupe(visual_summaries)))
        else:
            question["visual_parse_status"] = "failed"
            question.setdefault("visual_error", "视觉解析未返回结构化图表摘要")
            risk_flags.append("视觉解析失败，需人工复核")
        if visual_errors:
            question["visual_error"] = "\n".join(_dedupe(visual_errors))
        if visual_confidences:
            question["visual_confidence"] = max(visual_confidences)
    elif not has_visual:
        question.setdefault("visual_parse_status", "skipped")

    has_answer = bool(question.get("ai_candidate_answer"))
    has_analysis = bool(question.get("ai_candidate_analysis"))
    has_audit = bool(question.get("ai_audit_status"))
    answer_confidence = _safe_float(question.get("ai_answer_confidence"))
    if not has_audit:
        if has_answer or has_analysis:
            warning = bool(risk_flags or (answer_confidence is not None and answer_confidence < 0.7))
            question["ai_audit_status"] = "warning" if warning else "passed"
            question["ai_audit_verdict"] = "需复核" if warning else "可通过"
            question["ai_audit_summary"] = question.get("ai_reasoning_summary") or "AI 已在入库前生成答案/解析建议。"
            question["ai_can_understand_question"] = True
            question["ai_can_solve_question"] = has_answer and has_analysis
            question["ai_reviewed_before_human"] = True
            if warning:
                question["needs_review"] = True
        else:
            question["ai_audit_status"] = "failed" if has_visual else "skipped"
            question["ai_audit_verdict"] = "需复核"
            question["ai_audit_summary"] = "AI 预审核未生成答案或解析建议，需人工复核。"
            question["ai_can_understand_question"] = False
            question["ai_can_solve_question"] = False
            question["ai_reviewed_before_human"] = True
            question["answer_unknown_reason"] = question.get("answer_unknown_reason") or "AI 暂无法给出答案，需复核"
            question["analysis_unknown_reason"] = question.get("analysis_unknown_reason") or "AI 暂无法生成解析，需复核"
            question["needs_review"] = True
            risk_flags.append("AI 预审核未完成，需人工复核")

    if "question_quality" not in question or not isinstance(question.get("question_quality"), dict):
        options = _normalize_options(question)
        question["question_quality"] = {
            "stem_complete": bool(str(question.get("content") or "").strip()),
            "options_complete": len(options) >= 2,
            "visual_context_complete": not has_visual or question.get("visual_parse_status") in {"success", "partial"},
            "answer_derivable": bool(question.get("ai_candidate_answer")),
            "analysis_derivable": bool(question.get("ai_candidate_analysis")),
            "duplicate_suspected": False,
            "needs_review": bool(question.get("needs_review")),
            "review_reasons": _dedupe(risk_flags),
        }
    question["has_visual_context"] = has_visual
    question["ai_risk_flags"] = _dedupe(risk_flags)
    if question.get("ai_risk_flags") and "ai_preaudit_needs_review" not in (question.get("parse_warnings") or []):
        question["parse_warnings"] = _dedupe([*(question.get("parse_warnings") or []), "ai_preaudit_needs_review"])
    return question


def _dedupe(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_total_pages(pdf_path: str) -> int:
    try:
        import fitz

        doc = fitz.open(pdf_path)
        try:
            return len(doc)
        finally:
            doc.close()
    except Exception:
        return 0
