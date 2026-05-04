from __future__ import annotations

import re
from typing import Any, Iterable

from commercial_ocr.types import NormalizedOCRBlock, ProviderPageResult


CONTENT_BLOCK_TYPES = {"stem", "option", "answer", "analysis"}
QUESTION_NO_RE = re.compile(r"^\s*(\d{1,3})\s*[.．、]")
OPTION_RE = re.compile(r"^\s*([A-H])[.．、:：)]\s*(.+)$")
SENSITIVE_KEYS = {"image", "imagebase64", "base64", "access_token", "secret", "secretid", "secretkey", "api_key"}


def normalize_baidu_page_result(
    *,
    page_no: int,
    response_json: dict[str, Any],
    provider_name: str = "baidu_paper_cut_edu",
) -> ProviderPageResult:
    blocks: list[NormalizedOCRBlock] = []
    figures: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    reading_order = 1
    for question_index, item in enumerate(response_json.get("qus_result") or [], start=1):
        question_ref = str(item.get("question_id") or item.get("qus_id") or question_index)
        question_bbox = coerce_bbox(item.get("qus_location"))
        confidence = safe_float(item.get("qus_probability") or item.get("probability"))
        element_items = item.get("qus_element") or []
        if isinstance(element_items, list) and element_items:
            for element_index, element in enumerate(element_items, start=1):
                normalized_blocks = _normalize_baidu_question_element(
                    page_no=page_no,
                    provider_name=provider_name,
                    question_ref=question_ref,
                    element=element,
                    fallback_bbox=question_bbox,
                    fallback_confidence=confidence,
                    reading_order_start=reading_order,
                )
                blocks.extend(normalized_blocks)
                reading_order += max(1, len(normalized_blocks))
        else:
            reading_order = _append_baidu_question_summary_blocks(
                page_no=page_no,
                provider_name=provider_name,
                question_ref=question_ref,
                item=item,
                blocks=blocks,
                fallback_bbox=question_bbox,
                fallback_confidence=confidence,
                reading_order=reading_order,
            )

        for figure_index, page_figure in enumerate(item.get("qus_figure") or [], start=1):
            figure_bbox = coerce_bbox(page_figure)
            if not figure_bbox:
                continue
            block = build_normalized_block(
                block_id=f"{provider_name}-{page_no}-{question_ref}-figure-{figure_index}",
                provider_ref=f"{provider_name}:question:{question_ref}",
                page_no=page_no,
                text=str(item.get("figure_caption") or ""),
                bbox=figure_bbox,
                block_type="figure",
                confidence=confidence,
                reading_order=reading_order,
                raw={"question_ref": question_ref, "raw_kind": "qus_figure"},
            )
            reading_order += 1
            blocks.append(block)
            figures.append({"bbox": figure_bbox, "question_ref": question_ref})

    return ProviderPageResult(
        page_no=page_no,
        blocks=sort_blocks(blocks),
        figures=figures,
        tables=tables,
        raw=sanitize_raw_payload({"log_id": response_json.get("log_id"), "qus_result_num": response_json.get("qus_result_num")}),
        warnings=warnings_from_baidu_response(response_json),
    )


