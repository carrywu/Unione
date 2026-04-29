# PDF Service Parser Kernel P0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a unified `pdf-service` parser kernel for P0, route `question_splitter.py` and `TextStrategy` fallback through it, and remove distributed next-match splitting behavior without changing external API or `models.py` semantics.

**Architecture:** Introduce a layered `parser_kernel` that normalizes both text-layer and visual-fallback extraction into the same internal element stream, performs semantic segmentation, builds question and material groups, and adapts the result into existing raw-question and strategy payload shapes. Existing entry points become thin wrappers over the kernel so question-boundary governance lives in one place, while routing keeps scanned answer books and review-note PDFs out of question-book splitting.

**Tech Stack:** Python 3, FastAPI service internals, PyMuPDF-derived `PageContent`, `pytest`, existing `pydantic` models

---

## File Map

**Create**

- `pdf-service/tests/fixtures/2026资料分析题库-test.pdf`
- `pdf-service/tests/fixtures/test（7-12章下册完结）2026高照资料分析夸夸刷讲义复盘笔记（下册）.pdf`
- `pdf-service/parser_kernel/__init__.py`
- `pdf-service/parser_kernel/types.py`
- `pdf-service/parser_kernel/layout_engine.py`
- `pdf-service/parser_kernel/routing.py`
- `pdf-service/parser_kernel/semantic_segmenter.py`
- `pdf-service/parser_kernel/question_group_builder.py`
- `pdf-service/parser_kernel/adapter.py`
- `pdf-service/tests/test_parser_kernel_semantic.py`
- `pdf-service/tests/test_parser_kernel_grouping.py`
- `pdf-service/tests/test_text_strategy_kernel_fallback.py`
- `pdf-service/tests/test_review_note_routing.py`
- `pdf-service/tests/test_scanned_pdf_routing.py`

**Modify**

- `pdf-service/question_splitter.py`
- `pdf-service/strategies/text_strategy.py`

**Defer**

- `pdf-service/parser_kernel/visual_assignment.py`
- `pdf-service/strategies/markdown_question_strategy.py`
- `pdf-service/block_segmenter.py`

## Fixture Roles

- `pdf-service/tests/fixtures/2026资料分析题库-test.pdf`
  - treat as `question_book`
  - use for parser-kernel slicing, material grouping, and visual-assignment verification

- `pdf-service/tests/fixtures/test（7-12章下册完结）2026高照资料分析夸夸刷讲义复盘笔记（下册）.pdf`
  - treat as `answer_note` / `image_explanation`
  - do not feed into `question_splitter`
  - validate routing assumptions only in P0; deeper answer-book/image-mode work remains outside this parser-kernel scope

- `题本篇.pdf`
  - treat as `scanned_question_book`
  - do not allow empty-text failure to short-circuit parsing
  - visual extraction must still map into parser-kernel inputs

- `解析篇.pdf`
  - treat as `scanned_answer_book`
  - do not feed into normal question-book splitting
  - validate routing assumptions and candidate-oriented handling in P0

## Task 1: Lock P0 Boundary Regressions With Tests

**Files:**
- Create: `pdf-service/tests/test_parser_kernel_semantic.py`
- Create: `pdf-service/tests/test_parser_kernel_grouping.py`
- Create: `pdf-service/tests/test_text_strategy_kernel_fallback.py`
- Create: `pdf-service/tests/test_review_note_routing.py`
- Create: `pdf-service/tests/test_scanned_pdf_routing.py`

- [ ] **Step 1: Write failing semantic regression tests**

