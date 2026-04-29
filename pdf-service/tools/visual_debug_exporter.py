from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import fitz
from PIL import Image, ImageDraw

from debug_writer import _jsonable


QUESTION_COLOR = (0, 170, 80)
MATERIAL_COLOR = (0, 105, 220)
VISUAL_COLOR = (230, 130, 0)
WARNING_COLOR = (220, 30, 30)
FINAL_COLOR = (90, 40, 220)
CONTEXT_COLOR = (140, 65, 190)
LINKED_MATERIAL_COLOR = (0, 95, 170)
LINKED_VISUAL_COLOR = (210, 90, 0)
BOUNDARY_COLOR = (180, 0, 180)
CROP_PADDING_PX = 8
QUESTION_CONTEXT_TOP_PADDING_PX = 24


def export_visual_debug_images(
    *,
    pdf_path: Path,
    output_dir: Path,
    visual_pages: list[dict[str, Any]],
    questions: list[dict[str, Any]],
    materials: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    debug_dir = output_dir / "debug"
    overlay_dir = debug_dir / "overlays"
    crop_dir = debug_dir / "crops"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    crop_dir.mkdir(parents=True, exist_ok=True)

    page_rects = _load_page_rects(pdf_path)
    questions_by_page = _group_questions_by_page(questions)
    material_ids_by_content = {_normalize_content(item.get("content")): item.get("temp_id") for item in materials}
    lineages: list[dict[str, Any]] = []

    for page in visual_pages:
        page_num = int(page.get("page_num") or 0)
        if page_num <= 0:
            continue
        screenshot = output_dir / "page_screenshots" / f"page_{page_num:03d}.png"
        if not screenshot.exists():
            continue

        image = Image.open(screenshot).convert("RGB")
        draw = ImageDraw.Draw(image)
        image_size = {"width": image.width, "height": image.height}
        page_rect = page_rects.get(page_num)
        raw_result = page.get("normalized_result") or page.get("raw_result") or {}
        page_warnings = list(page.get("page_warnings") or [])

        raw_materials = _draw_raw_materials(
            draw=draw,
            page_num=page_num,
            raw_result=raw_result,
            material_ids_by_content=material_ids_by_content,
            page_warnings=page_warnings,
        )
        _draw_raw_questions(draw=draw, raw_result=raw_result, page_warnings=page_warnings)
        raw_visuals = _draw_raw_visuals(draw=draw, raw_result=raw_result, page_warnings=page_warnings)

        for question in questions_by_page.get(page_num, []):
            raw_question = _find_raw_question(raw_result, question.get("index"))
            lineage = _export_question_crop(
                image=image,
                draw=draw,
                crop_dir=crop_dir,
                page_num=page_num,
                question=question,
                raw_question=raw_question,
                raw_questions=raw_result.get("questions") or [],
                raw_materials=raw_materials,
                raw_visuals=raw_visuals,
                page_rect=page_rect,
                image_size=image_size,
                page_warnings=page_warnings,
            )
            if lineage:
                lineages.append(lineage)

        for raw_material in raw_materials:
            lineage = _export_material_crop(
                image=image,
                draw=draw,
                crop_dir=crop_dir,
                page_num=page_num,
                raw_material=raw_material,
                page_warnings=page_warnings,
            )
            if lineage:
                lineages.append(lineage)

        _draw_legend(draw)
        image.save(overlay_dir / f"page_{page_num:03d}_overlay.png")

    (debug_dir / "bbox_lineage.json").write_text(
        json.dumps(_jsonable(lineages), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return lineages


def _load_page_rects(pdf_path: Path) -> dict[int, fitz.Rect]:
    try:
        doc = fitz.open(str(pdf_path))
    except Exception:
        return {}
    try:
        return {index + 1: page.rect for index, page in enumerate(doc)}
    finally:
        doc.close()


def _group_questions_by_page(questions: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for question in questions:
        try:
            page_num = int(question.get("page_num") or question.get("source_page_start") or 0)
        except (TypeError, ValueError):
            continue
        if page_num > 0:
            grouped.setdefault(page_num, []).append(question)
    return grouped


def _draw_raw_materials(
    *,
    draw: ImageDraw.ImageDraw,
    page_num: int,
    raw_result: dict[str, Any],
    material_ids_by_content: dict[str, str | None],
    page_warnings: list[str],
) -> list[dict[str, Any]]:
    materials: list[dict[str, Any]] = []
    for material in raw_result.get("materials") or []:
        bbox = _coerce_bbox(material.get("bbox"))
        if not bbox:
            continue
        global_id = material_ids_by_content.get(_normalize_content(material.get("content"))) or material.get("temp_id")
        record = {**material, "global_material_id": global_id, "page_num": page_num}
        materials.append(record)
        _draw_box(
            draw,
            bbox,
            MATERIAL_COLOR,
            f"material {global_id or material.get('temp_id')} conf=0.85 clamped={_has_visual_clamp(page_warnings)}",
        )
    return materials


def _draw_raw_questions(
    *,
    draw: ImageDraw.ImageDraw,
    raw_result: dict[str, Any],
    page_warnings: list[str],
) -> None:
    for question in raw_result.get("questions") or []:
        bbox = _coerce_bbox(question.get("bbox") or question.get("stem_bbox"))
        if not bbox:
            continue
        qid = _format_qid(question.get("index"))
        _draw_box(draw, bbox, QUESTION_COLOR, f"{qid} raw conf=? clamped={_has_visual_clamp(page_warnings)}")


def _draw_raw_visuals(
    *,
    draw: ImageDraw.ImageDraw,
    raw_result: dict[str, Any],
    page_warnings: list[str],
) -> list[dict[str, Any]]:
    visuals: list[dict[str, Any]] = []
    for index, visual in enumerate(raw_result.get("visuals") or [], start=1):
        bbox = _coerce_bbox(visual.get("bbox"))
        if not bbox:
            continue
        record = {**visual, "visual_index": index, "bbox": bbox}
        visuals.append(record)
        kind = visual.get("kind") or "visual"
        _draw_box(draw, bbox, VISUAL_COLOR, f"{kind}#{index} conf=? clamped={_has_visual_clamp(page_warnings)}")
    return visuals


def _export_question_crop(
    *,
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    crop_dir: Path,
    page_num: int,
    question: dict[str, Any],
    raw_question: dict[str, Any] | None,
    raw_questions: list[dict[str, Any]],
    raw_materials: list[dict[str, Any]],
    raw_visuals: list[dict[str, Any]],
    page_rect: fitz.Rect | None,
    image_size: dict[str, int],
    page_warnings: list[str],
) -> dict[str, Any] | None:
    confidence = float(question.get("source_confidence") or 0.7)
    raw_bbox = _coerce_bbox((raw_question or {}).get("bbox") or (raw_question or {}).get("stem_bbox"))
    source_bbox = _coerce_bbox(question.get("source_bbox"))
    final_bbox = _pdf_to_pixel_bbox(source_bbox, page_rect, image_size) if source_bbox else raw_bbox
    if not final_bbox:
        return None

    warnings = list(question.get("parse_warnings") or [])
    linked_material = _find_linked_material(question=question, raw_question=raw_question, raw_materials=raw_materials)
    linked_visuals = _find_linked_visuals(linked_material=linked_material, raw_visuals=raw_visuals)
    crop_context_mode = _question_crop_context_mode(
        question=question,
        linked_material=linked_material,
        linked_visuals=linked_visuals,
    )
    context_bbox = _question_context_bbox(
        question_bbox=final_bbox,
        linked_material=linked_material,
        linked_visuals=linked_visuals,
        crop_context_mode=crop_context_mode,
    )
    expanded, clamped, clamp_reasons = _expand_and_clamp(
        context_bbox,
        image.size,
        top_padding=QUESTION_CONTEXT_TOP_PADDING_PX,
    )
    boundary = _next_question_boundary(raw_questions=raw_questions, current_bbox=raw_bbox or final_bbox)
    if boundary is not None and clamped[3] >= boundary:
        clamped[3] = max(clamped[1] + 1.0, boundary - 1.0)
        clamp_reasons.append("next_question_boundary")
    qid = int(question.get("index") or 0)
    filename = crop_dir / f"page_{page_num:03d}_q{qid:03d}_conf_{confidence:.2f}_crop.png"
    image.crop(_int_bbox(clamped)).save(filename)

    color = WARNING_COLOR if warnings or confidence < 0.7 else FINAL_COLOR
    material_bbox = _coerce_bbox((linked_material or {}).get("bbox"))
    linked_material_id = _material_identifier(linked_material)
    visual_bbox_list = [
        bbox
        for bbox in (_coerce_bbox(visual.get("bbox")) for visual in linked_visuals)
        if bbox
    ]
    _draw_box(draw, context_bbox, CONTEXT_COLOR, f"{_format_qid(qid)} context", width=2)
    if material_bbox:
        _draw_box(draw, material_bbox, LINKED_MATERIAL_COLOR, f"{_format_qid(qid)} linked material", width=3)
    for visual_index, visual_bbox in enumerate(visual_bbox_list, start=1):
        _draw_box(draw, visual_bbox, LINKED_VISUAL_COLOR, f"{_format_qid(qid)} linked visual {visual_index}", width=3)
    if boundary is not None:
        _draw_boundary(draw, boundary, image.width, f"{_format_qid(qid)} next boundary")
    _draw_box(
        draw,
        clamped,
        color,
        f"{_format_qid(qid)} crop conf={confidence:.2f} warnings={_label_warnings(warnings)} "
        f"crop_clamped={bool(clamp_reasons)} visual_clamped={_has_visual_clamp(page_warnings)}",
        width=3,
    )
    return {
        "type": "question_crop",
        "file": str(filename),
        "page_num": page_num,
        "raw_bbox": raw_bbox,
        "question_bbox": final_bbox,
        "context_bbox": context_bbox,
        "material_bbox": material_bbox,
        "visual_bbox_list": visual_bbox_list,
        "expanded_bbox": expanded,
        "clamped_bbox": clamped,
        "final_bbox": clamped,
        "clamp_reason": clamp_reasons,
        "crop_context_mode": crop_context_mode,
        "next_question_boundary": boundary,
        "source_candidate_id": f"page_{page_num:03d}_q{qid:03d}",
        "linked_question_id": qid,
        "linked_material_id": linked_material_id,
        "linked_visual_count": len(linked_visuals),
        "confidence": confidence,
        "warnings": warnings,
        "visual_bbox_clamped": _has_visual_clamp(page_warnings),
    }


def _export_material_crop(
    *,
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    crop_dir: Path,
    page_num: int,
    raw_material: dict[str, Any],
    page_warnings: list[str],
) -> dict[str, Any] | None:
    raw_bbox = _coerce_bbox(raw_material.get("bbox"))
    if not raw_bbox:
        return None
    material_id = str(raw_material.get("global_material_id") or raw_material.get("temp_id") or "unknown")
    confidence = 0.85
    warnings = list(raw_material.get("parse_warnings") or [])
    expanded, clamped, clamp_reasons = _expand_and_clamp(raw_bbox, image.size)
    safe_id = _safe_filename(material_id)
    filename = crop_dir / f"page_{page_num:03d}_material_{safe_id}_conf_{confidence:.2f}_crop.png"
    image.crop(_int_bbox(clamped)).save(filename)
    _draw_box(
        draw,
        clamped,
        MATERIAL_COLOR,
        f"material {material_id} crop conf={confidence:.2f} warnings={_label_warnings(warnings)} "
        f"crop_clamped={bool(clamp_reasons)} visual_clamped={_has_visual_clamp(page_warnings)}",
        width=3,
    )
    return {
        "type": "material_crop",
        "file": str(filename),
        "page_num": page_num,
        "raw_bbox": raw_bbox,
        "expanded_bbox": expanded,
        "clamped_bbox": clamped,
        "final_bbox": clamped,
        "clamp_reason": clamp_reasons,
        "source_candidate_id": f"page_{page_num:03d}_material_{raw_material.get('temp_id') or safe_id}",
        "linked_question_id": None,
        "linked_material_id": material_id,
        "confidence": confidence,
        "warnings": warnings,
        "visual_bbox_clamped": _has_visual_clamp(page_warnings),
    }


def _find_raw_question(raw_result: dict[str, Any], index: Any) -> dict[str, Any] | None:
    for question in raw_result.get("questions") or []:
        if question.get("index") == index:
            return question
    return None


def _find_linked_material(
    *,
    question: dict[str, Any],
    raw_question: dict[str, Any] | None,
    raw_materials: list[dict[str, Any]],
) -> dict[str, Any] | None:
    material_id = (
        question.get("material_temp_id")
        or question.get("material_id")
        or (raw_question or {}).get("material_temp_id")
        or (raw_question or {}).get("material_id")
    )
    if not material_id:
        return None
    normalized_id = str(material_id)
    for material in raw_materials:
        candidates = {
            str(material.get("global_material_id") or ""),
            str(material.get("temp_id") or ""),
            str(material.get("material_id") or ""),
        }
        if normalized_id in candidates:
            return material
    return None


def _material_identifier(material: dict[str, Any] | None) -> str | None:
    if not material:
        return None
    value = material.get("global_material_id") or material.get("temp_id") or material.get("material_id")
    return str(value) if value else None


def _find_linked_visuals(
    *,
    linked_material: dict[str, Any] | None,
    raw_visuals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    material_bbox = _coerce_bbox((linked_material or {}).get("bbox"))
    if not material_bbox:
        return []
    linked: list[dict[str, Any]] = []
    for visual in raw_visuals:
        bbox = _coerce_bbox(visual.get("bbox"))
        if not bbox:
            continue
        kind = str(visual.get("kind") or "visual").lower()
        if kind not in {"chart", "table", "image", "visual"}:
            continue
        if _bbox_intersects_or_inside(bbox, material_bbox):
            linked.append(visual)
    return linked


def _question_crop_context_mode(
    *,
    question: dict[str, Any],
    linked_material: dict[str, Any] | None,
    linked_visuals: list[dict[str, Any]],
) -> str:
    if question.get("crop_context_mode") in {"question_only", "question_with_material", "full_material_context"}:
        return str(question["crop_context_mode"])
    if question.get("material_temp_id") or question.get("material_id") or linked_material or linked_visuals:
        return "question_with_material"
    return "question_only"


def _question_context_bbox(
    *,
    question_bbox: list[float],
    linked_material: dict[str, Any] | None,
    linked_visuals: list[dict[str, Any]],
    crop_context_mode: str,
) -> list[float]:
    if crop_context_mode == "question_only":
        return question_bbox
    bboxes = [question_bbox]
    material_bbox = _coerce_bbox((linked_material or {}).get("bbox"))
    if material_bbox:
        bboxes.append(material_bbox)
    for visual in linked_visuals:
        visual_bbox = _coerce_bbox(visual.get("bbox"))
        if visual_bbox:
            bboxes.append(visual_bbox)
    return _union_bboxes(bboxes)


def _next_question_boundary(
    *,
    raw_questions: list[dict[str, Any]],
    current_bbox: list[float],
) -> float | None:
    current_y0 = current_bbox[1]
    current_y1 = current_bbox[3]
    boundaries: list[float] = []
    for question in raw_questions:
        bbox = _coerce_bbox(question.get("bbox") or question.get("stem_bbox"))
        if not bbox:
            continue
        if bbox[1] > current_y0 and bbox[1] >= current_y1:
            boundaries.append(bbox[1])
    return min(boundaries) if boundaries else None


def _union_bboxes(bboxes: list[list[float]]) -> list[float]:
    return [
        min(bbox[0] for bbox in bboxes),
        min(bbox[1] for bbox in bboxes),
        max(bbox[2] for bbox in bboxes),
        max(bbox[3] for bbox in bboxes),
    ]


def _bbox_intersects_or_inside(a: list[float], b: list[float]) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def _pdf_to_pixel_bbox(
    bbox: list[float] | None,
    page_rect: fitz.Rect | None,
    image_size: dict[str, int],
) -> list[float] | None:
    if not bbox:
        return None
    if not page_rect or page_rect.width <= 0 or page_rect.height <= 0:
        return bbox
    width = float(image_size["width"])
    height = float(image_size["height"])
    return [
        (bbox[0] - page_rect.x0) / page_rect.width * width,
        (bbox[1] - page_rect.y0) / page_rect.height * height,
        (bbox[2] - page_rect.x0) / page_rect.width * width,
        (bbox[3] - page_rect.y0) / page_rect.height * height,
    ]


def _expand_and_clamp(
    bbox: list[float],
    image_size: tuple[int, int],
    *,
    top_padding: int = CROP_PADDING_PX,
) -> tuple[list[float], list[float], list[str]]:
    width, height = image_size
    expanded = [
        bbox[0] - CROP_PADDING_PX,
        bbox[1] - top_padding,
        bbox[2] + CROP_PADDING_PX,
        bbox[3] + CROP_PADDING_PX,
    ]
    clamped = [
        max(0.0, min(float(width), expanded[0])),
        max(0.0, min(float(height), expanded[1])),
        max(0.0, min(float(width), expanded[2])),
        max(0.0, min(float(height), expanded[3])),
    ]
    reasons: list[str] = []
    labels = ["x0", "y0", "x1", "y1"]
    for label, before, after in zip(labels, expanded, clamped):
        if before != after:
            reasons.append(f"{label}_clamped")
    if clamped[2] <= clamped[0]:
        clamped[2] = min(float(width), clamped[0] + 1.0)
        reasons.append("width_minimized")
    if clamped[3] <= clamped[1]:
        clamped[3] = min(float(height), clamped[1] + 1.0)
        reasons.append("height_minimized")
    return expanded, clamped, reasons


def _coerce_bbox(value: Any) -> list[float] | None:
    if not isinstance(value, list | tuple) or len(value) != 4:
        return None
    try:
        bbox = [float(item) for item in value]
    except (TypeError, ValueError):
        return None
    if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        return None
    return bbox


def _draw_box(
    draw: ImageDraw.ImageDraw,
    bbox: list[float],
    color: tuple[int, int, int],
    label: str,
    *,
    width: int = 2,
) -> None:
    box = _int_bbox(bbox)
    draw.rectangle(box, outline=color, width=width)
    text_x = box[0] + 2
    text_y = max(0, box[1] - 12)
    draw.rectangle([text_x - 1, text_y, text_x + min(len(label) * 6, 700), text_y + 11], fill=(255, 255, 255))
    draw.text((text_x, text_y), label[:120], fill=color)


def _draw_boundary(draw: ImageDraw.ImageDraw, y: float, width: int, label: str) -> None:
    y_int = int(round(y))
    draw.line([(0, y_int), (width, y_int)], fill=BOUNDARY_COLOR, width=2)
    draw.rectangle([4, max(0, y_int - 13), 4 + min(len(label) * 6, 360), max(11, y_int - 2)], fill=(255, 255, 255))
    draw.text((5, max(0, y_int - 13)), label[:60], fill=BOUNDARY_COLOR)


def _draw_legend(draw: ImageDraw.ImageDraw) -> None:
    entries = [
        ("question bbox", QUESTION_COLOR),
        ("context bbox", CONTEXT_COLOR),
        ("linked material", LINKED_MATERIAL_COLOR),
        ("linked visual", LINKED_VISUAL_COLOR),
        ("final crop", FINAL_COLOR),
        ("warning crop", WARNING_COLOR),
        ("next boundary", BOUNDARY_COLOR),
    ]
    x0 = 8
    y0 = 8
    row_h = 14
    width = 170
    height = row_h * len(entries) + 8
    draw.rectangle([x0 - 4, y0 - 4, x0 + width, y0 + height], fill=(255, 255, 255), outline=(80, 80, 80))
    for index, (label, color) in enumerate(entries):
        y = y0 + index * row_h
        draw.rectangle([x0, y + 2, x0 + 10, y + 10], outline=color, width=2)
        draw.text((x0 + 16, y), label, fill=color)


def _int_bbox(bbox: list[float]) -> tuple[int, int, int, int]:
    return tuple(int(round(value)) for value in bbox)  # type: ignore[return-value]


def _normalize_content(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^根据以下资料[:：]?\s*", "", text)
    return re.sub(r"\s+", "", text)


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def _format_qid(index: Any) -> str:
    try:
        return f"q{int(index):03d}"
    except (TypeError, ValueError):
        return "q???"


def _label_warnings(warnings: list[str]) -> str:
    return ",".join(warnings) if warnings else "none"


def _has_visual_clamp(page_warnings: list[str]) -> bool:
    return "visual_bbox_clamped" in page_warnings
