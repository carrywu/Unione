from __future__ import annotations

import re
from collections import defaultdict

from layout_models import ExerciseBlock, LayoutElement, QuestionCoreBlock, SharedMaterialBlock

QUESTION_RE = re.compile(
    r"^\s*(?:(?:【\s*)?例\s*(?P<ex>\d{1,3})\s*】?|第\s*(?P<q>\d{1,3})\s*题|"
    r"(?P<n>\d{1,3})(?:[．、]|[.](?!\d))|[（(](?P<p>\d{1,3})[）)])"
)
OPTION_RE = re.compile(r"^\s*([A-D])[.．、]\s*(.+)", re.S)
SOURCE_RE = re.compile(r"[（(](20\d{2}[^）)]{0,30})[）)]")
MATERIAL_RANGE_RE = re.compile(r"回答\s*(?:第\s*)?(\d{1,3})\s*[-—~至到]\s*(\d{1,3})\s*题")
MATERIAL_HINT_RE = re.compile(r"(根据以下资料|根据下列资料|根据材料|阅读以下材料|根据所给资料|回答\s*\d{1,3}\s*[-—~至到]\s*\d{1,3}\s*题)")
QUESTION_HINT_RE = re.compile(r"(以下|下列|哪|约|为|是|正确|错误|能够推出|根据图|根据表|下图|下表|上图|上表)")
TEACHING_TEXT_RE = re.compile(
    r"(考法[一二三四五六七八九十\d]+|问法[一二三四五六七八九十\d]+|专项讲解|思路点拨|知识点|"
    r"核心提示|方法技巧|易错点|答案解析|参考答案)"
)
VISUAL_REQUIRED_RE = re.compile(r"(根据.*?(资料|图|表)|上图|上表|下图|下表|图中|表中)")
HEADER_FOOTER_RE = re.compile(r"^(?:\d{1,4}|.*(?:资料分析题库|夸夸刷|第[一二三四五六七八九十百千万\d]+章).*)$")


def segment_question_cores(elements: list[LayoutElement], markdown: str) -> list[QuestionCoreBlock]:
    markers = [element for element in elements if _is_question_marker(element)]
    cores: list[QuestionCoreBlock] = []
    for marker_index, marker in enumerate(markers):
        next_marker = markers[marker_index + 1] if marker_index + 1 < len(markers) else None
        block_elements = [
            element
            for element in elements
            if element.order_index >= marker.order_index
            and (next_marker is None or element.order_index < next_marker.order_index)
            and element.type != "heading"
        ]
        options: dict[str, str] = {}
        stem_parts: list[str] = []
        raw_parts: list[str] = []
        for element in block_elements:
            text = element.text or element.markdown or ""
            if not text:
                continue
            raw_parts.append(element.markdown or text)
            if _is_noise_text(text):
                continue
            option_match = OPTION_RE.match(text)
            if option_match:
                options[option_match.group(1)] = _clean_option(option_match.group(2))
                continue
            if options:
                continue
            if element.type in ("caption", "image", "table"):
                continue
            stem_parts.append(text)

        index = _question_index(marker.text or "")
        if index is None:
            continue
        stem = _clean_stem("\n".join(stem_parts), marker.text or "")
        if not _valid_question_core(stem, options, marker):
            continue
        warnings: list[str] = []
        if len(options) < 4:
            warnings.append("options_incomplete")
        block_text = "\n".join(raw_parts)
        internal_anchor_count = _question_anchor_count(block_text)
        if internal_anchor_count > 1:
            warnings.append("multiple_question_anchors")
        if TEACHING_TEXT_RE.search(block_text):
            warnings.append("teaching_text_mixed")
        source_match = SOURCE_RE.search(stem)
        source = source_match.group(1) if source_match else None
        cores.append(
            QuestionCoreBlock(
                id=f"q{index}-{len(cores) + 1}",
                index=index,
                source=source,
                page_start=min(item.page for item in block_elements),
                page_end=max(item.page for item in block_elements),
                marker_text=marker.text or "",
                stem_text=stem,
                options=options,
                element_ids=[item.id for item in block_elements],
                bbox_range=[item.bbox for item in block_elements if item.page == marker.page],
                raw_markdown="\n\n".join(raw_parts),
                warnings=warnings,
            )
        )
    return cores


def segment_shared_materials(elements: list[LayoutElement], question_cores: list[QuestionCoreBlock]) -> list[SharedMaterialBlock]:
    materials: list[SharedMaterialBlock] = []
    question_start_by_index = {core.index: min(_element_order(elements, core.element_ids), default=10**9) for core in question_cores}
    for element in elements:
        text = element.text or ""
        if not MATERIAL_HINT_RE.search(text):
            continue
        range_match = MATERIAL_RANGE_RE.search(text)
        question_range = None
        end_order = None
        if range_match:
            start, end = int(range_match.group(1)), int(range_match.group(2))
            if start <= end:
                question_range = (start, end)
                end_order = question_start_by_index.get(start)
        material_elements = [
            item
            for item in elements
            if item.order_index >= element.order_index
            and (end_order is None or item.order_index < end_order)
            and item.type not in ("heading", "question_marker", "option")
        ]
        if not material_elements:
            material_elements = [element]
        materials.append(
            SharedMaterialBlock(
                id=f"m{len(materials) + 1}",
                title=None,
                content="\n".join(item.text or item.markdown or "" for item in material_elements).strip(),
                question_range=question_range,
                page_start=min(item.page for item in material_elements),
                page_end=max(item.page for item in material_elements),
                visual_ids=[],
                element_ids=[item.id for item in material_elements],
                raw_markdown="\n\n".join(item.markdown or item.text or "" for item in material_elements),
                warnings=[] if question_range else ["material_range_uncertain"],
            )
        )
    return materials