```python
from models import PageContent, Region, TextBlock
from question_splitter import split_questions


def make_page(page_num: int, text: str, blocks: list[tuple[list[float], str]]) -> PageContent:
    return PageContent(
        page_num=page_num,
        text=text,
        blocks=[TextBlock(bbox=bbox, text=block_text) for bbox, block_text in blocks],
        regions=[],
    )


def test_directory_and_teaching_text_do_not_become_questions():
    page = make_page(
        1,
        "第一章 资料分析........12\n方法技巧\n1. 下列说法正确的是？\nA. 甲\nB. 乙\nC. 丙\nD. 丁\n",
        [
            ([0, 0, 100, 10], "第一章 资料分析........12"),
            ([0, 20, 100, 30], "方法技巧"),
            ([0, 40, 100, 50], "1. 下列说法正确的是？"),
            ([0, 52, 100, 62], "A. 甲"),
            ([0, 64, 100, 74], "B. 乙"),
            ([0, 76, 100, 86], "C. 丙"),
            ([0, 88, 100, 98], "D. 丁"),
        ],
    )

    questions = split_questions([page])

    assert len(questions) == 1
    assert "方法技巧" not in questions[0].text
    assert "第一章" not in questions[0].text
```

- [ ] **Step 2: Write failing grouping regression tests**

```python
from models import PageContent, TextBlock
from question_splitter import split_questions


def make_page(page_num: int, text: str, blocks: list[tuple[list[float], str]]) -> PageContent:
    return PageContent(
        page_num=page_num,
        text=text,
        blocks=[TextBlock(bbox=bbox, text=block_text) for bbox, block_text in blocks],
        regions=[],
    )


def test_following_material_is_not_absorbed_into_previous_question():
    page = make_page(
        1,
        "1. 第一题题干\nA. 甲\nB. 乙\nC. 丙\nD. 丁\n"
        "2. 第二题题干\nA. 甲\nB. 乙\nC. 丙\nD. 丁\n"
        "根据以下资料，回答3-5题\n2024年全市工业产值增长。\n"
        "3. 第三题题干\nA. 甲\nB. 乙\nC. 丙\nD. 丁\n",
        [
            ([0, 0, 100, 10], "1. 第一题题干"),
            ([0, 12, 100, 22], "A. 甲"),
            ([0, 24, 100, 34], "B. 乙"),
            ([0, 36, 100, 46], "C. 丙"),
            ([0, 48, 100, 58], "D. 丁"),
            ([0, 80, 100, 90], "2. 第二题题干"),
            ([0, 92, 100, 102], "A. 甲"),
            ([0, 104, 100, 114], "B. 乙"),
            ([0, 116, 100, 126], "C. 丙"),
            ([0, 128, 100, 138], "D. 丁"),
            ([0, 160, 180, 170], "根据以下资料，回答3-5题"),
            ([0, 172, 180, 182], "2024年全市工业产值增长。"),
            ([0, 200, 100, 210], "3. 第三题题干"),
            ([0, 212, 100, 222], "A. 甲"),
            ([0, 224, 100, 234], "B. 乙"),
            ([0, 236, 100, 246], "C. 丙"),
            ([0, 248, 100, 258], "D. 丁"),
        ],
    )

    questions = split_questions([page])

    assert len(questions) == 3
    assert "根据以下资料" not in questions[1].text
    assert questions[2].material_id is not None
    assert questions[1].material_id is None
```

- [ ] **Step 3: Write failing TextStrategy fallback routing test**

```python
from strategies.text_strategy import TextStrategy


class FakeExtractor:
    total_pages = 1

    def get_page_text(self, page_num: int) -> str:
        return "1. 下列说法正确的是？\nA. 甲\nB. 乙\nC. 丙\nD. 丁\n"


class FakeAiClient:
    @staticmethod
    def parse_text_block(text: str):
        return []


def test_text_strategy_fallback_uses_kernel(monkeypatch):
    calls = {"count": 0}

    def fake_parse_text_with_kernel(text: str):
        calls["count"] += 1
        return {
            "questions": [
                {
                    "index": 1,
                    "type": "single",
                    "content": "下列说法正确的是？",
                    "options": {"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
                }
            ],
            "materials": [],
        }

    monkeypatch.setattr(
        "strategies.text_strategy.parse_text_with_kernel",
        fake_parse_text_with_kernel,
    )

    result = TextStrategy().parse(FakeExtractor(), FakeAiClient())

    assert calls["count"] == 1
    assert len(result["questions"]) == 1
```

