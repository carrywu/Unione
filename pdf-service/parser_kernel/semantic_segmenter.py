from __future__ import annotations

import re

from parser_kernel.types import PageElement


QUESTION_ANCHOR_RE = re.compile(
    r"^\s*(?:(?:【\s*)?例\s*\d+\s*】?|第\s*\d+\s*题|\d{1,3}(?:[．、]|[.](?!\d))|[（(]\d{1,3}[）)]).*"
)
OPTION_RE = re.compile(r"^\s*[A-D][．.、。]\s*")
MATERIAL_PROMPT_RE = re.compile(
    r"(根据以下资料|根据下列资料|根据材料|阅读以下材料|根据所给资料|回答\s*(?:第\s*)?\d{1,3}\s*[-—~至到]\s*\d{1,3}\s*题)"
)
DIRECTORY_RE = re.compile(r"^.{1,60}\.{4,}\s*\d+\s*$")
TEACHING_RE = re.compile(r"(方法技巧|思路点拨|知识点|专项讲解|易错点|答案解析|参考答案)")


def annotate_semantics(elements: list[PageElement]) -> list[PageElement]:
    annotated: list[PageElement] = []
    for element in elements:
        text = element.text.strip()
        role = "unknown"
        if DIRECTORY_RE.match(text):
            role = "directory_heading"
        elif TEACHING_RE.search(text):
            role = "teaching_text"
        elif QUESTION_ANCHOR_RE.match(text):
            role = "question_anchor"
        elif MATERIAL_PROMPT_RE.search(text):
            role = "material_prompt"
        elif OPTION_RE.match(text):
            role = "option"
        annotated.append(PageElement(**{**element.__dict__, "semantic_role": role}))
    return annotated