def build_exercise_blocks(
    question_cores: list[QuestionCoreBlock],
    materials: list[SharedMaterialBlock],
    visual_assignments: dict[str, list[str]],
) -> list[ExerciseBlock]:
    exercises: list[ExerciseBlock] = []
    for core in question_cores:
        material = _material_for_question(core.index, materials)
        visual_ids = visual_assignments.get(core.id, [])
        page_values = [core.page_start, core.page_end]
        if material:
            page_values.extend([material.page_start, material.page_end])
        warnings = list(core.warnings)
        if material:
            warnings.extend(material.warnings)
        if VISUAL_REQUIRED_RE.search(core.stem_text) and not material and not visual_ids:
            warnings.append("material_or_visual_missing")
        confidence = _parse_confidence(core, bool(visual_ids), warnings)
        raw_parts = [core.raw_markdown]
        if material:
            raw_parts.append(f"\n\n<!-- material: {material.id} -->\n{material.raw_markdown[:1200]}")
        if visual_ids:
            raw_parts.append(f"\n\n<!-- visuals: {', '.join(visual_ids)} -->")
        exercises.append(
            ExerciseBlock(
                id=f"ex-{core.id}",
                question_core=core,
                material_id=material.id if material else None,
                visual_ids=visual_ids,
                page_range=(min(page_values), max(page_values)),
                source_bbox=_source_bbox(core),
                source_anchor_text=core.marker_text,
                raw_markdown="\n".join(raw_parts),
                parse_confidence=confidence,
                warnings=warnings,
            )
        )
    return exercises


def _is_question_marker(element: LayoutElement) -> bool:
    text = element.text or ""
    if element.type == "heading":
        return False
    if not QUESTION_RE.match(text):
        return False
    return element.type == "question_marker" or bool(QUESTION_HINT_RE.search(text))


def _question_index(text: str) -> int | None:
    match = QUESTION_RE.match(text)
    if not match:
        return None
    value = next((group for group in match.groupdict().values() if group), None)
    return int(value) if value else None


def _valid_question_core(stem: str, options: dict[str, str], marker: LayoutElement) -> bool:
    if len(options) >= 2:
        return True
    return bool(QUESTION_HINT_RE.search(stem or marker.text or ""))


def _clean_stem(text: str, marker_text: str) -> str:
    text = TEACHING_TEXT_RE.split(text, maxsplit=1)[0]
    text = re.sub(
        r"^\s*(?:(?:【\s*)?例\s*\d+\s*】?|第\s*\d+\s*题|\d{1,3}(?:[．、]|[.](?!\d))|[（(]\d{1,3}[）)])\s*",
        "",
        text,
    )
    text = re.sub(r"(?m)^\s*(?:图\s*\d*|表\s*\d*)[：:、.\s].*$", "", text)
    return _strip_orphan_corner_brackets(re.sub(r"\n{2,}", "\n", text)).strip()


def _strip_orphan_corner_brackets(text: str) -> str:
    lines = [line for line in text.splitlines() if line.strip() not in {"【", "】"}]
    text = "\n".join(lines).strip()
    text = re.sub(r"^\s*】+", "", text).strip()
    text = re.sub(r"【+\s*$", "", text).strip()
    return text


def _clean_option(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _is_noise_text(text: str) -> bool:
    compact = re.sub(r"\s+", "", str(text or ""))
    if not compact:
        return True
    return bool(HEADER_FOOTER_RE.match(compact))


def _element_order(elements: list[LayoutElement], ids: list[str]) -> list[int]:
    wanted = set(ids)
    return [element.order_index for element in elements if element.id in wanted]


def _material_for_question(index: int, materials: list[SharedMaterialBlock]) -> SharedMaterialBlock | None:
    for material in materials:
        if material.question_range and material.question_range[0] <= index <= material.question_range[1]:
            return material
    return None


def _parse_confidence(core: QuestionCoreBlock, has_visual: bool, warnings: list[str]) -> float:
    score = 0.0
    score += 0.2 if core.index else 0.0
    score += 0.2 if len(core.stem_text.strip()) >= 12 else 0.08
    if len(core.options) >= 4:
        score += 0.2
    elif len(core.options) >= 2:
        score += 0.1
    if not VISUAL_REQUIRED_RE.search(core.stem_text) or has_visual:
        score += 0.2
    score += 0.1 if core.bbox_range else 0.0
    score += 0.1

    unique_warnings = set(warnings)
    if "multiple_question_anchors" in unique_warnings:
        score = min(score, 0.4)
    if "options_incomplete" in unique_warnings:
        score = min(score, 0.6)
    if "teaching_text_mixed" in unique_warnings:
        score = min(score, 0.7)
    if "material_or_visual_missing" in unique_warnings or "visual_hint_without_image" in unique_warnings:
        score = min(score, 0.65)
    if core.page_end - core.page_start > 1:
        score = min(score, 0.6)
    score -= min(0.25, 0.05 * len(unique_warnings))
    return max(0.0, min(1.0, round(score, 2)))


def _question_anchor_count(text: str) -> int:
    return len([line for line in text.splitlines() if QUESTION_RE.match(line.strip())])


def _source_bbox(core: QuestionCoreBlock) -> list[float] | None:
    boxes = [bbox for bbox in core.bbox_range if bbox and len(bbox) == 4]
    if not boxes:
        return None
    return [
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    ]
