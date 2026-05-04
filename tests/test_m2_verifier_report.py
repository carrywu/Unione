import unittest

from scripts.m2_verifier_report import build_verifier_report, merge_question_numbers


class M2VerifierReportTest(unittest.TestCase):
    def test_page5_recovery_can_raise_question_count_from_16_to_20(self):
        produced = merge_question_numbers(list(range(1, 17)), [17, 18, 19, 20])

        report = build_verifier_report(
            task_id="task-1",
            produced_question_numbers=produced,
            expected_total=20,
            fallback_failed_pages=[],
            provider_recovery={
                "new_provider": "volcengine_ark_vl",
                "used_for_page_5": True,
                "provider_health": "pass",
            },
            debug_live_consistency="pass",
        )

        self.assertEqual(report["produced_question_count"], 20)
        self.assertEqual(report["missing_question_numbers"], [])
        self.assertEqual(report["m2_verdict"], "M2_PASS")

    def test_no_fake_pass_when_provider_recovery_failed(self):
        report = build_verifier_report(
            task_id="task-2",
            produced_question_numbers=list(range(1, 17)),
            expected_total=20,
            fallback_failed_pages=[5],
            provider_recovery={
                "new_provider": "volcengine_ark_vl",
                "used_for_page_5": True,
                "provider_health": "fail",
            },
            debug_live_consistency="pass",
        )

        self.assertEqual(report["m2_verdict"], "M2_FAIL")
        self.assertFalse(report["m3_allowed"])
        self.assertIn("fallback_failed_pages=[5]", report["failed_checks"])


if __name__ == "__main__":
    unittest.main()
