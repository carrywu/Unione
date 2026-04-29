from __future__ import annotations

import base64
from io import BytesIO
from typing import List

import fitz

from models import PageContent, Region, TextBlock


PADDING = 10


def _clip_rect(page: fitz.Page, rect: fitz.Rect) -> fitz.Rect:
    page_rect = page.rect
    return fitz.Rect(
        max(page_rect.x0, rect.x0 - PADDING),
        max(page_rect.y0, rect.y0 - PADDING),
        min(page_rect.x1, rect.x1 + PADDING),
        min(page_rect.y1, rect.y1 + PADDING),
    )


def _snapshot_region(page: fitz.Page, rect: fitz.Rect, region_type: str) -> Region:
    clip = _clip_rect(page, rect)
    pix = page.get_pixmap(clip=clip, dpi=150)
    return Region(
        type=region_type,
        bbox=[clip.x0, clip.y0, clip.x1, clip.y1],
        base64=base64.b64encode(pix.tobytes("png")).decode("utf-8"),
    )


def _extract_image_regions(doc: fitz.Document, page: fitz.Page) -> List[Region]:
    regions: List[Region] = []
    for image in page.get_images(full=True):
      xref = image[0]
      for rect in page.get_image_rects(xref):
          if rect.width > 5 and rect.height > 5:
              regions.append(_snapshot_region(page, rect, "image"))
    return regions


def _extract_table_regions(page: fitz.Page) -> List[Region]:
    drawings = page.get_drawings()
    horizontal = []
    vertical = []
    for drawing in drawings:
        for item in drawing.get("items", []):
            if item[0] != "l":
                continue
            p1, p2 = item[1], item[2]
            if abs(p1.y - p2.y) < 1:
                horizontal.append((p1, p2))
            if abs(p1.x - p2.x) < 1:
                vertical.append((p1, p2))

    if len(horizontal) + len(vertical) <= 8:
        return []

    xs = [point.x for line in horizontal + vertical for point in line]
    ys = [point.y for line in horizontal + vertical for point in line]
    if not xs or not ys:
        return []

    rect = fitz.Rect(min(xs), min(ys), max(xs), max(ys))
    return [_snapshot_region(page, rect, "table")]


def extract_pages(pdf_path: str) -> List[PageContent]:
    doc = fitz.open(pdf_path)
    pages: List[PageContent] = []
    try:
        for index, page in enumerate(doc, start=1):
            blocks = []
            for block in page.get_text("blocks"):
                x0, y0, x1, y1, text, *_ = block
                if text.strip():
                    blocks.append(TextBlock(bbox=[x0, y0, x1, y1], text=text.strip()))

            regions = _extract_image_regions(doc, page)
            regions.extend(_extract_table_regions(page))
            pages.append(
                PageContent(
                    page_num=index,
                    text=page.get_text("text"),
                    blocks=blocks,
                    regions=regions,
                )
            )
    finally:
        doc.close()
    return pages
