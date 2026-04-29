from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from extractor import PDFExtractor


@dataclass
class QuestionMarker:
    index: int
    start: int
    end: int
    label: str


class UniversalQuestionStrategy:
    """General PyMuPDF text-first strategy for question-only extraction.

    This strategy intentionally does not hardcode one publisher/book format. It
    keeps broad marker libraries for question numbers, options, chapter paths,
    materials, and skip pages, then extracts question blocks with metadata for
    later human review and answer-matching stages.
    """

    QUESTION_PATTERNS = [
        re.compile(r"(?m)^\s*【\s*例\s*(?P<index>\d{1,4})\s*】\s*"),
        re.compile(r"(?m)^\s*例题\s*(?P<index>\d{1,4})\s*[．.、:]?\s*"),
        re.compile(r"(?m)^\s*第\s*(?P<index>\d{1,4})\s*题\s*[．.、:]?\s*"),
        re.compile(r"(?m)^\s*(?P<index>\d{1,4})\s*[．.。]\s+"),
        re.compile(r"(?m)^\s*(?P<index>\d{1,4})\s*[、)]\s*"),
        # Bare question number, e.g. a line starts with "1 下列..." or a line
        # contains only "1" before the stem. Kept last because it is noisier.
        re.compile(r"(?m)^\s*(?P<index>\d{1,4})(?=\s+(?:下列|根据|关于|某|有|从|在|为|如|一个|一项|以下|材料|图|表|能够|可以|应当|不|与|将|把|对|从))\s*"),
        re.compile(r"(?m)^\s*(?P<index>\d{1,4})\s*$"),
    ]

    OPTION_LINE_RE = re.compile(
        r"(?m)^\s*(?:[（(]\s*(?P<label1>[A-D])\s*[）)]|(?P<label2>[A-D]))\s*[．.、。]?\s+(?P<body>\S.*?)\s*$"
    )
    OPTION_INLINE_RE = re.compile(
        r"(?:^|\s)(?:[（(]\s*(?P<label1>[A-D])\s*[）)]|(?P<label2>[A-D]))\s*[．.、。]?\s*(?P<body>.*?)(?=\s*(?:[（(]?\s*[A-D]\s*[）)]?\s*[．.、。]?\s+)|$)",
        re.S,
    )

    SKIP_PAGE_KEYWORDS = [
        "目录",
        "参考答案",
        "答案解析",
        "答案与解析",
        "答题详解",
        "课后赠言",
        "编者寄语",
        "前言",
        "本章小结",
    ]
    EXPLANATION_ONLY_KEYWORDS = ["考点精讲", "方法精讲", "知识梳理", "核心知识", "理论精讲"]
    CHAPTER_PATTERNS = [
        re.compile(r"^\s*第[一二三四五六七八九十百千万\d]+章\s*\S*"),
        re.compile(r"^\s*[一二三四五六七八九十]+[、.]\s*\S+"),
        re.compile(r"^\s*\d{1,2}[．.]\s*\S+"),
        re.compile(r"^\s*考法[一二三四五六七八九十\d]+\s*\S*"),
    ]
    MATERIAL_RANGE_RE = re.compile(
        r"(?P<text>(?:根据|阅读|结合).{0,80}?(?:资料|材料|下列|以下).{0,80}?(?:回答|完成|作答)\s*(?:第?\s*)?(?P<start>\d{1,4})\s*[-—~至到]\s*(?P<end>\d{1,4})\s*题?)"
    )
    MATERIAL_HINT_RE = re.compile(r"(根据以下资料|根据下列资料|阅读以下材料|阅读下列材料|根据材料|据此回答)")
    TITLE_HINT_RE = re.compile(r"(图\s*\d*[-—]?\d*|表\s*\d*[-—]?\d*|资料\s*\d*|材料\s*\d*)[：:].{1,80}")
    TOC_LINE_RE = re.compile(r"^.{1,80}(?:\.{4,}|…{2,})\s*\d+\s*$")

    def parse(self, extractor: PDFExtractor, ai_client_module: Any = None) -> dict[str, Any]:
        questions: list[dict[str, Any]] = []
        materials: list[dict[str, Any]] = []
        material_by_key: dict[str, str] = {}
        active_ranges: list[tuple[int, int, str]] = []
        chapter_path: list[str] = []
        recent_context: list[str] = []

        for page_num in range(extractor.total_pages):
            raw_text = extractor.get_page_text(page_num)
            text = self._normalize_text(raw_text)
            if self._should_skip_page(text):
                continue

            chapter_path = self._update_chapter_path(chapter_path, text)
            page_materials = self._extract_page_materials(
                text,
                page_num=page_num,
                materials=materials,
                material_by_key=material_by_key,
            )
            active_ranges.extend(page_materials)

            markers = self._find_question_markers(text)
            if not markers:
                recent_context = self._update_recent_context(recent_context, text)
                continue

            for pos, marker in enumerate(markers):
                block_start = marker.end
                block_end = markers[pos + 1].start if pos + 1 < len(markers) else len(text)
                block = text[block_start:block_end].strip()
                parsed = self._parse_question_block(marker, block, page_num, chapter_path)
                if not parsed:
                    continue

                material_id = self._material_for_index(marker.index, active_ranges)
                if not material_id:
                    material_text = self._nearest_material_text(text[: marker.start], recent_context)
                    if material_text:
                        material_id = self._material_id_for_text(
                            material_text,
                            page_num=page_num,
                            materials=materials,
                            material_by_key=material_by_key,
                        )
                if material_id:
                    parsed["material_temp_id"] = material_id
                    parsed["material_text"] = next(
                        (m.get("content") for m in materials if m.get("temp_id") == material_id),
                        None,
                    )

                questions.append(parsed)

            recent_context = self._update_recent_context(recent_context, text)

        return {"questions": questions, "materials": materials}

    def _normalize_text(self, text: str) -> str:
        text = text.replace("\r", "\n")
        text = re.sub(r"[\t\u3000]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _should_skip_page(self, text: str) -> bool:
        compact = re.sub(r"\s+", "", text)
        if not compact:
            return True
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        toc_lines = sum(1 for line in lines if self.TOC_LINE_RE.match(line))
        if lines and (toc_lines / max(len(lines), 1)) > 0.35:
            return True
        if any(keyword in compact for keyword in ["参考答案", "答案解析", "答案与解析", "课后赠言"]):
            return True
        option_count = len(re.findall(r"(?m)^\s*(?:[A-D][．.、。]|[（(][A-D][）)])", text))
        question_count = len(self._find_question_markers(text))
        explanation_score = sum(1 for keyword in self.EXPLANATION_ONLY_KEYWORDS if keyword in compact)
        if explanation_score >= 1 and option_count == 0 and question_count < 2:
            return True
        return False

    def _update_chapter_path(self, current: list[str], text: str) -> list[str]:
        path = list(current[-4:])
        for line in [line.strip() for line in text.splitlines() if line.strip()]:
            if len(line) > 60:
                continue
            for level, pattern in enumerate(self.CHAPTER_PATTERNS):
                if pattern.match(line) and not self._looks_like_question_line(line):
                    path = path[:level]
                    path.append(line)
                    break
        return path[-4:]

    def _extract_page_materials(
        self,
        text: str,
        *,
        page_num: int,
        materials: list[dict[str, Any]],
        material_by_key: dict[str, str],
    ) -> list[tuple[int, int, str]]:
        ranges: list[tuple[int, int, str]] = []
        for match in self.MATERIAL_RANGE_RE.finditer(text):
            material_text = self._nearest_material_text(text[: match.end()], []) or match.group("text")
            material_id = self._material_id_for_text(material_text, page_num, materials, material_by_key)
            start, end = int(match.group("start")), int(match.group("end"))
            if start <= end:
                ranges.append((start, end, material_id))
        return ranges

    def _find_question_markers(self, text: str) -> list[QuestionMarker]:
        found: list[QuestionMarker] = []
        for pattern in self.QUESTION_PATTERNS:
            for match in pattern.finditer(text):
                index = _safe_int(match.group("index"))
                if index is None:
                    continue
                line_end = text.find("\n", match.start())
                line = text[match.start() : line_end if line_end != -1 else len(text)]
                if self._is_false_question_marker(line):
                    continue
                found.append(QuestionMarker(index=index, start=match.start(), end=match.end(), label=match.group(0)))
        found.sort(key=lambda item: (item.start, -(item.end - item.start)))
        deduped: list[QuestionMarker] = []
        for marker in found:
            if deduped and abs(marker.start - deduped[-1].start) < 3:
                continue
            deduped.append(marker)
        return deduped

    def _is_false_question_marker(self, line: str) -> bool:
        stripped = line.strip()
        if self.TOC_LINE_RE.match(stripped):
            return True
        if re.match(r"^\d{1,2}[．.]\s*(目录|考法|方法|技巧|知识|题型|模块)", stripped):
            return True
        return False

    def _looks_like_question_line(self, line: str) -> bool:
        return any(pattern.match(line) for pattern in self.QUESTION_PATTERNS[:5]) and len(line) > 8

    def _parse_question_block(
        self,
        marker: QuestionMarker,
        block: str,
        page_num: int,
        chapter_path: list[str],
    ) -> dict[str, Any] | None:
        block = block.strip()
        if len(block) < 4:
            return None
        options = self._extract_options(block)
        option_positions = [pos for _, _, pos in options.values()]
        option_start = min(option_positions) if option_positions else len(block)
        content = self._clean_stem(block[:option_start])
        options_dict = {label: body for label, (body, _, _) in options.items() if body}
        missing_options = len(options_dict) < 2
        content_too_short = len(re.sub(r"\s+", "", content)) < 8
        material_suspected = bool(self.MATERIAL_HINT_RE.search(content)) and not re.search(r"[。；;]", content[-30:])
        if content_too_short and not options_dict:
            return None
        confidence = self._confidence(content, options_dict, missing_options, material_suspected)
        return {
            "index": marker.index,
            "type": "single" if options_dict else "single",
            "content": content,
            "options": options_dict,
            "option_a": options_dict.get("A"),
            "option_b": options_dict.get("B"),
            "option_c": options_dict.get("C"),
            "option_d": options_dict.get("D"),
            "answer": None,
            "analysis": None,
            "needs_review": bool(missing_options or content_too_short or material_suspected),
            "review_reasons": [
                reason
                for reason, enabled in [
                    ("options_missing", missing_options),
                    ("stem_too_short", content_too_short),
                    ("material_maybe_missing", material_suspected),
                ]
                if enabled
            ],
            "page_num": page_num + 1,
            "source": "universal_text_rule",
            "raw_text": f"{marker.label}{block}"[:12000],
            "parse_confidence": confidence,
            "chapter_path": " / ".join(chapter_path),
            "parse_stage": "question_parse",
        }

    def _extract_options(self, block: str) -> dict[str, tuple[str, int, int]]:
        options: dict[str, tuple[str, int, int]] = {}
        for match in self.OPTION_LINE_RE.finditer(block):
            label = (match.group("label1") or match.group("label2") or "").upper()
            body = self._clean_option(match.group("body"))
            if label and body and label not in options:
                options[label] = (body, match.end(), match.start())
        if len(options) >= 2:
            return options

        inline_options: dict[str, tuple[str, int, int]] = {}
        for match in self.OPTION_INLINE_RE.finditer(block):
            label = (match.group("label1") or match.group("label2") or "").upper()
            body = self._clean_option(match.group("body"))
            if label and body and label not in inline_options:
                inline_options[label] = (body, match.end(), match.start())
        return inline_options if len(inline_options) > len(options) else options

    def _clean_stem(self, stem: str) -> str:
        lines = [line.strip() for line in stem.splitlines() if line.strip()]
        cleaned = []
        for line in lines:
            if self._is_chapter_line(line):
                continue
            cleaned.append(line)
        return re.sub(r"\s+", " ", "\n".join(cleaned)).strip()

    def _clean_option(self, option: str) -> str:
        option = re.sub(r"\s+", " ", option).strip()
        option = re.sub(r"^[A-D][．.、。]?\s*", "", option).strip()
        return option

    def _is_chapter_line(self, line: str) -> bool:
        return any(pattern.match(line) for pattern in self.CHAPTER_PATTERNS) and len(line) < 60

    def _nearest_material_text(self, prefix: str, recent_context: list[str]) -> str:
        lines = [line.strip() for line in prefix.splitlines() if line.strip()]
        candidates: list[str] = []
        for line in lines[-20:]:
            if self._is_chapter_line(line) or self._looks_like_question_line(line):
                continue
            if self.MATERIAL_HINT_RE.search(line) or self.TITLE_HINT_RE.search(line) or len(line) > 30:
                candidates.append(line)
        if not candidates:
            candidates = recent_context[-6:]
        text = "\n".join(candidates[-8:]).strip()
        return text[:4000]

    def _material_for_index(self, index: int, ranges: list[tuple[int, int, str]]) -> str | None:
        for start, end, material_id in reversed(ranges):
            if start <= index <= end:
                return material_id
        return None

    def _material_id_for_text(
        self,
        material_text: str,
        page_num: int,
        materials: list[dict[str, Any]],
        material_by_key: dict[str, str],
    ) -> str:
        key = re.sub(r"\s+", "", material_text)[:120]
        if key in material_by_key:
            return material_by_key[key]
        material_id = f"u_p{page_num + 1}_m{len(materials) + 1}"
        materials.append(
            {
                "temp_id": material_id,
                "content": material_text,
                "images": [],
                "page_num": page_num + 1,
                "source": "universal_text_rule",
            }
        )
        material_by_key[key] = material_id
        return material_id

    def _update_recent_context(self, current: list[str], text: str) -> list[str]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        useful = [
            line
            for line in lines
            if len(line) > 20 and not self._is_chapter_line(line) and not self._looks_like_question_line(line)
        ]
        return (current + useful)[-10:]

    def _confidence(
        self,
        content: str,
        options: dict[str, str],
        missing_options: bool,
        material_suspected: bool,
    ) -> float:
        score = 0.55
        if len(content) >= 12:
            score += 0.15
        if len(options) >= 4:
            score += 0.25
        elif len(options) >= 2:
            score += 0.15
        if missing_options:
            score -= 0.25
        if material_suspected:
            score -= 0.1
        return round(max(0.1, min(score, 0.98)), 2)


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