def normalize_tencent_question_split_response(
    *,
    page_no: int,
    response_json: dict[str, Any],
    provider_name: str = "tencent_question_split",
    layout_only: bool = False,
) -> ProviderPageResult:
    payload = response_json.get("Response") if isinstance(response_json.get("Response"), dict) else response_json
    question_infos = payload.get("QuestionInfo") or []
    blocks: list[NormalizedOCRBlock] = []
    figures: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    warnings: list[str] = []
    reading_order = 1

    for info_index, info in enumerate(question_infos, start=1):
        result_list = info.get("ResultList") or []
        for result_index, result in enumerate(result_list, start=1):
            question_index = int(result.get("Index") or result_index)
            question_ref = str(result.get("QuestionNo") or result.get("QuestionId") or question_index)
            question_bbox = coerce_bbox(result.get("Coord"))
            question_text = str(result.get("Text") or "").strip()
            question_block_type = "bbox_only" if layout_only else _guess_question_block_type(question_text, result.get("GroupType"))
            root_block_id = f"{provider_name}-{page_no}-{question_ref}-root"

            question_no = extract_question_no(question_text)
            if question_no is not None:
                blocks.append(
                    build_normalized_block(
                        block_id=f"{provider_name}-{page_no}-{question_ref}-question-no",
                        provider_ref=f"{provider_name}:question:{question_ref}",
                        page_no=page_no,
                        text=str(question_no),
                        bbox=question_bbox,
                        block_type="question_no",
                        confidence=None,
                        reading_order=reading_order,
                        raw={"question_ref": question_ref, "result_index": question_index},
                    )
                )
                reading_order += 1

            if question_text or question_bbox:
                blocks.append(
                    build_normalized_block(
                        block_id=root_block_id,
                        provider_ref=f"{provider_name}:question:{question_ref}",
                        page_no=page_no,
                        text=question_text,
                        bbox=question_bbox,
                        block_type=question_block_type,
                        confidence=None,
                        reading_order=reading_order,
                        raw={
                            "question_ref": question_ref,
                            "group_type": result.get("GroupType"),
                            "layout_only": layout_only,
                        },
                        warnings=["layout_only_block"] if layout_only else None,
                    )
                )
                reading_order += 1

            if layout_only:
                _append_tencent_visual_blocks(
                    provider_name=provider_name,
                    page_no=page_no,
                    question_ref=question_ref,
                    root_block_id=root_block_id,
                    reading_order_start=reading_order,
                    result=result,
                    blocks=blocks,
                    figures=figures,
                    tables=tables,
                )
                reading_order += _count_visual_items(result)
                continue

            for option_index, option in enumerate(result.get("Option") or [], start=1):
                option_text = str(option.get("Text") or "").strip()
                blocks.append(
                    build_normalized_block(
                        block_id=f"{provider_name}-{page_no}-{question_ref}-option-{option_index}",
                        provider_ref=f"{provider_name}:question:{question_ref}",
                        page_no=page_no,
                        text=option_text,
                        bbox=coerce_bbox(option.get("Coord")) or question_bbox,
                        block_type="option",
                        confidence=None,
                        reading_order=reading_order,
                        parent_block_id=root_block_id,
                        raw={"question_ref": question_ref, "option_index": option_index},
                    )
                )
                reading_order += 1

            for answer_index, answer in enumerate(result.get("Answer") or [], start=1):
                answer_text = _extract_tencent_text(answer)
                if not answer_text:
                    continue
                blocks.append(
                    build_normalized_block(
                        block_id=f"{provider_name}-{page_no}-{question_ref}-answer-{answer_index}",
                        provider_ref=f"{provider_name}:question:{question_ref}",
                        page_no=page_no,
                        text=answer_text,
                        bbox=coerce_bbox(answer.get("Coord") if isinstance(answer, dict) else None) or question_bbox,
                        block_type="answer",
                        confidence=None,
                        reading_order=reading_order,
                        parent_block_id=root_block_id,
                        raw={"question_ref": question_ref, "answer_index": answer_index},
                    )
                )
                reading_order += 1

            analysis_text = _extract_tencent_text(result.get("Analysis"))
            if analysis_text:
                blocks.append(
                    build_normalized_block(
                        block_id=f"{provider_name}-{page_no}-{question_ref}-analysis",
                        provider_ref=f"{provider_name}:question:{question_ref}",
                        page_no=page_no,
                        text=analysis_text,
                        bbox=question_bbox,
                        block_type="analysis",
                        confidence=None,
                        reading_order=reading_order,
                        parent_block_id=root_block_id,
                        raw={"question_ref": question_ref},
                    )
                )
                reading_order += 1

            _append_tencent_visual_blocks(
                provider_name=provider_name,
                page_no=page_no,
                question_ref=question_ref,
                root_block_id=root_block_id,
                reading_order_start=reading_order,
                result=result,
                blocks=blocks,
                figures=figures,
                tables=tables,
            )
            reading_order += _count_visual_items(result)

        if not result_list:
            warnings.append(f"question_info_empty:{info_index}")

    page_payload = {
        "request_id": payload.get("RequestId"),
        "question_info_count": len(question_infos),
        "layout_only": layout_only,
    }
    return ProviderPageResult(
        page_no=page_no,
        blocks=sort_blocks(blocks),
        figures=figures,
        tables=tables,
        raw=sanitize_raw_payload(page_payload),
        warnings=list(dict.fromkeys(warnings)),
    )


def normalize_local_parser_page(
    *,
    page_no: int,
    page_text: str,
    blocks: Iterable[Any],
    provider_name: str = "local_parser",
) -> ProviderPageResult:
    normalized_blocks: list[NormalizedOCRBlock] = []
    for index, block in enumerate(blocks, start=1):
        bbox = [float(item) for item in getattr(block, "bbox", [])]
        text = str(getattr(block, "text", "") or "")
        normalized_blocks.append(
            build_normalized_block(
                block_id=f"{provider_name}-{page_no}-{index}",
                provider_ref=f"{provider_name}:page:{page_no}",
                page_no=page_no,
                text=text,
                bbox=bbox,
                block_type=_guess_text_block_type(text),
                confidence=None,
                reading_order=index,
                raw={"source": "local_parser"},
            )
        )
    return ProviderPageResult(
        page_no=page_no,
        blocks=sort_blocks(normalized_blocks),
        raw=sanitize_raw_payload({"page_text_length": len(page_text or "")}),
        warnings=[],
    )


