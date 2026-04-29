import unittest
from unittest.mock import patch

import pipeline


class FakeLongScannedExtractor:
    total_pages = 225
    pdf_path = "/tmp/题本篇.pdf"

    def __init__(self, path: str):
        self.path = path
        self.closed = False

    def get_page_text(self, page_num: int) -> str:
        return ""

    def close(self) -> None:
        self.closed = True


class PipelineScannedKernelTest(unittest.IsolatedAsyncioTestCase):
    async def test_long_scanned_question_book_uses_kernel_instead_of_legacy_skip(self):
        calls = {"kernel": 0, "legacy": 0}

        def fake_markdown_parse(*args, **kwargs):
            calls["markdown"] = calls.get("markdown", 0) + 1
            return {"questions": [], "materials": [], "stats": {"total": 0}}

        def fake_kernel_parse(extractor, **kwargs):
            calls["kernel"] += 1
            return {
                "questions": [
                    {
                        "index": 1,
                        "type": "single",
                        "content": "第一题题干内容",
                        "option_a": "甲",
                        "option_b": "乙",
                        "option_c": "丙",
                        "option_d": "丁",
                        "options": {"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
                    }
                ],
                "materials": [],
                "pdf_kind": "scanned_question_book",
                "debug_dir": "/tmp/kernel-debug",
                "stats": {
                    "pages_count": 225,
                    "page_elements_count": 5,
                    "question_candidates_count": 1,
                    "accepted_questions_count": 1,
                    "rejected_questions_count": 0,
                    "materials_count": 0,
                    "visuals_count": 0,
                    "debug_dir": "/tmp/kernel-debug",
                },
            }

        class FakeLegacyStrategy:
            def parse(self, extractor, ai_client_module):
                calls["legacy"] += 1
                return {"questions": [], "materials": [], "stats": {}}

        with patch.object(pipeline.MarkdownQuestionStrategy, "parse", fake_markdown_parse), patch(
            "pipeline.PDFExtractor",
            FakeLongScannedExtractor,
        ), patch.object(
            pipeline.PDFDetector,
            "detect",
            return_value={"type": "pure_text", "confidence": 0.2, "stats": {}},
        ), patch.dict(
            pipeline.STRATEGIES,
            {"pure_text": FakeLegacyStrategy()},
        ), patch(
            "pipeline.parse_extractor_with_kernel",
            side_effect=fake_kernel_parse,
        ):
            result = await pipeline.parse_pdf("/tmp/题本篇.pdf")

        self.assertEqual(calls["kernel"], 1)
        self.assertEqual(calls.get("markdown", 0), 0)
        self.assertEqual(calls["legacy"], 0)
        self.assertEqual(len(result.questions), 1)
        self.assertEqual(result.stats.strategy, "ParserKernelScannedQuestionBook")
        self.assertEqual(result.stats.debug_counts["accepted_questions_count"], 1)
        self.assertEqual(result.stats.scanned_fallback_debug["kernel_visual_fallback_called"], True)


if __name__ == "__main__":
    unittest.main()
