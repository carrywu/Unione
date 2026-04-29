from __future__ import annotations

import re
from dataclasses import asdict

from layout_models import LayoutElement, QuestionCoreBlock, SharedMaterialBlock, VisualBlock, VisualCandidate

VISUAL_HINT_RE = re.compile(r"(下图|如下图|图中|根据图|上图|下表|如下表|表中|根据表|上表|图|表)")


def assign_visuals(
    visuals: list[VisualBlock],
    question_cores: list[QuestionCoreBlock],
    materials: list[SharedMaterialBlock],
    elements: list[LayoutElement],
) -> dict:
    question_visuals: dict[str, list[str]] = {question.id: [] for question in question_cores}
    material_visuals: dict[str, list[str]] = {material.id: list(material.visual_ids) for material in materials}
    warnings: list[dict] = []
    element_by_id = {element.id: element for element in elements}

    for visual in visuals:
        if _is_duplicate_fallback_visual(visual, visuals):
            visual.warnings.append("visual_duplicate_fallback_ignored")
            warnings.append({"visual_id": visual.id, "warning": "visual_duplicate_fallback_ignored", "candidates": []})
            continue

        following_question = _nearest_following_question(visual, question_cores, element_by_id)
        if following_question:
            score, reasons = _score_question(visual, following_question, element_by_id)
            best = VisualCandidate(
                following_question.id,
                "question",
                max(score, 82.0),
                [*reasons, "nearest_following_question_anchor"],
            )
            visual.candidates = [best]
            visual.assigned_to = best.target_id
            visual.assigned_type = best.target_type
            visual.assignment_confidence = round(min(1.0, best.score / 100), 2)
            question_visuals.setdefault(best.target_id, []).append(visual.id)
            continue

        candidates: list[VisualCandidate] = []
        for material in materials:
            score, reasons = _score_material(visual, material, element_by_id)
            if score > 0:
                candidates.append(VisualCandidate(material.id, "material", score, reasons))
        for question in question_cores:
            score, reasons = _score_question(visual, question, element_by_id)
            if score > 0:
                candidates.append(VisualCandidate(question.id, "question", score, reasons))
        candidates.sort(key=lambda item: item.score, reverse=True)
        visual.candidates = candidates
        if not candidates or candidates[0].score < 45:
            visual.warnings.append("visual_unassigned")
            warnings.append({"visual_id": visual.id, "warning": "visual_unassigned", "candidates": [asdict(item) for item in candidates[:5]]})
            continue
        best = _resolve_conflict(candidates, question_cores, materials)
        visual.assigned_to = best.target_id
        visual.assigned_type = best.target_type
        visual.assignment_confidence = round(min(1.0, best.score / 100), 2)
        if best.score < 65:
            visual.warnings.append("visual_assignment_low_confidence")
            warnings.append({"visual_id": visual.id, "warning": "visual_assignment_low_confidence", "candidates": [asdict(item) for item in candidates[:5]]})
        if best.target_type == "material":
            material_visuals.setdefault(best.target_id, []).append(visual.id)
        else:
            question_visuals.setdefault(best.target_id, []).append(visual.id)

    for material in materials:
        material.visual_ids = material_visuals.get(material.id, [])

    return {"questions": question_visuals, "materials": material_visuals, "warnings": warnings}


def _score_material(visual: VisualBlock, material: SharedMaterialBlock, element_by_id: dict[str, LayoutElement]) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    material_orders = [element_by_id[element_id].order_index for element_id in material.element_ids if element_id in element_by_id]
    if material_orders and min(material_orders) <= _visual_order(visual, element_by_id) <= max(material_orders) + 12:
        score += 45
        reasons.append("visual_near_material_window")
    if material.page_start <= visual.page <= material.page_end:
        score += 20
        reasons.append("same_material_page_range")
    if material.question_range:
        score += 20
        reasons.append("material_has_question_range")
    context = f"{visual.caption or ''}\n{visual.nearby_text_before or ''}\n{visual.nearby_text_after or ''}"
    if re.search(r"(资料|材料|图|表|统计|情况)", context):
        score += 10
        reasons.append("material_visual_context")
    return score, reasons


def _score_question(visual: VisualBlock, question: QuestionCoreBlock, element_by_id: dict[str, LayoutElement]) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    question_orders = [element_by_id[element_id].order_index for element_id in question.element_ids if element_id in element_by_id]
    if not question_orders:
        return score, reasons
    visual_order = _visual_order(visual, element_by_id)
    q_min, q_max = min(question_orders), max(question_orders)
    if q_min <= visual_order <= q_max:
        score += 40
        reasons.append("inside_question_block")
    elif q_min - 4 <= visual_order < q_min:
        score += 25
        reasons.append("before_question_nearby")
    elif q_max < visual_order <= q_max + 4:
        score += 10
        reasons.append("after_question_weak")
    if VISUAL_HINT_RE.search(question.stem_text):
        score += 25
        reasons.append("stem_has_visual_hint")
        if re.search(r"(上图|上表)", question.stem_text) and visual_order < q_min:
            score += 10
            reasons.append("stem_points_backward")
    overlap = _keyword_overlap(question.stem_text, f"{visual.caption or ''} {visual.nearby_text_before or ''} {visual.nearby_text_after or ''}")
    if overlap:
        score += min(15, overlap * 5)
        reasons.append("caption_keyword_overlap")
    distance = min(abs(visual_order - q_min), abs(visual_order - q_max))
    score += max(0, 20 - distance * 3)
    return score, reasons