def build_normalized_block(
    *,
    block_id: str,
    provider_ref: str,
    page_no: int,
    text: str,
    bbox: list[float] | None,
    block_type: str,
    confidence: float | None,
    reading_order: int,
    parent_block_id: str | None = None,
    raw: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> NormalizedOCRBlock:
    normalized_text = str(text or "").strip()
    if page_no <= 0:
        raise ValueError("page_no must be positive")
    if not str(provider_ref or "").strip():
        raise ValueError("provider_ref must not be empty")

    block_warnings = [str(item) for item in warnings or [] if str(item).strip()]
    normalized_bbox = [float(item) for item in (bbox or [])] if bbox else []
    if normalized_bbox and not is_valid_bbox(normalized_bbox):
        block_warnings.append("bbox_invalid")
        normalized_bbox = []
    if confidence is None:
        block_warnings.append("confidence_missing")
    if block_type in CONTENT_BLOCK_TYPES and not normalized_text:
        block_warnings.append("text_missing_for_content_block")
    if block_type == "bbox_only" and normalized_text:
        block_warnings.append("bbox_only_contains_text")

    return NormalizedOCRBlock(
        block_id=str(block_id),
        provider_ref=str(provider_ref),
        page_no=page_no,
        text=normalized_text,
        bbox=normalized_bbox,
        block_type=str(block_type or "unknown"),
        confidence=confidence,
        reading_order=max(0, int(reading_order)),
        parent_block_id=parent_block_id,
        raw=sanitize_raw_payload(raw or {}),
        warnings=list(dict.fromkeys(block_warnings)),
    )


def flatten_blocks(page_results: Iterable[ProviderPageResult]) -> list[NormalizedOCRBlock]:
    return sort_blocks([block for page in page_results for block in page.blocks])


def sort_blocks(blocks: Iterable[NormalizedOCRBlock]) -> list[NormalizedOCRBlock]:
    return sorted(
        list(blocks),
        key=lambda block: (
            block.page_no,
            block.reading_order,
            block.bbox[1] if len(block.bbox) == 4 else 0.0,
            block.block_id,
        ),
    )


def coerce_bbox(value: Any) -> list[float]:
    if isinstance(value, dict):
        if all(key in value for key in ("left", "top", "width", "height")):
            left = safe_float(value.get("left"))
            top = safe_float(value.get("top"))
            width = safe_float(value.get("width"))
            height = safe_float(value.get("height"))
            if None not in {left, top, width, height}:
                return [left, top, left + width, top + height]
        corners = []
        for key in ("LeftTop", "RightTop", "RightBottom", "LeftBottom"):
            point = value.get(key)
            if isinstance(point, dict):
                x = safe_float(point.get("X"))
                y = safe_float(point.get("Y"))
                if x is not None and y is not None:
                    corners.append((x, y))
        if corners:
            xs = [item[0] for item in corners]
            ys = [item[1] for item in corners]
            return [min(xs), min(ys), max(xs), max(ys)]
        points = value.get("point") or value.get("points")
        if isinstance(points, list):
            return coerce_bbox(points)
    if isinstance(value, list):
        if len(value) == 4 and all(isinstance(item, (int, float)) for item in value):
            return [float(item) for item in value]
        points: list[tuple[float, float]] = []
        for item in value:
            if isinstance(item, dict):
                candidate = coerce_bbox(item)
                if len(candidate) == 4:
                    points.extend([(candidate[0], candidate[1]), (candidate[2], candidate[3])])
                    continue
                x = safe_float(item.get("x"))
                y = safe_float(item.get("y"))
                if x is not None and y is not None:
                    points.append((x, y))
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                x = safe_float(item[0])
                y = safe_float(item[1])
                if x is not None and y is not None:
                    points.append((x, y))
        if points:
            xs = [item[0] for item in points]
            ys = [item[1] for item in points]
            return [min(xs), min(ys), max(xs), max(ys)]
    return []


def is_valid_bbox(bbox: list[float]) -> bool:
    if len(bbox) != 4:
        return False
    x0, y0, x1, y1 = bbox
    return x1 > x0 and y1 > y0


def extract_question_no(text: str) -> int | None:
    match = QUESTION_NO_RE.match(str(text or ""))
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def sanitize_raw_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized: dict[str, Any] = {}
        for index, (key, value) in enumerate(payload.items()):
            if index >= 12:
                sanitized["__truncated__"] = True
                break
            lowered = str(key).lower()
            if lowered in SENSITIVE_KEYS:
                sanitized[str(key)] = "[redacted]"
                continue
            sanitized[str(key)] = sanitize_raw_payload(value)
        return sanitized
    if isinstance(payload, list):
        limited = payload[:8]
        return [sanitize_raw_payload(item) for item in limited]
    if isinstance(payload, str):
        stripped = payload.strip()
        if not stripped:
            return ""
        lowered = stripped.lower()
        if lowered.startswith("akid") or "access_token" in lowered:
            return "[redacted]"
        if len(stripped) > 240:
            return f"{stripped[:237]}..."
        return stripped
    return payload


def warnings_from_baidu_response(payload: dict[str, Any]) -> list[str]:
    warnings = [str(item) for item in payload.get("warnings") or [] if str(item).strip()]
    if payload.get("log_id") is None:
        warnings.append("baidu_log_id_missing")
    return list(dict.fromkeys(warnings))


def _normalize_baidu_question_element(
    *,
    page_no: int,
    provider_name: str,
    question_ref: str,
    element: dict[str, Any],
    fallback_bbox: list[float],
    fallback_confidence: float | None,
    reading_order_start: int,
) -> list[NormalizedOCRBlock]:
    block_type = _baidu_elem_type_to_block_type(element.get("type") or element.get("elem_type"))
    words = element.get("elem_word") or element.get("words") or []
    blocks: list[NormalizedOCRBlock] = []
    if isinstance(words, list) and words:
        reading_order = reading_order_start
        for word_index, word in enumerate(words, start=1):
            text = str(word.get("word") or word.get("text") or "").strip()
            if not text and block_type != "bbox_only":
                continue
            blocks.append(
                build_normalized_block(
                    block_id=f"{provider_name}-{page_no}-{question_ref}-{block_type}-{word_index}",
                    provider_ref=f"{provider_name}:question:{question_ref}",
                    page_no=page_no,
                    text=text,
                    bbox=coerce_bbox(word.get("word_location") or word.get("location")) or list(fallback_bbox),
                    block_type=block_type,
                    confidence=safe_float(element.get("elem_probability") or element.get("probability")) or fallback_confidence,
                    reading_order=reading_order,
                    raw={"question_ref": question_ref, "element_type": element.get("elem_type")},
                )
            )
            reading_order += 1
        return blocks

    text_candidates = []
    elem_text = element.get("elem_text")
    if isinstance(elem_text, dict):
        for key, value in elem_text.items():
            if isinstance(value, str) and value.strip():
                text_candidates.append((key, value.strip()))
    elif isinstance(elem_text, str) and elem_text.strip():
        text_candidates.append(("elem_text", elem_text.strip()))

    reading_order = reading_order_start
    for key, text in text_candidates:
        blocks.append(
            build_normalized_block(
                block_id=f"{provider_name}-{page_no}-{question_ref}-{block_type}-{key}",
                provider_ref=f"{provider_name}:question:{question_ref}",
                page_no=page_no,
                text=text,
                bbox=coerce_bbox(element.get("elem_location") or element.get("location")) or list(fallback_bbox),
                block_type=_baidu_text_key_override(key, default=block_type),
                confidence=safe_float(element.get("elem_probability") or element.get("probability")) or fallback_confidence,
                reading_order=reading_order,
                raw={"question_ref": question_ref, "element_type": element.get("elem_type")},
            )
        )
        reading_order += 1
    return blocks


def _append_baidu_question_summary_blocks(
    *,
    page_no: int,
    provider_name: str,
    question_ref: str,
    item: dict[str, Any],
    blocks: list[NormalizedOCRBlock],
    fallback_bbox: list[float],
    fallback_confidence: float | None,
    reading_order: int,
) -> int:
    key_order = [
        ("stem_text", "stem"),
        ("subqus_text", "material_intro"),
        ("option_text", "option"),
        ("answer_text", "answer"),
        ("interpretation_text", "analysis"),
    ]
    for key, block_type in key_order:
        text = str(item.get(key) or "").strip()
        if not text:
            continue
        blocks.append(
            build_normalized_block(
                block_id=f"{provider_name}-{page_no}-{question_ref}-{key}",
                provider_ref=f"{provider_name}:question:{question_ref}",
                page_no=page_no,
                text=text,
                bbox=list(fallback_bbox),
                block_type=block_type,
                confidence=fallback_confidence,
                reading_order=reading_order,
                raw={"question_ref": question_ref, "field": key},
            )
        )
        reading_order += 1
    return reading_order


def _append_tencent_visual_blocks(
    *,
    provider_name: str,
    page_no: int,
    question_ref: str,
    root_block_id: str,
    reading_order_start: int,
    result: dict[str, Any],
    blocks: list[NormalizedOCRBlock],
    figures: list[dict[str, Any]],
    tables: list[dict[str, Any]],
) -> None:
    reading_order = reading_order_start
    for figure_index, figure in enumerate(result.get("Figure") or [], start=1):
        bbox = coerce_bbox(figure.get("Coord") if isinstance(figure, dict) else None)
        if not bbox:
            continue
        text = _extract_tencent_text(figure)
        block_type = (
            "chart"
            if _looks_like_chart(text)
            or _looks_like_chart(str(result.get("Text") or ""))
            or _looks_like_chart(str(result.get("GroupType") or ""))
            else "figure"
        )
        blocks.append(
            build_normalized_block(
                block_id=f"{provider_name}-{page_no}-{question_ref}-figure-{figure_index}",
                provider_ref=f"{provider_name}:question:{question_ref}",
                page_no=page_no,
                text=text,
                bbox=bbox,
                block_type=block_type,
                confidence=None,
                reading_order=reading_order,
                parent_block_id=root_block_id,
                raw={"question_ref": question_ref, "figure_index": figure_index},
            )
        )
        figures.append({"bbox": bbox, "question_ref": question_ref, "block_type": block_type})
        reading_order += 1

    for table_index, table in enumerate(result.get("Table") or [], start=1):
        bbox = coerce_bbox(table.get("Coord") if isinstance(table, dict) else None)
        if not bbox:
            continue
        blocks.append(
            build_normalized_block(
                block_id=f"{provider_name}-{page_no}-{question_ref}-table-{table_index}",
                provider_ref=f"{provider_name}:question:{question_ref}",
                page_no=page_no,
                text=_extract_tencent_text(table),
                bbox=bbox,
                block_type="table",
                confidence=None,
                reading_order=reading_order,
                parent_block_id=root_block_id,
                raw={"question_ref": question_ref, "table_index": table_index},
            )
        )
        tables.append({"bbox": bbox, "question_ref": question_ref})
        reading_order += 1


def _count_visual_items(result: dict[str, Any]) -> int:
    return len(result.get("Figure") or []) + len(result.get("Table") or [])


def _guess_question_block_type(text: str, group_type: Any) -> str:
    lowered = str(group_type or "").lower()
    if any(token in text for token in ("根据以下资料", "根据所给资料", "阅读以下材料")):
        return "material_intro"
    if "table" in lowered:
        return "table"
    if "chart" in lowered:
        return "chart"
    return "stem"


def _guess_text_block_type(text: str) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return "unknown"
    if QUESTION_NO_RE.match(normalized):
        return "question_no"
    if OPTION_RE.match(normalized):
        return "option"
    if normalized.startswith("答案") or normalized.lower().startswith("answer"):
        return "answer"
    if normalized.startswith("解析") or normalized.lower().startswith("analysis"):
        return "analysis"
    if any(token in normalized for token in ("根据以下资料", "阅读以下材料", "根据所给资料")):
        return "material_intro"
    if _looks_like_chart(normalized):
        return "chart"
    return "text"


def _looks_like_chart(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(token in lowered for token in ("图", "表", "chart", "table", "同比", "环比", "增长率"))


def _extract_tencent_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, dict):
        return ""
    for key in ("Text", "Value", "Answer", "Content"):
        text = str(value.get(key) or "").strip()
        if text:
            return text
    result_list = value.get("ResultList")
    if isinstance(result_list, list):
        parts = [str(item.get("Text") or "").strip() for item in result_list if isinstance(item, dict) and str(item.get("Text") or "").strip()]
        return "\n".join(parts).strip()
    return ""


def _baidu_elem_type_to_block_type(value: Any) -> str:
    mapping = {
        0: "stem",
        1: "material_intro",
        2: "answer",
        3: "option",
        4: "figure",
        5: "analysis",
    }
    try:
        key = int(value)
    except (TypeError, ValueError):
        return "unknown"
    return mapping.get(key, "unknown")


def _baidu_text_key_override(key: str, *, default: str) -> str:
    return {
        "stem_text": "stem",
        "subqus_text": "material_intro",
        "option_text": "option",
        "answer_text": "answer",
        "interpretation_text": "analysis",
    }.get(key, default)
