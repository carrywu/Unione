import unittest
from types import SimpleNamespace

from scripts.compare_commercial_vs_local_bbox import compare_page_summaries
from scripts.run_real_data_analysis_batch_smoke import provider_page_summary


class RealCommercialOcrScriptsTest(unittest.TestCase):
    def test_provider_page_summary_classifies_missing_keys(self):
        summary = provider_page_summary(
            candidate={"page_no": 6},
            provider_name="tencent_question_split",
            provider_status="skipped_unavailable",
            provider_latency_ms=0,
            assembly=None,
            result=None,
            warnings=["missing_tencent_secret_id", "missing_tencent_secret_key"],
        )
        self.assertEqual(summary["skipped_reason"], "key_missing")
        self.assertEqual(summary["question_count"], 0)
        self.assertIsNone(summary["raw_ref_redacted"])

    def test_provider_page_summary_classifies_auth_failure(self):
        result = SimpleNamespace(
            raw_response_ref="/tmp/provider/failure.json",
            provider_error={"code": "AuthFailure.SignatureFailure", "message": "signature invalid"},
        )
        summary = provider_page_summary(
            candidate={"page_no": 1},
            provider_name="tencent_question_split",
            provider_status="error",
            provider_latency_ms=128,
            assembly=None,
            result=result,
            warnings=["tencent_auth_error"],
        )
        self.assertEqual(summary["skipped_reason"], "auth_failed")
        self.assertEqual(summary["errors"][0]["code"], "AuthFailure.SignatureFailure")
        self.assertTrue(str(summary["raw_ref_redacted"]).endswith("failure.json"))

    def test_provider_page_summary_clears_skipped_reason_for_success(self):
        result = SimpleNamespace(
            raw_response_ref="/tmp/provider/success.json",
            provider_error={"code": "http_request_failed", "message": "request failed earlier"},
        )
        summary = provider_page_summary(
            candidate={"page_no": 1},
            provider_name="baidu_paper_cut_edu",
            provider_status="ok",
            provider_latency_ms=10,
            assembly=None,
            result=result,
            warnings=["provider_http_error"],
        )
        self.assertIsNone(summary["skipped_reason"])

    def test_compare_page_summaries_prefers_commercial_when_bboxs_exist(self):
        commercial = {
            "provider": "baidu_paper_cut_edu",
            "status": "ok",
            "bbox_count": 2,
            "question_numbers": [17, 18],
            "question_bboxes": [
                {"question_no": 17, "bbox": [0, 0, 50, 50]},
                {"question_no": 18, "bbox": [60, 0, 120, 50]},
            ],
            "material_bboxes": [
                {"material_id": "m1", "bbox": [0, 0, 200, 120]},
            ],
        }
        local = {
            "provider": "tesseract_local_ocr",
            "status": "ok_local_fallback",
            "bbox_count": 2,
            "question_numbers": [17, 18, 19],
            "question_bboxes": [
                {"question_no": 17, "bbox": [5, 5, 55, 55]},
                {"question_no": 18, "bbox": [62, 0, 122, 50]},
            ],
            "material_bboxes": [
                {"material_id": "local-1", "bbox": [0, 0, 210, 120]},
            ],
        }
        comparison = compare_page_summaries(commercial, local, 16)
        self.assertEqual(comparison["recommended_source"], "commercial")
        self.assertEqual(comparison["commercial_missing"], [19])
        self.assertEqual(comparison["local_missing"], [])
        self.assertEqual(comparison["question_bbox_overlap"], 1.0)
        self.assertEqual(comparison["material_bbox_overlap"], 1.0)


if __name__ == "__main__":
    unittest.main()
