import unittest
from unittest.mock import patch

from strategies.text_strategy import TextStrategy


class FakeExtractor:
    total_pages = 1
    pdf_path = "/tmp/fake.pdf"

    def get_page_text(self, page_num: int) -> str:
        return "1. 下列说法正确的是？\nA. 甲\nB. 乙\nC. 丙\nD. 丁\n"


class FakeAiClient:
    @staticmethod
    def parse_text_block(text: str):
        return []


class TextStrategyKernelFallbackTest(unittest.TestCase):
    def test_text_strategy_fallback_uses_kernel(self):
        calls = {"count": 0}

        def fake_parse_extractor_with_kernel(extractor):
            calls["count"] += 1
            return {
                "questions": [
                    {
                        "index": 1,
                        "type": "single",
                        "content": "下列说法正确的是？",
                        "options": {"A": "甲", "B": "乙", "C": "丙", "D": "丁"},
                        "option_a": "甲",
                        "option_b": "乙",
                        "option_c": "丙",
                        "option_d": "丁",
                    }
                ],
                "materials": [],
            }

        with patch(
            "strategies.text_strategy.parse_extractor_with_kernel",
            fake_parse_extractor_with_kernel,
        ):
            result = TextStrategy().parse(FakeExtractor(), FakeAiClient())

        self.assertEqual(calls["count"], 1)
        self.assertEqual(len(result["questions"]), 1)


if __name__ == "__main__":
    unittest.main()