- [ ] **Step 4: Write failing review-note routing safeguard test**

```python
from pathlib import Path


def should_use_question_book_kernel(file_name: str) -> bool:
    raise NotImplementedError


def test_review_note_fixture_is_not_treated_as_question_book():
    fixture = Path(
        "tests/fixtures/test（7-12章下册完结）2026高照资料分析夸夸刷讲义复盘笔记（下册）.pdf"
    )
    assert should_use_question_book_kernel(fixture.name) is False
```

- [ ] **Step 5: Write failing scanned PDF routing tests**

```python
from parser_kernel.routing import classify_pdf_kind


def test_scanned_question_book_is_not_treated_as_text_layer_book():
    kind = classify_pdf_kind(
        file_name="题本篇.pdf",
        total_pages=12,
        text_lengths=[0] * 12,
    )
    assert kind == "scanned_question_book"


def test_scanned_answer_book_is_not_treated_as_question_book():
    kind = classify_pdf_kind(
        file_name="解析篇.pdf",
        total_pages=10,
        text_lengths=[0] * 10,
    )
    assert kind == "scanned_answer_book"
```

- [ ] **Step 6: Run tests to verify they fail**

Run:

```bash
cd /Users/apple/Downloads/公考/project2/pdf-service
pytest tests/test_parser_kernel_semantic.py tests/test_parser_kernel_grouping.py tests/test_text_strategy_kernel_fallback.py tests/test_review_note_routing.py tests/test_scanned_pdf_routing.py -q
```

Expected:

- import failures for kernel helpers, or
- assertion failures because the old splitter still absorbs headings/material, or
- monkeypatch target missing because `parse_extractor_with_kernel` is not defined yet
- routing-helper failure because the question-book gate is not defined yet
- scanned-PDF classifier failure because the PDF kind model is not defined yet

## Task 2: Create Kernel Types and Layout Normalization

**Files:**
- Create: `pdf-service/parser_kernel/__init__.py`
- Create: `pdf-service/parser_kernel/types.py`
- Create: `pdf-service/parser_kernel/layout_engine.py`

- [ ] **Step 1: Add internal kernel types**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


ElementKind = Literal["text", "region"]
SemanticRole = Literal[
    "unknown",
    "question_anchor",
    "option",
    "material_prompt",
    "material_body",
    "teaching_text",
    "directory_heading",
    "question_body",
]


@dataclass
class PageElement:
    page_num: int
    order_index: int
    bbox: list[float]
    text: str
    kind: ElementKind = "text"
    semantic_role: SemanticRole = "unknown"


@dataclass
class MaterialGroup:
    id: str
    prompt_text: str
    body_text: str
    question_range: tuple[int, int] | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class QuestionGroup:
    index: int
    text: str
    page_num: int
    y0: float
    y1: float
    material_id: str | None = None
    warnings: list[str] = field(default_factory=list)
```

- [ ] **Step 2: Add page normalization**

```python
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
```

- [ ] **Step 3: Add kernel exports**

```python
from parser_kernel.layout_engine import normalize_pages

__all__ = ["normalize_pages"]
```

- [ ] **Step 4: Run targeted tests**

Run:

```bash
cd /Users/apple/Downloads/公考/project2/pdf-service
pytest tests/test_parser_kernel_semantic.py -q
```

Expected:

- still failing on behavior assertions, but not failing on missing basic imports

## Task 3: Add Document-Type Routing Helpers

**Files:**
- Create: `pdf-service/parser_kernel/routing.py`
- Modify: `pdf-service/parser_kernel/__init__.py`
- Test: `pdf-service/tests/test_review_note_routing.py`
- Test: `pdf-service/tests/test_scanned_pdf_routing.py`

- [ ] **Step 1: Add a conservative routing helper**

```python
from __future__ import annotations


