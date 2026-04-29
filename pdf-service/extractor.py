from __future__ import annotations

import base64
from typing import Any

import fitz


class PDFExtractor:
    """Thin PyMuPDF utility wrapper with no question-parsing business logic."""

    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.doc = fitz.open(pdf_path)
        self.total_pages = len(self.doc)

    def get_page_text(self, page_num: int) -> str:
        """Extract plain text from one zero-based page."""
        return self.doc[page_num].get_text("text")

    def get_page_screenshot(self, page_num: int, dpi: int = 150) -> str:
        """Render a full page to PNG and return base64."""
        page = self.doc[page_num]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        return base64.b64encode(pix.tobytes("png")).decode("utf-8")

    def get_region_screenshot(
        self,
        page_num: int,
        rect: fitz.Rect,
        padding: int = 10,
    ) -> str:
        """Render a padded region to PNG and return base64."""
        page = self.doc[page_num]
        page_rect = page.rect
        padded = fitz.Rect(
            max(rect.x0 - padding, page_rect.x0),
            max(rect.y0 - padding, page_rect.y0),
            min(rect.x1 + padding, page_rect.x1),
            min(rect.y1 + padding, page_rect.y1),
        )
        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat, clip=padded)
        return base64.b64encode(pix.tobytes("png")).decode("utf-8")

    def get_page_images(self, page_num: int) -> list[dict[str, Any]]:
        """Return embedded image regions as base64 screenshots."""
        page = self.doc[page_num]
        results: list[dict[str, Any]] = []
        for image_info in page.get_images(full=True):
            xref = image_info[0]
            for rect in page.get_image_rects(xref):
                if rect.width <= 5 or rect.height <= 5:
                    continue
                results.append(
                    {
                        "bbox": rect,
                        "base64": self.get_region_screenshot(page_num, rect),
                    }
                )
        return results

    def get_page_tables(self, page_num: int) -> list[dict[str, Any]]:
        """Detect simple table-like line clusters and return screenshots."""
        page = self.doc[page_num]
        drawings = page.get_drawings()
        lines: list[fitz.Rect] = []

        for drawing in drawings:
            rect = drawing.get("rect")
            if isinstance(rect, fitz.Rect) and rect.width > 0 and rect.height > 0:
                drawing_type = drawing.get("type")
                if drawing_type in {"s", "f", "fs"}:
                    lines.append(rect)

            for item in drawing.get("items", []):
                if not item:
                    continue
                kind = item[0]
                if kind == "l" and len(item) >= 3:
                    p1, p2 = item[1], item[2]
                    lines.append(fitz.Rect(p1, p2).normalize())
                elif kind == "re" and len(item) >= 2:
                    lines.append(item[1])

        dense_lines = [
            rect
            for rect in lines
            if rect.width >= 20 or rect.height >= 20 or (rect.width * rect.height >= 200)
        ]
        if len(dense_lines) < 6:
            return []

        x0 = min(rect.x0 for rect in dense_lines)
        y0 = min(rect.y0 for rect in dense_lines)
        x1 = max(rect.x1 for rect in dense_lines)
        y1 = max(rect.y1 for rect in dense_lines)
        table_rect = fitz.Rect(x0, y0, x1, y1)
        if table_rect.width < 100 or table_rect.height < 50:
            return []

        return [
            {
                "bbox": table_rect,
                "base64": self.get_region_screenshot(page_num, table_rect),
            }
        ]

    def get_all_visual_elements(self, page_num: int) -> list[dict[str, Any]]:
        """Return image/table visual elements, avoiding obvious overlaps."""
        elements: list[dict[str, Any]] = []
        for image in self.get_page_images(page_num):
            elements.append({**image, "type": "image"})

        for table in self.get_page_tables(page_num):
            overlaps = any(table["bbox"].intersects(element["bbox"]) for element in elements)
            if not overlaps:
                elements.append({**table, "type": "table"})

        return elements

    def get_full_text(self) -> str:
        """Extract all text in reading order page-by-page."""
        return "\n".join(self.get_page_text(i) for i in range(self.total_pages))

    def close(self) -> None:
        self.doc.close()
