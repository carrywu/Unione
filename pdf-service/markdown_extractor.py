from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

import fitz

from layout_models import LayoutElement, VisualBlock
from render_cv_fallback import detect_rendered_visual_blocks

CAPTION_RE = re.compile(r"^\s*(?:图\s*\d*|图\d+|表\s*\d*|表\d+)[：:、.\s].{0,120}$")
HEADING_RE = re.compile(
    r"^\s*(?:第[一二三四五六七八九十百千万\d]+章|[一二三四五六七八九十]+[、.]\s*|"
    r"\d{1,2}[．.]\s*(?!\d)|考法[一二三四五六七八九十\d]+)"
)
OPTION_RE = re.compile(r"^\s*[A-D][.．、]\s+\S+")
QUESTION_RE = re.compile(r"^\s*(?:(?:【\s*)?例\s*\d+\s*】?|第\s*\d+\s*题|\d{1,3}(?:[．、]|[.](?!\d))|[（(]\d{1,3}[）)])")
MATERIAL_RE = re.compile(r"(根据以下资料|根据下列资料|根据材料|阅读以下材料|根据所给资料|回答\s*\d{1,3}\s*[-—~至到]\s*\d{1,3}\s*题)")


def extract_pdf_to_markdown(pdf_path: str, output_dir: str) -> dict[str, Any]:
    output = Path(output_dir)
    image_dir = output / "images"
    image_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    elements: list[LayoutElement] = []
    visuals: list[VisualBlock] = []
    markdown_parts: list[str] = []
    order_index = 0

    try:
        for page_index, page in enumerate(doc):
            page_num = page_index + 1
            markdown_parts.append(f"\n<!-- page: {page_num} -->\n")
            blocks = page.get_text("dict").get("blocks", [])
            blocks.sort(key=lambda block: (round(block.get("bbox", [0, 0, 0, 0])[1], 1), block.get("bbox", [0, 0, 0, 0])[0]))
            page_elements: list[LayoutElement] = []

            for block_index, block in enumerate(blocks):
                bbox = [float(value) for value in block.get("bbox", [0, 0, 0, 0])]
                if block.get("type") == 1:
                    image_bytes = block.get("image")
                    if not image_bytes:
                        continue
                    visual_id = f"p{page_num}-img{len([v for v in visuals if v.page == page_num]) + 1}"
                    rel_path = f"images/{visual_id}.png"
                    (output / rel_path).write_bytes(image_bytes)
                    markdown = f"![image:{visual_id}]({rel_path})"
                    element = LayoutElement(
                        id=f"e{order_index}",
                        page=page_num,
                        type="image",
                        text=None,
                        bbox=bbox,
                        image_path=rel_path,
                        markdown=markdown,
                        order_index=order_index,
                    )
                    visual = VisualBlock(
                        id=visual_id,
                        page=page_num,
                        kind="image",
                        bbox=bbox,
                        image_path=rel_path,
                    )
                    elements.append(element)
                    page_elements.append(element)
                    visuals.append(visual)
                    markdown_parts.append(markdown)
                    order_index += 1
                    continue

                for line in block.get("lines", []):
                    text = _line_text(line)
                    if not text:
                        continue
                    line_bbox = [float(value) for value in line.get("bbox", bbox)]
                    for logical_line in _split_logical_lines(text):
                        element_type = _classify_text(logical_line)
                        markdown = _text_to_markdown(logical_line, element_type)
                        element = LayoutElement(
                            id=f"e{order_index}",
                            page=page_num,
                            type=element_type,
                            text=logical_line,
                            bbox=line_bbox,
                            image_path=None,
                            markdown=markdown,
                            order_index=order_index,
                        )
                        elements.append(element)
                        page_elements.append(element)
                        markdown_parts.append(markdown)
                        order_index += 1

            fallback_visuals = detect_rendered_visual_blocks(
                page,
                page_num,
                output,
                [visual.bbox for visual in visuals if visual.page == page_num],
            )
            for visual in fallback_visuals:
                markdown = f"![{visual.kind}:{visual.id}]({visual.image_path})"
                element = LayoutElement(
                    id=f"e{order_index}",
                    page=page_num,
                    type="table" if visual.kind == "table" else "image",
                    text=None,
                    bbox=visual.bbox,
                    image_path=visual.image_path,
                    markdown=markdown,
                    order_index=order_index,
                    confidence=0.65,
                )
                elements.append(element)
                page_elements.append(element)
                visuals.append(visual)
                markdown_parts.append(markdown)
                order_index += 1

            _attach_caption_and_context(page_elements, visuals)

        markdown = "\n\n".join(part for part in markdown_parts if part)
        return {
            "markdown": markdown,
            "elements": elements,
            "visuals": visuals,
            "pages": [{"page": index + 1} for index in range(len(doc))],
        }
    finally:
        doc.close()