REVIEW_NOTE_HINTS = (
    "复盘笔记",
    "讲义复盘",
    "下册完结",
)
SCANNED_ANSWER_BOOK_HINTS = ("解析篇",)
SCANNED_QUESTION_BOOK_HINTS = ("题本篇",)


def should_use_question_book_kernel(file_name: str) -> bool:
    normalized = file_name.strip()
    return not any(hint in normalized for hint in REVIEW_NOTE_HINTS)


def classify_pdf_kind(file_name: str, total_pages: int, text_lengths: list[int]) -> str:
    normalized = file_name.strip()
    total_text = sum(text_lengths)
    sparse_text = total_pages > 0 and total_text < max(80, total_pages * 10)
    if any(hint in normalized for hint in REVIEW_NOTE_HINTS):
        return "answer_note"
    if any(hint in normalized for hint in SCANNED_ANSWER_BOOK_HINTS):
        return "scanned_answer_book"
    if any(hint in normalized for hint in SCANNED_QUESTION_BOOK_HINTS):
        return "scanned_question_book"
    if sparse_text:
        return "scanned_question_book"
    return "text_layer_book"
```

- [ ] **Step 2: Export the routing helper**

```python
from parser_kernel.layout_engine import normalize_pages
from parser_kernel.routing import classify_pdf_kind, should_use_question_book_kernel

__all__ = ["classify_pdf_kind", "normalize_pages", "should_use_question_book_kernel"]
```

- [ ] **Step 3: Run the routing safeguard tests**

Run:

```bash
cd /Users/apple/Downloads/公考/project2/pdf-service
pytest tests/test_review_note_routing.py tests/test_scanned_pdf_routing.py -q
```

Expected:

- PASS
## Task 4: Implement Semantic Segmentation

**Files:**
- Create: `pdf-service/parser_kernel/semantic_segmenter.py`
- Modify: `pdf-service/parser_kernel/__init__.py`

- [ ] **Step 1: Add unified semantic rules**

```python
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
        elif MATERIAL_PROMPT_RE.search(text):
            role = "material_prompt"
        elif OPTION_RE.match(text):
            role = "option"
        elif QUESTION_ANCHOR_RE.match(text):
            role = "question_anchor"
        annotated.append(PageElement(**{**element.__dict__, "semantic_role": role}))
    return annotated
```

- [ ] **Step 2: Export semantic annotation**

```python
from parser_kernel.layout_engine import normalize_pages
from parser_kernel.semantic_segmenter import annotate_semantics

__all__ = ["annotate_semantics", "normalize_pages"]
```

- [ ] **Step 3: Run semantic regression test**

Run:

```bash
cd /Users/apple/Downloads/公考/project2/pdf-service
pytest tests/test_parser_kernel_semantic.py::test_directory_and_teaching_text_do_not_become_questions -q
```

Expected:

- still failing on grouping because no builder exists yet, but semantic import path is valid

## Task 5: Implement Question and Material Group Building

**Files:**
- Create: `pdf-service/parser_kernel/question_group_builder.py`
- Modify: `pdf-service/parser_kernel/__init__.py`

- [ ] **Step 1: Add group builder with material-aware boundaries**

```python
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
            index = next(int(group) for group in INDEX_RE.match(text).groups() if group)
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
```

- [ ] **Step 2: Export group builder**

```python
from parser_kernel.layout_engine import normalize_pages
from parser_kernel.question_group_builder import build_groups
from parser_kernel.semantic_segmenter import annotate_semantics

