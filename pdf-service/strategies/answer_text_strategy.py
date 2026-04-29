from __future__ import annotations

import re
from dataclasses import dataclass

from answer_models import AnswerCandidate
from extractor import PDFExtractor


ANCHOR_PATTERNS = [
    re.compile(r"【\s*例\s*(\d{1,4})\s*】"),
    re.compile(r"例\s*(\d{1,4})\s*[：:]"),
    re.compile(r"第\s*(\d{1,4})\s*题"),
    re.compile(r"(?m)^\s*(\d{1,4})\s*[\.、．]"),
]

ANSWER_PATTERNS = [
    re.compile(r"【\s*答案\s*】\s*[:：]?\s*([A-D]|对|错|正确|错误)", re.I),
    re.compile(r"答案\s*[:：]?\s*([A-D]|对|错|正确|错误)", re.I),
    re.compile(r"选\s*([A-D])", re.I),
    re.compile(r"(?:【\s*例\s*\d{1,4}\s*】|例\s*\d{1,4}\s*[：:]?)\s*([A-D]|对|错|正确|错误)\b", re.I),
    re.compile(r"(?m)^\s*\d{1,4}\s*[\.、．]\s*([A-D])\b", re.I),
]

ANALYSIS_PATTERNS = [
    re.compile(r"【\s*解析\s*】\s*[:：]?(.*)", re.S),
    re.compile(r"解析\s*[:：](.*)", re.S),
    re.compile(r"答案\s*[:：]?.*?[A-D对错正确错误][。\s]*(.*)", re.S | re.I),
]

SECTION_RE = re.compile(
    r"((?:第[一二三四五六七八九十百千万\d]+[章节部分篇])[^\n]{0,30}|[一二三四五六七八九十\d]+[、.．]\s*[^\n]{2,30})"
)


@dataclass(frozen=True)
class Anchor:
    index: int
    text: str
    start: int
    end: int


class TextAnswerStrategy:
    def parse(self, extractor: PDFExtractor) -> list[AnswerCandidate]:
        candidates: list[AnswerCandidate] = []
        current_section: str | None = None

        for page_index in range(extractor.total_pages):
            page_num = page_index + 1
            text = self._normalize_text(extractor.get_page_text(page_index))
            if not text.strip():
                continue

            current_section = self._detect_section(text) or current_section
            anchors = self._find_anchors(text)
            if not anchors:
                continue

            for anchor, block_text in self._split_by_anchors(text, anchors):
                answer = self._extract_answer(block_text)
                analysis = self._extract_analysis(block_text)
                confidence = self._score(
                    block_text=block_text,
                    anchor=anchor,
                    answer=answer,
                    analysis=analysis,
                    section_key=current_section,
                )
                candidates.append(
                    AnswerCandidate(
                        section_key=current_section,
                        question_index=anchor.index,
                        question_anchor=anchor.text,
                        answer=answer,
                        analysis_text=analysis,
                        source_page_num=page_num,
                        raw_text=block_text.strip(),
                        confidence=confidence,
                        parse_mode="text",
                    )
                )

        return candidates

    def _normalize_text(self, text: str) -> str:
        return text.replace("\r\n", "\n").replace("\r", "\n")

    def _detect_section(self, text: str) -> str | None:
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or len(stripped) > 48:
                continue
            match = SECTION_RE.search(stripped)
            if match and not any(word in stripped for word in ("答案", "解析")):
                return re.sub(r"\s+", "_", match.group(1).strip(" ：:"))
        return None

    def _find_anchors(self, text: str) -> list[Anchor]:
        anchors: list[Anchor] = []
        seen_starts: set[int] = set()
        for pattern in ANCHOR_PATTERNS:
            for match in pattern.finditer(text):
                if match.start() in seen_starts:
                    continue
                seen_starts.add(match.start())
                anchors.append(
                    Anchor(
                        index=int(match.group(1)),
                        text=match.group(0).strip(),
                        start=match.start(),
                        end=match.end(),
                    )
                )
        return sorted(anchors, key=lambda item: item.start)

    def _split_by_anchors(self, text: str, anchors: list[Anchor]) -> list[tuple[Anchor, str]]:
        blocks: list[tuple[Anchor, str]] = []
        for pos, anchor in enumerate(anchors):
            next_start = anchors[pos + 1].start if pos + 1 < len(anchors) else len(text)
            block = text[anchor.start:next_start].strip()
            if block:
                blocks.append((anchor, block))
        return blocks

    def _extract_answer(self, block_text: str) -> str | None:
        for pattern in ANSWER_PATTERNS:
            match = pattern.search(block_text)
            if match:
                return self._normalize_answer(match.group(1))
        return None

    def _extract_analysis(self, block_text: str) -> str | None:
        for pattern in ANALYSIS_PATTERNS:
            match = pattern.search(block_text)
            if match:
                analysis = self._clean_analysis(match.group(1))
                return analysis or None
        return None

    def _clean_analysis(self, analysis: str) -> str:
        cleaned = analysis.strip()
        cleaned = re.sub(r"^\s*[。；;，,：:]\s*", "", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    def _normalize_answer(self, answer: str) -> str:
        value = answer.strip().upper()
        return {"正确": "对", "错误": "错", "√": "对", "×": "错"}.get(value, value)

    def _score(
        self,
        block_text: str,
        anchor: Anchor,
        answer: str | None,
        analysis: str | None,
        section_key: str | None,
    ) -> int:
        score = 30
        if answer:
            score += 30
        if analysis:
            score += 20
        if section_key:
            score += 10
        if analysis and 8 <= len(analysis) <= 3000:
            score += 10

        anchor_count = len(self._find_anchors(block_text))
        if not answer:
            score = min(score, 40)
        if anchor_count > 1:
            score = min(score, 60)
        if not analysis:
            score = min(score, 70)
        if anchor.index <= 0:
            score = min(score, 75)
        return max(0, min(100, score))
