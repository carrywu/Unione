from __future__ import annotations

import re
from typing import Any


BANNED_SOURCE_ELEMENT_TYPES = {"caption", "heading", "image", "table"}
HEADER_FOOTER_RE = re.compile(r"^(?:\d{1,4}|.*(?:资料分析题库|夸夸刷|第[一二三四五六七八九十百千万\d]+章).*)$")
QUESTION_OR_OPTION_RE = re.compile(r"^\s*(?:(?:【\s*)?例\s*\d+|第\s*\d+\s*题|[A-D][.．、])")


def run_visual_assertions(layout: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    questions = _question_records(layout)
    visuals = {visual.get("id"): visual for visual in layout.get("visuals") or []}
    elements = layout.get("layout_elements") or []
    failures: list[dict[str, Any]] = []
    question_results: list[dict[str, Any]] = []

    for q_key, expected in (case.get("questions") or {}).items():
        index = int(expected.get("index") or q_key.lstrip("q"))
        question = questions.get(index)
        expected_visuals = list(expected.get("expected_visuals") or [])
        if not question:
            failures.append(_failure("missing_question", q_key, f"question index {index} was not parsed", []))
            continue

        actual_visuals = list(question.get("visual_ids") or question.get("image_refs") or [])
        source_bbox = _bbox(question.get("source_bbox"))
        source_page = int(question.get("source_page_start") or question.get("page_num") or question.get("page_range", [0])[0] or 0)
        question_results.append(
            {
                "question": q_key,
                "index": index,
                "expected_visuals": expected_visuals,
                "actual_visuals": actual_visuals,
                "source_page": source_page,
                "source_bbox": source_bbox,
            }
        )

        if actual_visuals != expected_visuals:
            failures.append(
                _failure(
                    "visual_ids_mismatch",
                    q_key,
                    f"expected {expected_visuals}, got {actual_visuals}",
                    _visual_boxes(visuals, set(expected_visuals) | set(actual_visuals)),
                )
            )

        expected_child_visuals = list(expected.get("expected_child_visuals") or [])
        if expected_child_visuals:
            child_ids: list[str] = []
            group_ids: set[str] = set()
            for visual_id in actual_visuals:
                visual = visuals.get(visual_id) or {}
                child_ids.extend(str(item) for item in visual.get("child_visual_ids") or [])
                group_id = visual.get("same_visual_group_id") or visual.get("visual_group_id")
                if group_id:
                    group_ids.add(str(group_id))
            if child_ids != expected_child_visuals:
                failures.append(
                    _failure(
                        "visual_child_ids_mismatch",
                        q_key,
                        f"expected child visuals {expected_child_visuals}, got {child_ids}",
                        _visual_boxes(visuals, set(actual_visuals)),
                    )
                )
            if not group_ids:
                failures.append(
                    _failure(
                        "visual_group_id_missing",
                        q_key,
                        "merged visual must expose a visual group id",
                        _visual_boxes(visuals, set(actual_visuals)),
                    )
                )

        expected_absorbed_texts = list(expected.get("expected_absorbed_texts") or [])
        if expected_absorbed_texts:
            absorbed_texts: list[dict[str, Any]] = []
            for visual_id in actual_visuals:
                visual = visuals.get(visual_id) or {}
                raw_bbox = _bbox(visual.get("raw_bbox"))
                expanded_bbox = _bbox(visual.get("expanded_bbox") or visual.get("bbox"))
                if not raw_bbox or not expanded_bbox:
                    failures.append(
                        _failure(
                            "visual_expansion_missing",
                            q_key,
                            f"{visual_id} must expose raw_bbox and expanded_bbox",
                            _visual_boxes(visuals, {visual_id}),
                        )
                    )
                elif raw_bbox == expanded_bbox:
                    failures.append(
                        _failure(
                            "visual_not_expanded",
                            q_key,
                            f"{visual_id} bbox was not expanded",
                            [
                                {"page": int(visual.get("page") or 0), "bbox": raw_bbox, "label": f"{visual_id} raw"},
                                {"page": int(visual.get("page") or 0), "bbox": expanded_bbox, "label": f"{visual_id} expanded"},
                            ],
                        )
                    )
                visual_absorbed = list(visual.get("absorbed_texts") or [])
                absorbed_texts.extend(visual_absorbed)
                for text in expected_absorbed_texts:
                    if not any(str(text) in str(item.get("text") or "") for item in visual_absorbed):
                        failures.append(
                            _failure(
                                "visual_absorbed_text_missing_for_visual",
                                q_key,
                                f"{visual_id} did not absorb expected caption/title text: {text}",
                                _visual_boxes(visuals, {visual_id}),
                            )
                        )
            for text in expected_absorbed_texts:
                if not any(str(text) in str(item.get("text") or "") for item in absorbed_texts):
                    failures.append(
                        _failure(
                            "visual_absorbed_text_missing",
                            q_key,
                            f"expected visual caption/title text not absorbed: {text}",
                            _visual_boxes(visuals, set(actual_visuals)),
                        )
                    )
            for item in absorbed_texts:
                absorbed_text = str(item.get("text") or "")
                if item.get("type") in {"question_marker", "option"} or QUESTION_OR_OPTION_RE.match(absorbed_text):
                    failures.append(
                        _failure(
                            "visual_absorbed_question_or_option",
                            q_key,
                            f"visual absorbed question/option text: {absorbed_text}",
                            _visual_boxes(visuals, set(actual_visuals)),
                        )
                    )

        if not source_bbox:
            failures.append(_failure("source_bbox_missing", q_key, "source_bbox is missing", []))
            continue

        for visual_id in expected.get("must_not_overlap_visuals") or []:
            visual = visuals.get(visual_id)
            visual_bbox = _bbox((visual or {}).get("bbox"))
            if visual_bbox and _overlap_ratio(source_bbox, visual_bbox) > 0.02:
                failures.append(
                    _failure(
                        "source_overlaps_visual",
                        q_key,
                        f"source_bbox overlaps {visual_id}",
                        [
                            {"page": source_page, "bbox": source_bbox, "label": f"{q_key} source"},
                            {"page": int((visual or {}).get("page") or source_page), "bbox": visual_bbox, "label": visual_id},
                        ],
                    )
                )

        for other_key in expected.get("must_not_overlap_questions") or []:
            other_index = int(str(other_key).lstrip("q"))
            other = questions.get(other_index)
            other_bbox = _bbox((other or {}).get("source_bbox"))
            other_page = int((other or {}).get("source_page_start") or (other or {}).get("page_num") or 0)
            if other_bbox and other_page == source_page and _overlap_ratio(source_bbox, other_bbox) > 0.02:
                failures.append(
                    _failure(
                        "source_overlaps_question",
                        q_key,
                        f"source_bbox overlaps {other_key}",
                        [
                            {"page": source_page, "bbox": source_bbox, "label": f"{q_key} source"},
                            {"page": other_page, "bbox": other_bbox, "label": f"{other_key} source"},
                        ],
                    )
                )

        for element in elements:
            if int(element.get("page") or 0) != source_page:
                continue
            element_bbox = _bbox(element.get("bbox"))
            if not element_bbox or _overlap_ratio(source_bbox, element_bbox) <= 0.02:
                continue
            text = re.sub(r"\s+", "", str(element.get("text") or ""))
            if element.get("type") in BANNED_SOURCE_ELEMENT_TYPES or HEADER_FOOTER_RE.match(text):
                failures.append(
                    _failure(
                        "source_overlaps_banned_element",
                        q_key,
                        f"source_bbox overlaps {element.get('type')} {element.get('id')}",
                        [
                            {"page": source_page, "bbox": source_bbox, "label": f"{q_key} source"},
                            {"page": source_page, "bbox": element_bbox, "label": str(element.get("id") or element.get("type"))},
                        ],
                    )
                )

    return {
        "passed": not failures,
        "failed_count": len(failures),
        "failures": failures,
        "questions": question_results,
    }


def _question_records(layout: dict[str, Any]) -> dict[int, dict[str, Any]]:
    by_index: dict[int, dict[str, Any]] = {}
    exercise_by_index: dict[int, dict[str, Any]] = {}
    for exercise in layout.get("exercise_blocks") or []:
        core = exercise.get("question_core") or {}
        if core.get("index") is not None:
            exercise_by_index[int(core["index"])] = exercise
    for question in layout.get("questions") or []:
        index = int(question.get("index") or question.get("index_num") or 0)
        merged = dict(question)
        exercise = exercise_by_index.get(index)
        if exercise:
            merged.setdefault("visual_ids", exercise.get("visual_ids") or [])
        by_index[index] = merged
    return by_index


def _bbox(value: Any) -> list[float] | None:
    if not isinstance(value, list | tuple) or len(value) != 4:
        return None
    try:
        bbox = [float(item) for item in value]
    except (TypeError, ValueError):
        return None
    if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        return None
    return bbox


def _visual_boxes(visuals: dict[str, dict[str, Any]], visual_ids: set[str]) -> list[dict[str, Any]]:
    boxes: list[dict[str, Any]] = []
    for visual_id in sorted(visual_ids):
        visual = visuals.get(visual_id)
        bbox = _bbox((visual or {}).get("bbox"))
        if bbox:
            boxes.append({"page": int((visual or {}).get("page") or 0), "bbox": bbox, "label": visual_id})
    return boxes


def _overlap_ratio(left: list[float], right: list[float]) -> float:
    x0 = max(left[0], right[0])
    y0 = max(left[1], right[1])
    x1 = min(left[2], right[2])
    y1 = min(left[3], right[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    overlap = (x1 - x0) * (y1 - y0)
    left_area = max(1.0, (left[2] - left[0]) * (left[3] - left[1]))
    right_area = max(1.0, (right[2] - right[0]) * (right[3] - right[1]))
    return overlap / min(left_area, right_area)


def _failure(kind: str, question: str, message: str, boxes: list[dict[str, Any]]) -> dict[str, Any]:
    return {"kind": kind, "question": question, "message": message, "boxes": boxes}