__all__ = ["annotate_semantics", "build_groups", "normalize_pages"]
```

- [ ] **Step 3: Run grouping regression test**

Run:

```bash
cd /Users/apple/Downloads/公考/project2/pdf-service
pytest tests/test_parser_kernel_grouping.py::test_following_material_is_not_absorbed_into_previous_question -q
```

Expected:

- PASS or one narrow failure around anchor text retention that will be fixed in the adapter task

## Task 6: Add Adapter and Convert `question_splitter.py` Into a Compatibility Shell

**Files:**
- Create: `pdf-service/parser_kernel/adapter.py`
- Modify: `pdf-service/parser_kernel/__init__.py`
- Modify: `pdf-service/question_splitter.py`

- [ ] **Step 1: Add adapter helpers**

```python
from __future__ import annotations

from models import RawQuestion
from parser_kernel.types import MaterialGroup, QuestionGroup


def groups_to_raw_questions(materials: list[MaterialGroup], questions: list[QuestionGroup]) -> list[RawQuestion]:
    material_text_by_id = {
        material.id: "\n".join(part for part in [material.prompt_text, material.body_text] if part).strip()
        for material in materials
    }
    return [
        RawQuestion(
            index=question.index,
            text=question.text,
            page_num=question.page_num,
            y0=question.y0,
            y1=question.y1,
            material_id=question.material_id,
            material_text=material_text_by_id.get(question.material_id),
        )
        for question in questions
    ]
```

- [ ] **Step 2: Export end-to-end page parser**

```python
from parser_kernel.adapter import groups_to_raw_questions
from parser_kernel.layout_engine import normalize_pages
from parser_kernel.question_group_builder import build_groups
from parser_kernel.semantic_segmenter import annotate_semantics


def parse_pages_to_raw_questions(pages):
    elements = normalize_pages(pages)
    annotated = annotate_semantics(elements)
    materials, questions = build_groups(annotated)
    return groups_to_raw_questions(materials, questions)
```

- [ ] **Step 3: Replace `question_splitter.py` internals with kernel delegation**

```python
from __future__ import annotations

from typing import List

from models import PageContent, RawQuestion
from parser_kernel import parse_pages_to_raw_questions


def split_questions(pages: List[PageContent]) -> List[RawQuestion]:
    return parse_pages_to_raw_questions(pages)
```

- [ ] **Step 4: Run splitter regression tests**

Run:

```bash
cd /Users/apple/Downloads/公考/project2/pdf-service
pytest tests/test_parser_kernel_semantic.py tests/test_parser_kernel_grouping.py -q
```

Expected:

- PASS for both tests

## Task 7: Route `TextStrategy` Fallback Through the Kernel

**Files:**
- Modify: `pdf-service/strategies/text_strategy.py`
- Test: `pdf-service/tests/test_text_strategy_kernel_fallback.py`

- [ ] **Step 1: Add a kernel-backed fallback helper**

```python
from pdf_analyzer import extract_pages
from parser_kernel import parse_pages_to_raw_questions


def parse_text_with_kernel(pdf_path: str):
    pages = extract_pages(pdf_path)
    raw_questions = parse_pages_to_raw_questions(pages)
    questions = []
    materials_by_text: dict[str, str] = {}
    materials = []
    for raw in raw_questions:
        material_temp_id = None
        if raw.material_text:
            material_temp_id = materials_by_text.get(raw.material_text)
            if material_temp_id is None:
                material_temp_id = f"m_{len(materials) + 1}"
                materials_by_text[raw.material_text] = material_temp_id
                materials.append({"temp_id": material_temp_id, "content": raw.material_text, "images": []})
        questions.append(
            {
                "index": raw.index,
                "type": "single",
                "content": raw.text,
                "options": {},
                "answer": None,
                "analysis": None,
                "needs_review": True,
                "material_temp_id": material_temp_id,
            }
        )
    return {"questions": questions, "materials": materials}
