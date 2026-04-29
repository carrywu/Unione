from __future__ import annotations

import base64
import re

import fitz
from PIL import Image

import ai_client
from answer_models import AnswerCandidate
from extractor import PDFExtractor


ANCHOR_RE = re.compile(
    r"【\s*例\s*(\d{1,4})\s*】|例\s*(\d{1,4})\s*[：:]|第\s*(\d{1,4})\s*题|^\s*(\d{1,4})\s*[\.、．]",
    re.M,
)
SECTION_RE = re.compile(r"(第[一二三四五六七八九十百千万\d]+[章节部分篇][^\n]{0,30})")


class ImageAnswerStrategy:
    def parse(self, extractor: PDFExtractor) -> list[AnswerCandidate]:
        candidates: list[AnswerCandidate] = []
        current_section: str | None = None
        fallback_index = 1
        fallback_started = False

        for page_index in range(extractor.total_pages):
            page = extractor.doc[page_index]
            page_num = page_index + 1
            text = extractor.get_page_text(page_index)
            current_section = self._detect_section(text) or current_section
            blocks = self._find_color_note_blocks(page, fallback_started)
            if blocks:
                if not fallback_started:
                    fallback_started = True
                    if candidates and all(self._is_numeric_page_anchor(item.raw_text) for item in candidates):
                        candidates.clear()
                        fallback_index = 1
                for rect in blocks:
                    image = self._render_rect(page, rect)
                    candidates.append(
                        AnswerCandidate(
                            section_key=current_section,
                            question_index=fallback_index,
                            question_anchor=f"顺序题块{fallback_index}",
                            analysis_image_base64=image["base64"],
                            image_width=image["width"],
                            image_height=image["height"],
                            source_page_num=page_num,
                            source_bbox=[rect.x0, rect.y0, rect.x1, rect.y1],
                            raw_text="color_note_block_fallback",
                            confidence=72,
                            parse_mode="image",
                        )
                    )
                    fallback_index += 1
                continue

            anchors = self._find_anchor_rects(page)

            if not anchors:
                anchors = self._find_visual_anchor_rects(page)
            if not anchors:
                continue

            for pos, anchor in enumerate(anchors):
                next_anchor = anchors[pos + 1] if pos + 1 < len(anchors) else None
                rect = self._block_rect(page.rect, anchor["bbox"], next_anchor["bbox"] if next_anchor else None)
                if rect.height < 20 or rect.width < 80:
                    continue
                image = self._render_rect(page, rect)
                confidence = self._score(rect, page.rect, current_section, pos, anchors)
                candidates.append(
                    AnswerCandidate(
                        section_key=current_section,
                        question_index=anchor["index"],
                        question_anchor=anchor["text"],
                        analysis_image_base64=image["base64"],
                        image_width=image["width"],
                        image_height=image["height"],
                        source_page_num=page_num,
                        source_bbox=[rect.x0, rect.y0, rect.x1, rect.y1],
                        raw_text=anchor["text"],
                        confidence=confidence,
                        parse_mode="image",
                    )
                )
                fallback_index = max(fallback_index, anchor["index"] + 1)

        return candidates

    def _is_numeric_page_anchor(self, text: str | None) -> bool:
        return bool(re.fullmatch(r"\s*\d+\s*[\.、．]\s*", text or ""))

    def _detect_section(self, text: str) -> str | None:
        for line in text.splitlines():
            stripped = line.strip()
            if len(stripped) > 48:
                continue
            match = SECTION_RE.search(stripped)
            if match:
                return re.sub(r"\s+", "_", match.group(1).strip(" ：:"))
        return None

    def _find_anchor_rects(self, page: fitz.Page) -> list[dict]:
        anchors: list[dict] = []
        for match in ANCHOR_RE.finditer(page.get_text("text")):
            anchor_text = match.group(0).strip()
            index_text = next(group for group in match.groups() if group)
            if int(index_text) <= 0:
                continue
            rects = page.search_for(anchor_text)
            if not rects:
                rects = page.search_for(index_text)
            if not rects:
                continue
            rect = min(rects, key=lambda item: (item.y0, item.x0))
            anchors.append({"index": int(index_text), "text": anchor_text, "bbox": rect})
        return self._dedupe_anchors(anchors)

    def _find_visual_anchor_rects(self, page: fitz.Page) -> list[dict]:
        image = self._render_page(page)
        raw_anchors = ai_client.parse_answer_anchors_visual(image["base64"])
        if not raw_anchors:
            return []

        scale_x = page.rect.width / max(image["width"], 1)
        scale_y = page.rect.height / max(image["height"], 1)
        anchors: list[dict] = []
        for item in raw_anchors:
            bbox = item.get("bbox") or []
            if len(bbox) != 4:
                continue
            rect = fitz.Rect(
                float(bbox[0]) * scale_x,
                float(bbox[1]) * scale_y,
                float(bbox[2]) * scale_x,
                float(bbox[3]) * scale_y,
            ) & page.rect
            if rect.is_empty or rect.width < 2 or rect.height < 2:
                continue
            anchors.append(
                {
                    "index": int(item["question_index"]),
                    "text": str(item.get("anchor_text") or f"例{item['question_index']}"),
                    "bbox": rect,
                    "source": "vision",
                }
            )
        return self._dedupe_anchors(anchors)

    def _block_rect(self, page_rect: fitz.Rect, anchor: fitz.Rect, next_anchor: fitz.Rect | None) -> fitz.Rect:
        bottom = next_anchor.y0 if next_anchor else page_rect.y1
        return fitz.Rect(
            page_rect.x0 + 24,
            max(page_rect.y0, anchor.y0 - 8),
            page_rect.x1 - 24,
            min(page_rect.y1, bottom - 4),
        )

    def _render_rect(self, page: fitz.Page, rect: fitz.Rect) -> dict:
        mat = fitz.Matrix(150 / 72, 150 / 72)
        pix = page.get_pixmap(matrix=mat, clip=rect)
        return {
            "base64": base64.b64encode(pix.tobytes("png")).decode("utf-8"),
            "width": pix.width,
            "height": pix.height,
        }

    def _render_page(self, page: fitz.Page) -> dict:
        mat = fitz.Matrix(150 / 72, 150 / 72)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        return {
            "base64": base64.b64encode(pix.tobytes("png")).decode("utf-8"),
            "width": pix.width,
            "height": pix.height,
        }

    def _find_color_note_blocks(self, page: fitz.Page, fallback_started: bool) -> list[fitz.Rect]:
        blocks: list[tuple[fitz.Rect, float, float]] = []
        for image_info in page.get_images(full=True):
            for rect in page.get_image_rects(image_info[0]):
                if rect.width < page.rect.width * 0.75:
                    continue
                if rect.height < 120:
                    continue
                # The first band in these note PDFs is usually a repeated page
                # header. The answer blocks start below it.
                if rect.y0 < page.rect.height * 0.14:
                    continue
                color_ratio, dark_ratio = self._block_color_stats(page, rect)
                if color_ratio >= 0.012 or (fallback_started and dark_ratio >= 0.035):
                    blocks.append((rect, color_ratio, dark_ratio))

        # Do not start on black-and-white TOC pages. Once a colorful note page is
        # found, keep accepting darker blocks because some examples are mostly
        # printed tables with only tiny handwritten marks.
        if not fallback_started and sum(1 for _, color_ratio, _ in blocks if color_ratio >= 0.02) < 2:
            return []

        deduped: list[fitz.Rect] = []
        for rect, _, _ in sorted(blocks, key=lambda item: (item[0].y0, item[0].x0)):
            if any(rect.intersects(existing) and (rect & existing).get_area() / max(rect.get_area(), 1.0) > 0.8 for existing in deduped):
                continue
            deduped.append(rect)
        return deduped

    def _block_color_stats(self, page: fitz.Page, rect: fitz.Rect) -> tuple[float, float]:
        pix = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5), clip=rect, alpha=False)
        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        total = max(pix.width * pix.height, 1)
        color = 0
        dark = 0
        for red, green, blue in image.getdata():
            if max(red, green, blue) - min(red, green, blue) > 35 and max(red, green, blue) > 80:
                color += 1
            if min(red, green, blue) < 210:
                dark += 1
        return color / total, dark / total

    def _dedupe_anchors(self, anchors: list[dict]) -> list[dict]:
        unique: list[dict] = []
        seen: set[tuple[int, int, int]] = set()
        for anchor in sorted(anchors, key=lambda item: (item["bbox"].y0, item["bbox"].x0)):
            key = (anchor["index"], round(anchor["bbox"].y0), round(anchor["bbox"].x0))
            if key not in seen:
                seen.add(key)
                unique.append(anchor)
        return unique

    def _score(
        self,
        rect: fitz.Rect,
        page_rect: fitz.Rect,
        section_key: str | None,
        pos: int,
        anchors: list[dict],
    ) -> int:
        score = 40
        if rect.width > page_rect.width * 0.6 and rect.height > 40:
            score += 20
        if section_key:
            score += 10
        if 40 <= rect.height <= page_rect.height * 0.9:
            score += 10
        if pos == 0 or anchors[pos]["index"] >= anchors[pos - 1]["index"]:
            score += 10
        if rect.height < 30:
            score = min(score, 60)
        return max(0, min(100, score))
