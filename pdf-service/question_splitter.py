from __future__ import annotations

from typing import List

from models import PageContent, RawQuestion
from parser_kernel import parse_pages_to_raw_questions


def split_questions(pages: List[PageContent]) -> List[RawQuestion]:
    return parse_pages_to_raw_questions(pages)
