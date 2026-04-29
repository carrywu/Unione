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
VISUAL_LABEL_RE = re.compile(r"^\s*(?:图\s*\d*|图\d+|表\s*\d*|表\d+|资料图)\s*$")
VISUAL_UNIT_RE = re.compile(r"(?:单位|注|备注|来源|数据来源)\s*[:：]")
VISUAL_TITLE_KEYWORD_RE = re.compile(r"(亿元|万美元|万人|%|同比|增速|规模|产量|营业额|总额|比重|预测|情况)")
VISUAL_YEAR_TITLE_RE = re.compile(r"20\d{2}.*20\d{2}.*(规模|产量|总额|比重|预测|情况|营业额|增长)")
HEADING_RE = re.compile(
    r"^\s*(?:第[一二三四五六七八九十百千万\d]+章|[一二三四五六七八九十]+[、.]\s*|"
    r"\d{1,2}[．.]\s*(?!\d)|考法[一二三四五六七八九十\d]+)"
)
OPTION_RE = re.compile(r"^\s*[A-D][.．、]\s+\S+")
QUESTION_RE = re.compile(r"^\s*(?:(?:【\s*)?例\s*\d+\s*】?|第\s*\d+\s*题|\d{1,3}(?:[．、]|[.](?!\d))|[（(]\d{1,3}[）)])")
MATERIAL_RE = re.compile(r"(根据以下资料|根据下列资料|根据材料|阅读以下材料|根据所给资料|回答\s*\d{1,3}\s*[-—~至到]\s*\d{1,3}\s*题)")
QUESTION_TEXT_RE = re.compile(
    r"(?:哪|下列|以下|正确|错误|推出|保持|首次|超过|将|则|翻一番|计算|按照|第\s*\d+\s*题|例\s*\d+|[A-D][.．、])"
)


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

            _expand_visual_blocks(page, page_elements, visuals, output)
            _merge_page_visual_fragments(page, page_elements, visuals, output)
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
    if MATERIAL_RE.search(compact):
        return "material_marker"
    if OPTION_RE.match(compact):
        return "option"
    if QUESTION_RE.match(compact) and not _looks_like_heading(compact):
        return "question_marker"
    if _looks_like_visual_caption(compact):
        return "caption"
    if _looks_like_heading(compact):
        return "heading"
    return "text"


def _looks_like_visual_caption(text: str) -> bool:
    compact = " ".join(str(text or "").split())
    if not compact:
        return False
    if QUESTION_RE.match(compact) or QUESTION_TEXT_RE.search(compact):
        return False
    if CAPTION_RE.match(compact) and len(compact) <= 160:
        return True
    if VISUAL_LABEL_RE.match(compact):
        return True
    if VISUAL_UNIT_RE.search(compact):
        return True
    if VISUAL_YEAR_TITLE_RE.search(compact):
        return True
    if re.search(r"20\d{2}", compact) and VISUAL_TITLE_KEYWORD_RE.search(compact) and len(compact) <= 180:
        return True
    return False


def _looks_like_heading(text: str) -> bool:
    if "?" in text or "？" in text:
        return False
    return bool(HEADING_RE.match(text)) and not any(token in text for token in ["下列", "以下", "根据", "哪", "正确", "错误", "约为"])


def _text_to_markdown(text: str, element_type: str) -> str:
    if element_type == "heading":
        return f"## {text}"
    return text


def _expand_visual_blocks(page: fitz.Page, page_elements: list[LayoutElement], visuals: list[VisualBlock], output: Path) -> None:
    page_visuals = sorted(
        [visual for visual in visuals if visual.page == page.number + 1],
        key=lambda item: ((item.raw_bbox or item.bbox)[1], (item.raw_bbox or item.bbox)[0]),
    )
    text_elements = [element for element in page_elements if element.text]
    processed: list[VisualBlock] = []
    for visual in page_visuals:
        raw_bbox = list(visual.raw_bbox or visual.bbox)
        visual.raw_bbox = raw_bbox
        absorbed = _absorbed_visual_texts(raw_bbox, text_elements)
        if not absorbed:
            absorbed = _continuation_visual_caption_texts(raw_bbox, processed, text_elements)
        expanded_bbox = _expanded_visual_bbox(page, raw_bbox, absorbed)
        visual.expanded_bbox = expanded_bbox
        visual.absorbed_texts = [_absorbed_text_payload(element) for element in absorbed]
        visual.bbox = expanded_bbox
        if absorbed and not visual.caption:
            visual.caption = "\n".join(element.text or "" for element in absorbed).strip() or None
        _clip_page_to_path(page, fitz.Rect(expanded_bbox), output / visual.image_path)
        processed.append(visual)


