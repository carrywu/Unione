from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz
from PIL import Image

from layout_models import VisualBlock


def detect_rendered_visual_blocks(
    page: fitz.Page,
    page_num: int,
    output_dir: Path,
    existing_bboxes: list[list[float]],
) -> list[VisualBlock]:
    """Detect chart/table-like regions that are drawn as vectors.

    This is a light CV fallback that avoids OpenCV as a hard dependency:
    1. cluster PyMuPDF drawing rectangles/lines into candidate regions;
    2. if vector clustering is sparse, render the page and scan for dark
       connected regions that are not mostly covered by text.
    """
    visuals = _detect_vector_clusters(page, page_num, output_dir, existing_bboxes)
    if visuals:
        return visuals
    return _detect_rendered_dark_regions(page, page_num, output_dir, existing_bboxes)


def _detect_vector_clusters(
    page: fitz.Page,
    page_num: int,
    output_dir: Path,
    existing_bboxes: list[list[float]],
) -> list[VisualBlock]:
    rects: list[fitz.Rect] = []
    for drawing in page.get_drawings():
        rect = fitz.Rect(drawing.get("rect") or fitz.Rect())
        if rect.is_empty or rect.width < 12 or rect.height < 8:
            continue
        if _overlaps_any(rect, existing_bboxes):
            continue
        rects.append(rect)
    clusters = _cluster_rects(rects, gap=18)
    visuals: list[VisualBlock] = []
    for cluster in clusters:
        if cluster.width < 80 or cluster.height < 40:
            continue
        if _text_coverage(page, cluster) > 0.55:
            continue
        visual_id = f"p{page_num}-vec{len(visuals) + 1}"
        rel_path = f"images/{visual_id}.png"
        _clip_page(page, cluster, output_dir / rel_path)
        visuals.append(
            VisualBlock(
                id=visual_id,
                page=page_num,
                kind="chart",
                bbox=[cluster.x0, cluster.y0, cluster.x1, cluster.y1],
                image_path=rel_path,
                warnings=["render_cv_fallback_vector"],
            )
        )
    return visuals


def _detect_rendered_dark_regions(
    page: fitz.Page,
    page_num: int,
    output_dir: Path,
    existing_bboxes: list[list[float]],
) -> list[VisualBlock]:
    scale = 1.5
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples).convert("L")
    width, height = image.size
    cell = 24
    occupied: list[tuple[int, int]] = []
    for y in range(0, height, cell):
        for x in range(0, width, cell):
            crop = image.crop((x, y, min(x + cell, width), min(y + cell, height)))
            pixels = list(crop.getdata())
            dark_ratio = sum(1 for value in pixels if value < 190) / max(len(pixels), 1)
            if dark_ratio > 0.08:
                occupied.append((x // cell, y // cell))
    components = _grid_components(occupied)
    visuals: list[VisualBlock] = []
    for component in components:
        xs = [item[0] for item in component]
        ys = [item[1] for item in component]
        rect_px = fitz.Rect(
            min(xs) * cell,
            min(ys) * cell,
            (max(xs) + 1) * cell,
            (max(ys) + 1) * cell,
        )
        rect = fitz.Rect(rect_px.x0 / scale, rect_px.y0 / scale, rect_px.x1 / scale, rect_px.y1 / scale)
        if rect.width < 100 or rect.height < 50:
            continue
        if _overlaps_any(rect, existing_bboxes) or _text_coverage(page, rect) > 0.65:
            continue
        visual_id = f"p{page_num}-cv{len(visuals) + 1}"
        rel_path = f"images/{visual_id}.png"
        _clip_page(page, rect, output_dir / rel_path)
        visuals.append(
            VisualBlock(
                id=visual_id,
                page=page_num,
                kind="chart",
                bbox=[rect.x0, rect.y0, rect.x1, rect.y1],
                image_path=rel_path,
                warnings=["render_cv_fallback_raster"],
            )
        )
    return visuals[:4]


def _cluster_rects(rects: list[fitz.Rect], gap: float) -> list[fitz.Rect]:
    clusters: list[fitz.Rect] = []
    for rect in sorted(rects, key=lambda item: (item.y0, item.x0)):
        expanded = fitz.Rect(rect.x0 - gap, rect.y0 - gap, rect.x1 + gap, rect.y1 + gap)
        merged = False
        for index, cluster in enumerate(clusters):
            if expanded.intersects(cluster):
                clusters[index] = cluster | rect
                merged = True
                break
        if not merged:
            clusters.append(fitz.Rect(rect))
    return clusters


def _grid_components(cells: list[tuple[int, int]]) -> list[list[tuple[int, int]]]:
    remaining = set(cells)
    components: list[list[tuple[int, int]]] = []
    while remaining:
        start = remaining.pop()
        stack = [start]
        component = [start]
        while stack:
            x, y = stack.pop()
            for neighbor in [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]:
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    stack.append(neighbor)
                    component.append(neighbor)
        components.append(component)
    return components


def _text_coverage(page: fitz.Page, rect: fitz.Rect) -> float:
    words = page.get_text("words", clip=rect)
    if not words:
        return 0.0
    text_area = 0.0
    for word in words:
        word_rect = fitz.Rect(word[:4])
        text_area += max(0.0, word_rect.width * word_rect.height)
    return text_area / max(rect.width * rect.height, 1.0)


def _overlaps_any(rect: fitz.Rect, bboxes: list[list[float]]) -> bool:
    for bbox in bboxes:
        other = fitz.Rect(bbox)
        if rect.intersects(other) and (rect & other).get_area() / max(rect.get_area(), 1.0) > 0.45:
            return True
    return False


def _clip_page(page: fitz.Page, rect: fitz.Rect, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=rect, alpha=False)
    pix.save(path)
