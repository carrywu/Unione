from __future__ import annotations

import re
from typing import Dict, List

from models import PageContent


ANSWER_KEYWORDS = ("参考答案", "答案解析", "答题详解")
ANSWER_RE = re.compile(r"(\d+)[．.、]\s*([ABCD√×对错])")


def find_answer_page(pages: List[PageContent]) -> int:
    for page in pages:
        if any(keyword in page.text for keyword in ANSWER_KEYWORDS):
            return page.page_num
    return -1


def extract_answers(answer_text: str) -> Dict[int, str]:
    answers: Dict[int, str] = {}
    for match in ANSWER_RE.finditer(answer_text):
        answers[int(match.group(1))] = match.group(2)
    return answers
