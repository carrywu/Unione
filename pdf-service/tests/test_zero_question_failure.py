import unittest

from main import _result_payload, _summary_payload
from models import ParseResult, ParseStats


class ZeroQuestionFailureTest(unittest.TestCase):
    def make_result(self):
        return ParseResult(
            questions=[],
            materials=[],
            stats=ParseStats(
                total_pages=12,
                total_questions=0,
                has_images=False,
                needs_review_count=0,
                suspected_bad_parse=True,
                warnings=["zero_questions_extracted"],
                debug_counts={
                    "pages_count": 12,
                    "page_elements_count": 0,
                    "question_candidates_count": 0,
                    "accepted_questions_count": 0,
                    "rejected_questions_count": 0,
                    "materials_count": 0,
                    "visuals_count": 0,
                },
                scanned_fallback_debug={
                    "pdf_kind": "scanned_question_book",
                    "legacy_visual_fallback_called": False,
                },
            ),
        )

    def test_result_payload_does_not_report_success_for_zero_questions(self):
        payload = _result_payload(self.make_result())
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["error"], "未解析到题目")
        self.assertTrue(payload["stats"]["suspected_bad_parse"])
        self.assertIn("zero_questions_extracted", payload["stats"]["warnings"])
        self.assertEqual(payload["stats"]["debug_counts"]["accepted_questions_count"], 0)

    def test_summary_payload_does_not_report_success_for_zero_questions(self):
        payload = _summary_payload(self.make_result())
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["error"], "未解析到题目")
        self.assertEqual(payload["questions_count"], 0)
        self.assertTrue(payload["stats"]["suspected_bad_parse"])


if __name__ == "__main__":
    unittest.main()
