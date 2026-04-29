from __future__ import annotations

from models import PageContent
from parser_kernel.types import PageElement


def normalize_pages(pages: list[PageContent]) -> list[PageElement]:
    elements: list[PageElement] = []
    order_index = 0
    for page in pages:
        sorted_blocks = sorted(page.blocks, key=lambda block: (block.bbox[1], block.bbox[0]))
        for block in sorted_blocks:
            text = block.text.strip()
            if not text:
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
