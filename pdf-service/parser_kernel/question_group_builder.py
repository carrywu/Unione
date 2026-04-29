from __future__ import annotations

import re

from parser_kernel.types import MaterialGroup, PageElement, QuestionGroup


INDEX_RE = re.compile(r"^\s*(?:(?:【\s*)?例\s*(\d+)\s*】?|第\s*(\d+)\s*题|(\d{1,3})(?:[．、]|[.](?!\d))|[（(](\d{1,3})[）)]).*")
RANGE_RE = re.compile(r"回答\s*(?:第\s*)?(\d{1,3})\s*[-—~至到]\s*(\d{1,3})\s*题")


def build_groups(elements: list[PageElement]) -> tuple[list[MaterialGroup], list[QuestionGroup]]:
    materials: list[MaterialGroup] = []
    questions: list[QuestionGroup] = []
    current_material: MaterialGroup | None = None
    current_question_parts: list[str] = []
    current_question: QuestionGroup | None = None

    def flush_question() -> None:
        nonlocal current_question, current_question_parts
        if current_question is None:
            return
        current_question.text = "\n".join(part for part in current_question_parts if part).strip()
        questions.append(current_question)
        current_question = None
        current_question_parts = []

    for element in elements:
        role = element.semantic_role
        text = element.text.strip()
        if role in {"directory_heading", "teaching_text"}:
            continue
        if role == "material_prompt":
            flush_question()
            match = RANGE_RE.search(text)
            question_range = None
            if match:
                question_range = (int(match.group(1)), int(match.group(2)))
            current_material = MaterialGroup(
                id=f"m{len(materials) + 1}",
                prompt_text=text,
                body_text="",
                question_range=question_range,
                warnings=[] if question_range else ["material_range_uncertain"],
            )
            materials.append(current_material)
            continue
        if role == "question_anchor":
            flush_question()
            match = INDEX_RE.match(text)
            if not match:
                continue
            index = next(int(group) for group in match.groups() if group)
            material_id = None
            if current_material and current_material.question_range:
                start, end = current_material.question_range
                if start <= index <= end:
                    material_id = current_material.id
            current_question = QuestionGroup(
                index=index,
                text="",
                page_num=element.page_num,
                y0=element.bbox[1],
                y1=element.bbox[3],
                material_id=material_id,
            )
            current_question_parts.append(text)
            continue
        if current_question is not None:
            current_question_parts.append(text)
            current_question.y1 = max(current_question.y1, element.bbox[3])
            continue
        if current_material is not None:
            current_material.body_text = "\n".join(
                part for part in [current_material.body_text, text] if part
            ).strip()

    flush_question()
    return materials, questions