def write_markdown_debug(payload: dict[str, Any], output_dir: str) -> None:
    output = Path(output_dir)
    debug = output / "debug"
    debug.mkdir(parents=True, exist_ok=True)
    (debug / "parse-debug.md").write_text(_debug_markdown(payload), encoding="utf-8")
    (debug / "layout-elements.json").write_text(
        json.dumps([asdict(item) for item in payload["elements"]], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (debug / "visuals.json").write_text(
        json.dumps([asdict(item) for item in payload["visuals"]], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _line_text(line: dict[str, Any]) -> str:
    spans = line.get("spans", [])
    return "".join(span.get("text", "") for span in spans).strip()


def _split_logical_lines(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    pattern = re.compile(r"(?=(?:(?:【\s*)?例\s*\d+\s*】?|第\s*\d+\s*题|[A-D][.．、]))")
    parts = [part.strip() for part in pattern.split(text) if part.strip()]
    return parts or [text]


def _classify_text(text: str) -> str:
    compact = " ".join(text.split())
    if CAPTION_RE.match(compact) and len(compact) <= 140:
        return "caption"
    if MATERIAL_RE.search(compact):
        return "material_marker"
    if OPTION_RE.match(compact):
        return "option"
    if QUESTION_RE.match(compact) and not _looks_like_heading(compact):
        return "question_marker"
    if _looks_like_heading(compact):
        return "heading"
    return "text"


def _looks_like_heading(text: str) -> bool:
    if "?" in text or "？" in text:
        return False
    return bool(HEADING_RE.match(text)) and not any(token in text for token in ["下列", "以下", "根据", "哪", "正确", "错误", "约为"])


def _text_to_markdown(text: str, element_type: str) -> str:
    if element_type == "heading":
        return f"## {text}"
    return text


def _attach_caption_and_context(page_elements: list[LayoutElement], visuals: list[VisualBlock]) -> None:
    by_id = {visual.id: visual for visual in visuals}
    visual_elements = [element for element in page_elements if element.type == "image" and element.markdown]
    text_elements = [element for element in page_elements if element.text]
    for visual_element in visual_elements:
        visual_id_match = re.search(r"image:(.*?)\]", visual_element.markdown or "")
        if not visual_id_match:
            continue
        visual = by_id.get(visual_id_match.group(1))
        if not visual:
            continue
        before = [item for item in text_elements if item.order_index < visual_element.order_index]
        after = [item for item in text_elements if item.order_index > visual_element.order_index]
        visual.nearby_text_before = _join_nearby(before[-3:])
        visual.nearby_text_after = _join_nearby(after[:3])
        caption = next((item.text for item in after[:2] if item.type == "caption"), None)
        if not caption:
            caption = next((item.text for item in before[-2:] if item.type == "caption"), None)
        visual.caption = caption


def _join_nearby(elements: list[LayoutElement]) -> str | None:
    text = "\n".join(item.text or "" for item in elements).strip()
    return text or None


def _debug_markdown(payload: dict[str, Any]) -> str:
    lines = ["# Parse Debug", "", "## Markdown", "", payload["markdown"], "", "## Layout Elements"]
    for element in payload["elements"]:
        text = (element.text or element.markdown or "").replace("\n", " ")[:120]
        lines.append(f"- {element.id} type={element.type} page={element.page} bbox={element.bbox} text={text}")
    lines.extend(["", "## Visuals"])
    for visual in payload["visuals"]:
        lines.append(
            f"- {visual.id} page={visual.page} bbox={visual.bbox} caption={visual.caption or ''} "
            f"before={(visual.nearby_text_before or '')[:80]} after={(visual.nearby_text_after or '')[:80]}"
        )
    return "\n".join(lines)