def _merge_page_visual_fragments(page: fitz.Page, page_elements: list[LayoutElement], visuals: list[VisualBlock], output: Path) -> None:
    page_num = page.number + 1
    text_elements = [element for element in page_elements if element.text]
    page_visuals = sorted(
        [visual for visual in visuals if visual.page == page_num],
        key=lambda item: ((item.raw_bbox or item.bbox)[1], (item.raw_bbox or item.bbox)[0]),
    )
    if len(page_visuals) < 2:
        return

    merged: list[VisualBlock] = []
    index = 0
    group_index = 1
    while index < len(page_visuals):
        group = [page_visuals[index]]
        index += 1
        while index < len(page_visuals) and _can_merge_visual_fragments(group[-1], page_visuals[index], text_elements):
            group.append(page_visuals[index])
            index += 1
        if len(group) == 1:
            merged.append(group[0])
            continue
        merged.append(_merge_visual_group(page, group, output, group_index))
        group_index += 1

    visuals[:] = [visual for visual in visuals if visual.page != page_num] + merged


def _can_merge_visual_fragments(previous: VisualBlock, current: VisualBlock, text_elements: list[LayoutElement]) -> bool:
    previous_raw = previous.raw_bbox or previous.bbox
    current_raw = current.raw_bbox or current.bbox
    if previous.page != current.page:
        return False
    if _x_overlap_ratio(previous_raw, current_raw) <= 0.75:
        return False
    if abs(float(previous_raw[0]) - float(current_raw[0])) > 24.0 or abs(float(previous_raw[2]) - float(current_raw[2])) > 24.0:
        return False
    gap = _y_gap(previous_raw, current_raw)
    if not _shared_absorbed_caption(previous, current):
        return False
    if gap > 60.0:
        return False
    return not _blocked_by_question_text(previous_raw[3], current_raw[1], text_elements)


def _merge_visual_group(page: fitz.Page, group: list[VisualBlock], output: Path, group_index: int) -> VisualBlock:
    base = group[0]
    raw_boxes = [visual.raw_bbox or visual.bbox for visual in group]
    expanded_boxes = [visual.expanded_bbox or visual.bbox for visual in group]
    raw_bbox = _union_boxes(raw_boxes)
    expanded_bbox = _clip_bbox_to_page(_union_boxes(expanded_boxes), page)
    group_id = base.same_visual_group_id or f"vg_p{base.page}_{group_index}"
    absorbed_texts = _unique_absorbed_texts(group)
    child_ids = [
        child_id
        for visual in group
        for child_id in (visual.child_visual_ids or [visual.id])
    ]

    base.raw_bbox = raw_bbox
    base.expanded_bbox = expanded_bbox
    base.bbox = expanded_bbox
    base.same_visual_group_id = group_id
    base.child_visual_ids = child_ids
    base.absorbed_texts = absorbed_texts
    base.caption = _merged_caption(group, absorbed_texts)
    _clip_page_to_path(page, fitz.Rect(expanded_bbox), output / base.image_path)
    return base


def _union_boxes(boxes: list[list[float]]) -> list[float]:
    return [
        min(float(box[0]) for box in boxes),
        min(float(box[1]) for box in boxes),
        max(float(box[2]) for box in boxes),
        max(float(box[3]) for box in boxes),
    ]


def _clip_bbox_to_page(bbox: list[float], page: fitz.Page) -> list[float]:
    rect = fitz.Rect(bbox) & page.rect
    return [rect.x0, rect.y0, rect.x1, rect.y1]