def _resolve_conflict(candidates: list[VisualCandidate], questions: list[QuestionCoreBlock], materials: list[SharedMaterialBlock]) -> VisualCandidate:
    best = candidates[0]
    if len(candidates) < 2:
        return best
    second = candidates[1]
    if best.target_type != second.target_type and abs(best.score - second.score) < 10:
        material_candidate = next((item for item in [best, second] if item.target_type == "material"), None)
        question_candidate = next((item for item in [best, second] if item.target_type == "question"), None)
        if material_candidate and question_candidate:
            material = next((item for item in materials if item.id == material_candidate.target_id), None)
            question = next((item for item in questions if item.id == question_candidate.target_id), None)
            if material and question and material.question_range and material.question_range[0] <= question.index <= material.question_range[1]:
                return material_candidate
    return best


def _nearest_following_question(
    visual: VisualBlock,
    questions: list[QuestionCoreBlock],
    element_by_id: dict[str, LayoutElement],
) -> QuestionCoreBlock | None:
    visual_order = _visual_order(visual, element_by_id)
    following: list[tuple[int, QuestionCoreBlock]] = []
    for question in questions:
        question_orders = [element_by_id[element_id].order_index for element_id in question.element_ids if element_id in element_by_id]
        if not question_orders:
            continue
        q_min = min(question_orders)
        marker = element_by_id.get(question.element_ids[0])
        if q_min > visual_order and marker and marker.page == visual.page:
            following.append((q_min, question))
    if not following:
        return None
    q_min, question = min(following, key=lambda item: item[0])
    return question if q_min - visual_order <= 4 else None


def _is_duplicate_fallback_visual(visual: VisualBlock, visuals: list[VisualBlock]) -> bool:
    if "render_cv_fallback_raster" not in visual.warnings:
        return False
    for other in visuals:
        if other is visual or other.page != visual.page:
            continue
        if "render_cv_fallback_raster" in other.warnings:
            continue
        if _bbox_overlap_ratio(visual.bbox, other.bbox) >= 0.3:
            return True
        if _x_overlap_ratio(visual.bbox, other.bbox) >= 0.6 and _y_gap(visual.bbox, other.bbox) <= 80:
            return True
    return False


def _bbox_overlap_ratio(left: list[float], right: list[float]) -> float:
    if len(left) != 4 or len(right) != 4:
        return 0.0
    x0 = max(float(left[0]), float(right[0]))
    y0 = max(float(left[1]), float(right[1]))
    x1 = min(float(left[2]), float(right[2]))
    y1 = min(float(left[3]), float(right[3]))
    if x1 <= x0 or y1 <= y0:
        return 0.0
    overlap = (x1 - x0) * (y1 - y0)
    left_area = max(1.0, (float(left[2]) - float(left[0])) * (float(left[3]) - float(left[1])))
    right_area = max(1.0, (float(right[2]) - float(right[0])) * (float(right[3]) - float(right[1])))
    return overlap / min(left_area, right_area)


def _x_overlap_ratio(left: list[float], right: list[float]) -> float:
    if len(left) != 4 or len(right) != 4:
        return 0.0
    x0 = max(float(left[0]), float(right[0]))
    x1 = min(float(left[2]), float(right[2]))
    if x1 <= x0:
        return 0.0
    left_width = max(1.0, float(left[2]) - float(left[0]))
    right_width = max(1.0, float(right[2]) - float(right[0]))
    return (x1 - x0) / min(left_width, right_width)


def _y_gap(left: list[float], right: list[float]) -> float:
    if len(left) != 4 or len(right) != 4:
        return float("inf")
    if float(left[3]) < float(right[1]):
        return float(right[1]) - float(left[3])
    if float(right[3]) < float(left[1]):
        return float(left[1]) - float(right[3])
    return 0.0


def _visual_order(visual: VisualBlock, element_by_id: dict[str, LayoutElement]) -> int:
    for element in element_by_id.values():
        if element.image_path == visual.image_path:
            return element.order_index
    same_page = [element.order_index for element in element_by_id.values() if element.page == visual.page]
    return min(same_page) if same_page else 0


def _keyword_overlap(left: str, right: str) -> int:
    tokens = {token for token in re.split(r"\W+", left) if len(token) >= 2}
    other = {token for token in re.split(r"\W+", right) if len(token) >= 2}
    return len(tokens & other)
