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

    def test_validator_filters_visual_parse_placeholders_from_question_fields(self):
        cleaned = _clean_question(
            {
                "index": 5,
                "type": "single",
                "content": "[page 5 visual parse unavailable]\n2017～2021 五年间重庆市城镇常住居民人均可支配收入与农村常住居民人均可支配收入之比最小的是：",
                "option_a": "A. 2017 年",
                "option_b": "[visual parse unavailable]",
                "option_c": "C. 2020 年",
                "option_d": "D. 2021 年",
                "analysis": "visual parse unavailable",
            }
        )

        self.assertIsNotNone(cleaned)
        serialized = "\n".join(
            str(cleaned.get(key) or "")
            for key in ["content", "option_a", "option_b", "option_c", "option_d", "analysis"]
        ).lower()
        self.assertNotIn("visual parse unavailable", serialized)
        self.assertNotIn("[page 5 visual parse", serialized)
        self.assertIn("placeholder_filtered", cleaned["parse_warnings"])


if __name__ == "__main__":
    unittest.main()