```

- [ ] **Step 2: Replace local fallback splitters**

```python
    def _fallback_split(self, text: str) -> list[dict[str, Any]]:
        raise RuntimeError("_fallback_split is deprecated; use parse_text_with_kernel")

    def _fallback_parse_question(self, index: int, raw: str) -> dict[str, Any] | None:
        raise RuntimeError("_fallback_parse_question is deprecated; use parse_text_with_kernel")
```

And update the `parse()` fallback branch to call the new helper instead of `_fallback_split`.

- [ ] **Step 3: Adjust the test seam if extractor text-only fallback cannot provide `pdf_path`**

```python
class TextStrategy:
    ...
    def parse(self, extractor: PDFExtractor, ai_client_module: Any) -> dict[str, Any]:
        ...
        if not parsed:
            parsed_payload = parse_text_with_kernel(extractor.pdf_path)
            parsed = parsed_payload["questions"]
            materials.extend(parsed_payload["materials"])
```

- [ ] **Step 4: Run the fallback routing test**

Run:

```bash
cd /Users/apple/Downloads/公考/project2/pdf-service
pytest tests/test_text_strategy_kernel_fallback.py::test_text_strategy_fallback_uses_kernel -q
```

Expected:

- PASS with the monkeypatched kernel helper called exactly once

## Task 8: Remove Distributed Next-Match Split Behavior and Verify P0

**Files:**
- Modify: `pdf-service/strategies/text_strategy.py`
- Modify: `pdf-service/question_splitter.py`

- [ ] **Step 1: Delete or neutralize local `QUESTION_RE` usage outside the kernel**

Make sure these are no longer active parsing authorities:

```python
QUESTION_RE = re.compile(r"^\s*(\d{1,3})[．.、]\s*", re.MULTILINE)
```

Delete from:

- `pdf-service/question_splitter.py`
- `pdf-service/strategies/text_strategy.py`

Keep anchor detection only inside `parser_kernel/semantic_segmenter.py`.

- [ ] **Step 2: Run focused P0 regression suite**

Run:

```bash
cd /Users/apple/Downloads/公考/project2/pdf-service
pytest tests/test_parser_kernel_semantic.py tests/test_parser_kernel_grouping.py tests/test_text_strategy_kernel_fallback.py tests/test_review_note_routing.py -q
```

Expected:

- all tests PASS

- [ ] **Step 3: Run existing parser smoke test**

Run:

```bash
cd /Users/apple/Downloads/公考/project2/pdf-service
pytest tests/test_orphan_corner_brackets.py -q
```

Expected:

- PASS

- [ ] **Step 4: Manual sanity check on sample parser output**

Run:

```bash
cd /Users/apple/Downloads/公考/project2/pdf-service
.venv/bin/python tools/evaluate_self_parser.py /Users/apple/Downloads/test.pdf --output-dir tmp/p0-kernel-smoke
```

Expected:

- command completes without crashing the full book
- debug output directory exists
- output is produced even if warnings remain

## Self-Review

### Spec Coverage

- unified layered parser kernel: covered by Tasks 2-6
- `question_splitter.py` compatibility shell: covered by Task 6
- `TextStrategy` fallback unification: covered by Task 7
- no distributed next-match splitting: covered by Task 8
- directory/teaching/next-material regression protection: covered by Task 1 and Tasks 4-6
- review-note fixture routing guard: covered by Tasks 1 and 3

### Placeholder Scan

- No `TODO`, `TBD`, or deferred implementation steps exist inside P0 tasks.
- P1/P2 items are explicitly out of scope for this plan.

### Type Consistency

- Kernel output flows from `PageElement` -> `MaterialGroup`/`QuestionGroup` -> `RawQuestion`.
- `question_splitter.py` consumes only `parse_pages_to_raw_questions`.
- `TextStrategy` fallback consumes a dedicated kernel helper instead of old local regex splitting.
- question-book lane eligibility is checked by one exported routing helper instead of ad hoc call-site naming logic.

## Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-28-pdf-service-parser-kernel-p0.md`.
