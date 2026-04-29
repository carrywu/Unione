import unittest

from block_segmenter import _clean_stem
from validator import _clean_question


class OrphanCornerBracketCleanupTest(unittest.TestCase):
    def test_clean_stem_removes_trailing_orphan_open_bracket(self):
        content = _clean_stem(
            "1. （2024 河北事业单位）煤炭进口2868 万吨。\n【",
            "1.",
        )

        self.assertEqual(content, "（2024 河北事业单位）煤炭进口2868 万吨。")

    def test_clean_stem_removes_leading_orphan_close_bracket(self):
        content = _clean_stem(
            "】（2025 浙江事业单位）融资事件少于100 起的轮次有几个？",
            "例15】",
        )

        self.assertEqual(content, "（2025 浙江事业单位）融资事件少于100 起的轮次有几个？")

    def test_validator_removes_standalone_orphan_bracket_lines(self):
        cleaned = _clean_question(
            {
                "index": 1,
                "type": "single",
                "content": "（2024 河北事业单位）煤炭进口2868 万吨。\n【",
                "option_a": "A. 1",
                "option_b": "B. 2",
                "option_c": "C. 3",
                "option_d": "D. 4",
            }
        )

        self.assertIsNotNone(cleaned)
        self.assertEqual(cleaned["content"], "（2024 河北事业单位）煤炭进口2868 万吨。")


if __name__ == "__main__":
    unittest.main()
