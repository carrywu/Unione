from __future__ import annotations

import re
from collections import Counter, defaultdict

from models import PageContent
from parser_kernel.types import PageElement


STATIC_HEADER_FOOTER_RE = re.compile(
    r"^(?:\d{1,4}|[-—]?\s*\d{1,4}\s*[-—]?|.*(?:资料分析题库|夸夸刷|原创笔记|倒卖搬运|目录|第[一二三四五六七八九十百千万\d]+[章节]).*)$"
)


def normalize_pages(pages: list[PageContent]) -> list[PageElement]:
    repeated_header_footer = _detect_repeated_header_footer(pages)
    elements: list[PageElement] = []
    order_index = 0
    for page in pages:
        sorted_blocks = sorted(page.blocks, key=lambda block: (block.bbox[1], block.bbox[0]))
        for block in sorted_blocks:
            text = block.text.strip()
            if not text:
                continue
            if _is_header_footer_text(text, repeated_header_footer):
                continue
            elements.append(
                PageElement(
                    page_num=page.page_num,
                    order_index=order_index,
                    bbox=list(block.bbox),
                    text=text,
                )
            )
            order_index += 1
    return elements


def _detect_repeated_header_footer(pages: list[PageContent]) -> set[str]:
    candidates: Counter[str] = Counter()
    seen_by_page: defaultdict[int, set[str]] = defaultdict(set)
    for page in pages:
        page_height = _page_height(page)
        top_limit = page_height * 0.08
        bottom_limit = page_height * 0.94
        for block in page.blocks:
            text = _normalize_header_footer_text(block.text)
            if not text or len(text) > 80:
                continue
            y0 = float(block.bbox[1]) if len(block.bbox) > 1 else 0.0
            y1 = float(block.bbox[3]) if len(block.bbox) > 3 else y0
            if y0 <= top_limit or y1 >= bottom_limit:
                seen_by_page[page.page_num].add(text)
    for page_candidates in seen_by_page.values():
        candidates.update(page_candidates)
    return {text for text, count in candidates.items() if count > 3}


def _is_header_footer_text(text: str, repeated_header_footer: set[str]) -> bool:
    normalized = _normalize_header_footer_text(text)
    if not normalized:
        return False
    if normalized in repeated_header_footer:
        return True
    return bool(STATIC_HEADER_FOOTER_RE.match(normalized))


def _normalize_header_footer_text(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "").strip())


def _page_height(page: PageContent) -> float:
    bottoms = [float(block.bbox[3]) for block in page.blocks if len(block.bbox) > 3]
    bottoms.extend(float(region.bbox[3]) for region in page.regions if len(region.bbox) > 3)
    return max(bottoms or [1000.0], default=1000.0)
