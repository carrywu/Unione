from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz
from PIL import Image, ImageDraw


ORANGE = (235, 130, 20)
BLUE = (30, 110, 230)
GREEN = (20, 160, 80)
PURPLE = (145, 70, 190)
RED = (220, 30, 30)


def draw_overlays(*, pdf_path: Path, layout: dict[str, Any], assertions: dict[str, Any], out_dir: Path) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    elements_by_page = _group_by_page(layout.get("layout_elements") or [])
    visuals_by_page = _group_by_page(layout.get("visuals") or [])
    questions_by_page = _questions_by_source_page(layout)
    failure_boxes = _failure_boxes_by_page(assertions)
    files: list[str] = []

    doc = fitz.open(str(pdf_path))
    try:
        for page_index, page in enumerate(doc):
            page_num = page_index + 1
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            draw = ImageDraw.Draw(image)
            scale_x = image.width / max(1.0, float(page.rect.width))
            scale_y = image.height / max(1.0, float(page.rect.height))

            for element in elements_by_page.get(page_num, []):
                bbox = _scale_bbox(element.get("bbox"), scale_x, scale_y)
                if not bbox:
                    continue
                color = GREEN if element.get("type") == "question_marker" else PURPLE
                width = 3 if element.get("type") == "question_marker" else 1
                label = f"{element.get('id')} {element.get('type')}"
                _draw_box(draw, bbox, color, label, width=width)

            for visual in visuals_by_page.get(page_num, []):
                bbox = _scale_bbox(visual.get("bbox"), scale_x, scale_y)
                if bbox:
                    _draw_box(draw, bbox, BLUE, f"{visual.get('id')} visual", width=4)

            for question in questions_by_page.get(page_num, []):
                bbox = _scale_bbox(question.get("source_bbox"), scale_x, scale_y)
                if bbox:
                    _draw_box(draw, bbox, ORANGE, f"q{question.get('index')} source_bbox", width=5)

            for failure in failure_boxes.get(page_num, []):
                bbox = _scale_bbox(failure.get("bbox"), scale_x, scale_y)
                if bbox:
                    _draw_failure_box(image, bbox)
                    _draw_box(draw, bbox, RED, failure.get("label") or "failed assertion", width=4)

            _draw_legend(draw)
            file_path = out_dir / f"page{page_num}_overlay.png"
            image.save(file_path)
            files.append(str(file_path))
    finally:
        doc.close()
    return files


def _group_by_page(records: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for record in records:
        page = int(record.get("page") or 0)
        if page > 0:
            grouped.setdefault(page, []).append(record)
    return grouped


def _questions_by_source_page(layout: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for question in layout.get("questions") or []:
        page = int(question.get("source_page_start") or question.get("page_num") or 0)
        if page > 0:
            grouped.setdefault(page, []).append(question)
    return grouped


def _failure_boxes_by_page(assertions: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for failure in assertions.get("failures") or []:
        for box in failure.get("boxes") or []:
            page = int(box.get("page") or 0)
            if page > 0:
                grouped.setdefault(page, []).append({**box, "label": f"{failure.get('question')} {failure.get('kind')}"})
    return grouped


def _scale_bbox(value: Any, scale_x: float, scale_y: float) -> list[float] | None:
    if not isinstance(value, list | tuple) or len(value) != 4:
        return None
    try:
        x0, y0, x1, y1 = [float(item) for item in value]
    except (TypeError, ValueError):
        return None
    if x1 <= x0 or y1 <= y0:
        return None
    return [x0 * scale_x, y0 * scale_y, x1 * scale_x, y1 * scale_y]


def _draw_box(draw: ImageDraw.ImageDraw, bbox: list[float], color: tuple[int, int, int], label: str, *, width: int) -> None:
    box = [int(round(item)) for item in bbox]
    draw.rectangle(box, outline=color, width=width)
    text_x = box[0] + 3
    text_y = max(0, box[1] - 14)
    draw.rectangle([text_x - 2, text_y, text_x + min(760, len(label) * 7), text_y + 13], fill=(255, 255, 255))
    draw.text((text_x, text_y), label[:120], fill=color)


def _draw_failure_box(image: Image.Image, bbox: list[float]) -> None:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle([int(round(item)) for item in bbox], fill=(220, 30, 30, 70))
    image.paste(Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB"))


def _draw_legend(draw: ImageDraw.ImageDraw) -> None:
    entries = [
        ("orange source_bbox", ORANGE),
        ("blue visual bbox", BLUE),
        ("green question marker", GREEN),
        ("purple LayoutElement", PURPLE),
        ("red failed assertion", RED),
    ]
    x0, y0 = 8, 8
    draw.rectangle([4, 4, 230, 88], fill=(255, 255, 255), outline=(90, 90, 90))
    for index, (label, color) in enumerate(entries):
        y = y0 + index * 15
        draw.rectangle([x0, y + 2, x0 + 10, y + 11], outline=color, width=2)
        draw.text((x0 + 16, y), label, fill=color)