def _unique_absorbed_texts(group: list[VisualBlock]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for visual in group:
        for item in visual.absorbed_texts:
            key = (str(item.get("id") or ""), str(item.get("text") or ""))
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
    return result


def _merged_caption(group: list[VisualBlock], absorbed_texts: list[dict[str, Any]]) -> str | None:
    parts: list[str] = []
    for item in absorbed_texts:
        text = str(item.get("text") or "").strip()
        if text and text not in parts:
            parts.append(text)
    for visual in group:
        text = str(visual.caption or "").strip()
        if text and text not in parts:
            parts.append(text)
    return "\n".join(parts) or None


def _shared_absorbed_caption(left: VisualBlock, right: VisualBlock) -> bool:
    left_texts = {str(item.get("text") or "").strip() for item in left.absorbed_texts if str(item.get("text") or "").strip()}
    right_texts = {str(item.get("text") or "").strip() for item in right.absorbed_texts if str(item.get("text") or "").strip()}
    return bool(left_texts & right_texts)


def _absorbed_visual_texts(raw_bbox: list[float], text_elements: list[LayoutElement]) -> list[LayoutElement]:
    caption_elements = [
        element
        for element in text_elements
        if element.bbox
        and len(element.bbox) == 4
        and element.type == "caption"
        and not _is_question_or_option_text(element.text or "")
    ]
    absorbed: list[LayoutElement] = []
    current_top = float(raw_bbox[1])
    current_bottom = float(raw_bbox[3])

    while True:
        above = [
            element
            for element in caption_elements
            if element not in absorbed
            and float(element.bbox[3]) <= current_top + 1.0
            and _x_near_or_overlaps(raw_bbox, element.bbox)
            and current_top - float(element.bbox[3]) <= 28.0
            and not _blocked_by_question_text(element.bbox[3], current_top, text_elements)
        ]
        if not above:
            break
        nearest_bottom = max(float(element.bbox[3]) for element in above)
        row = [
            element
            for element in above
            if abs(float(element.bbox[3]) - nearest_bottom) <= 2.0
            or _vertical_overlap_ratio(element.bbox, [raw_bbox[0], nearest_bottom - 2.0, raw_bbox[2], nearest_bottom + 2.0]) > 0
        ]
        for element in sorted(row, key=lambda item: (item.bbox[0], item.order_index)):
            absorbed.append(element)
            current_top = min(current_top, float(element.bbox[1]))

    while True:
        below = [
            element
            for element in caption_elements
            if element not in absorbed
            and float(element.bbox[1]) >= current_bottom - 1.0
            and _x_near_or_overlaps(raw_bbox, element.bbox)
            and float(element.bbox[1]) - current_bottom <= 28.0
            and not _blocked_by_question_text(current_bottom, element.bbox[1], text_elements)
        ]
        if not below:
            break
        nearest_top = min(float(element.bbox[1]) for element in below)
        row = [
            element
            for element in below
            if abs(float(element.bbox[1]) - nearest_top) <= 2.0
            or _vertical_overlap_ratio(element.bbox, [raw_bbox[0], nearest_top - 2.0, raw_bbox[2], nearest_top + 2.0]) > 0
        ]
        for element in sorted(row, key=lambda item: (item.bbox[0], item.order_index)):
            absorbed.append(element)
            current_bottom = max(current_bottom, float(element.bbox[3]))

    return sorted(absorbed, key=lambda item: (item.bbox[1], item.bbox[0], item.order_index))


def _continuation_visual_caption_texts(
    raw_bbox: list[float],
    processed_visuals: list[VisualBlock],
    text_elements: list[LayoutElement],
) -> list[LayoutElement]:
    by_id = {element.id: element for element in text_elements}
    for previous in reversed(processed_visuals):
        previous_raw = previous.raw_bbox or previous.bbox
        if not _same_visual_continuation(previous_raw, raw_bbox, text_elements):
            continue
        inherited: list[LayoutElement] = []
        for payload in previous.absorbed_texts:
            element = by_id.get(str(payload.get("id") or ""))
            if element and element.type == "caption":
                inherited.append(element)
        if inherited:
            return inherited
    return []


def _same_visual_continuation(previous_bbox: list[float], current_bbox: list[float], text_elements: list[LayoutElement]) -> bool:
    if not previous_bbox or not current_bbox:
        return False
    if _x_overlap_ratio(previous_bbox, current_bbox) < 0.75:
        return False
    if _y_gap(previous_bbox, current_bbox) > 8.0:
        return False
    return not _blocked_by_question_text(previous_bbox[3], current_bbox[1], text_elements)


def _expanded_visual_bbox(page: fitz.Page, raw_bbox: list[float], absorbed: list[LayoutElement]) -> list[float]:
    boxes = [raw_bbox, *[element.bbox for element in absorbed if element.bbox]]
    rect = fitz.Rect(
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )
    padding_x = 6.0
    padding_y = 4.0
    rect = fitz.Rect(rect.x0 - padding_x, rect.y0 - padding_y, rect.x1 + padding_x, rect.y1 + padding_y)
    rect = rect & page.rect
    return [rect.x0, rect.y0, rect.x1, rect.y1]


def _absorbed_text_payload(element: LayoutElement) -> dict[str, Any]:
    return {
        "id": element.id,
        "type": element.type,
        "text": element.text or "",
        "bbox": element.bbox,
        "order_index": element.order_index,
    }


def _x_near_or_overlaps(visual_bbox: list[float], text_bbox: list[float]) -> bool:
    page_band_left = min(visual_bbox[0], text_bbox[0])
    page_band_right = max(visual_bbox[2], text_bbox[2])
    horizontal_gap = max(0.0, max(visual_bbox[0], text_bbox[0]) - min(visual_bbox[2], text_bbox[2]))
    if horizontal_gap <= 36.0:
        return True
    visual_width = max(1.0, visual_bbox[2] - visual_bbox[0])
    text_width = max(1.0, text_bbox[2] - text_bbox[0])
    band_width = max(1.0, page_band_right - page_band_left)
    return visual_width / band_width >= 0.55 or text_width / band_width >= 0.55


def _x_overlap_ratio(left: list[float], right: list[float]) -> float:
    overlap = max(0.0, min(float(left[2]), float(right[2])) - max(float(left[0]), float(right[0])))
    width = max(1.0, min(float(left[2]) - float(left[0]), float(right[2]) - float(right[0])))
    return overlap / width


def _y_gap(left: list[float], right: list[float]) -> float:
    if float(left[3]) < float(right[1]):
        return float(right[1]) - float(left[3])
    if float(right[3]) < float(left[1]):
        return float(left[1]) - float(right[3])
    return 0.0


def _vertical_overlap_ratio(left: list[float], right: list[float]) -> float:
    overlap = max(0.0, min(float(left[3]), float(right[3])) - max(float(left[1]), float(right[1])))
    height = max(1.0, min(float(left[3]) - float(left[1]), float(right[3]) - float(right[1])))
    return overlap / height


def _blocked_by_question_text(top: float, bottom: float, text_elements: list[LayoutElement]) -> bool:
    lower, upper = sorted([float(top), float(bottom)])
    for element in text_elements:
        if not element.bbox or len(element.bbox) != 4:
            continue
        if float(element.bbox[1]) < lower - 0.5 or float(element.bbox[3]) > upper + 0.5:
            continue
        if element.type in {"question_marker", "option"} or _is_question_or_option_text(element.text or ""):
            return True
    return False


def _is_question_or_option_text(text: str) -> bool:
    compact = " ".join(str(text or "").split())
    return bool(QUESTION_RE.match(compact) or OPTION_RE.match(compact))


def _clip_page_to_path(page: fitz.Page, rect: fitz.Rect, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=rect, alpha=False)
    pix.save(path)


def _attach_caption_and_context(page_elements: list[LayoutElement], visuals: list[VisualBlock]) -> None:
    by_id = {visual.id: visual for visual in visuals}
    visual_elements = [element for element in page_elements if element.type in {"image", "table"} and element.markdown]
    text_elements = [element for element in page_elements if element.text]
    for visual_element in visual_elements:
        visual_id_match = re.search(r"(?:image|table|chart):(.*?)\]", visual_element.markdown or "")
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
