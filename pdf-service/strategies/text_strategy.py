from __future__ import annotations

import re
from typing import Any

from extractor import PDFExtractor
from parser_kernel import parse_extractor_with_kernel


class TextStrategy:
    """Plain-text PDF parsing strategy with AI-first and regex fallback."""

    ANSWER_PAGE_KEYWORDS = ["参考答案", "答案解析", "答题详解", "答案与解析", "参考答案及解析"]

    def parse(self, extractor: PDFExtractor, ai_client_module: Any) -> dict[str, Any]:
        questions: list[dict[str, Any]] = []
        materials: list[dict[str, Any]] = []

        answer_start_page = self._find_answer_page(extractor)
        content_page_count = (
            answer_start_page if answer_start_page > 0 else extractor.total_pages
        )
        saw_candidate_text = False

        batch_size = 5
        for batch_start in range(0, content_page_count, batch_size):
            batch_end = min(batch_start + batch_size, content_page_count)
            batch_text = "\n".join(
                extractor.get_page_text(page_num)
                for page_num in range(batch_start, batch_end)
            )
            if not batch_text.strip():
                continue
            saw_candidate_text = True
            if len(batch_text.strip()) < 100:
                continue

            parsed = ai_client_module.parse_text_block(batch_text)
            if not parsed:
                parsed_payload = parse_extractor_with_kernel(extractor)
                parsed = parsed_payload["questions"]
                materials.extend(parsed_payload["materials"])

            for question in parsed:
                question = dict(question)
                material_text = question.pop("material_text", None)
                if material_text:
                    material = {
                        "temp_id": f"m_{len(materials) + 1}",
                        "content": material_text,
                        "images": [],
                    }
                    materials.append(material)
                    question["material_temp_id"] = material["temp_id"]
                questions.append(question)

        if not questions and not materials and saw_candidate_text:
            parsed_payload = parse_extractor_with_kernel(extractor)
            questions.extend(dict(question) for question in parsed_payload["questions"])
            materials.extend(parsed_payload["materials"])

        if answer_start_page > 0:
            answer_text = "\n".join(
                extractor.get_page_text(page_num)
                for page_num in range(answer_start_page, extractor.total_pages)
            )
            answer_map = self._extract_answers(answer_text)
            for question in questions:
                index = _safe_int(question.get("index"))
                if index in answer_map and not question.get("answer"):
                    question["answer"] = answer_map[index]

        return {"questions": questions, "materials": materials}

    def _find_answer_page(self, extractor: PDFExtractor) -> int:
        for page_num in range(extractor.total_pages - 1, max(extractor.total_pages - 20, -1), -1):
            text = extractor.get_page_text(page_num)
            if any(keyword in text for keyword in self.ANSWER_PAGE_KEYWORDS):
                return page_num
        return -1

    def _extract_answers(self, answer_text: str) -> dict[int, str]:
        result: dict[int, str] = {}
        patterns = [
            r"(\d{1,3})[．.、]\s*([ABCD对错√×正确错误])",
            r"[（(](\d{1,3})[）)]\s*([ABCD对错√×])",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, answer_text):
                index = int(match.group(1))
                answer = self._normalize_answer(match.group(2))
                result.setdefault(index, answer)
        return result

    def _normalize_answer(self, answer: str) -> str:
        return {
            "√": "对",
            "×": "错",
            "正确": "对",
            "错误": "错",
        }.get(answer, answer)


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
