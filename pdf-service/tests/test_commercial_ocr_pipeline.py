import unittest
from unittest.mock import patch

from commercial_ocr.adapters import BaiduPaperCutEduProvider
from commercial_ocr.service import provider_result_to_page_contents, run_commercial_ocr_pipeline


class FakeExtractor:
    total_pages = 1
    pdf_path = "/tmp/mock-paper.pdf"

    class _Page:
        class _Rect:
            x0 = 0.0
            y0 = 0.0
            x1 = 1000.0
            y1 = 1400.0

        rect = _Rect()

    doc = [_Page()]

    def __init__(self, text: str = "1. 根据以下资料，回答 1-2 题\nA. 甲\nB. 乙"):
        self.text = text

    def get_page_text(self, page_num: int) -> str:
        return self.text

    def get_page_screenshot(self, page_num: int, dpi: int = 150, max_side: int | None = None) -> str:
        return "ZmFrZS1wYWdl"

    def get_region_screenshot(self, page_num: int, rect, padding: int = 10) -> str:
        return "ZmFrZS1yZWdpb24="


class CommercialOCRPipelineTest(unittest.TestCase):
    def test_mock_provider_selected_without_real_http(self):
        with patch.dict(
            "os.environ",
            {
                "COMMERCIAL_OCR_ENABLED": "true",
                "PDF_PARSE_PRIMARY_PROVIDER": "mock_commercial_ocr",
                "PDF_PARSE_FALLBACK_PROVIDERS": "local_parser",
            },
            clear=False,
        ), patch("commercial_ocr.adapters.httpx.Client.post", side_effect=AssertionError("real http should not be called")):
            execution = run_commercial_ocr_pipeline(FakeExtractor(), total_pages=1, debug_dir=None)

        self.assertEqual(execution.effective_provider, "mock_commercial_ocr")
        self.assertFalse(execution.fallback_used)
        self.assertFalse(execution.should_use_local_parser)
        self.assertIsNotNone(execution.provider_result)
        pages = provider_result_to_page_contents(FakeExtractor(), execution.provider_result)
        self.assertEqual(pages[0].page_num, 1)
        self.assertIn("根据以下资料", pages[0].text)

    def test_missing_baidu_keys_skips_real_provider_and_falls_back_to_mock(self):
        with patch.dict(
            "os.environ",
            {
                "COMMERCIAL_OCR_ENABLED": "true",
                "PDF_PARSE_PRIMARY_PROVIDER": "baidu_paper_cut_edu",
                "PDF_PARSE_FALLBACK_PROVIDERS": "mock_commercial_ocr,local_parser",
                "BAIDU_API_KEY": "",
                "BAIDU_SECRET_KEY": "",
                "BAIDU_ACCESS_TOKEN": "",
            },
            clear=False,
        ):
            execution = run_commercial_ocr_pipeline(FakeExtractor(), total_pages=1, debug_dir=None)

        self.assertEqual(execution.effective_provider, "mock_commercial_ocr")
        self.assertTrue(execution.fallback_used)
        self.assertEqual(execution.attempted_providers[0]["provider"], "baidu_paper_cut_edu")
        self.assertEqual(execution.attempted_providers[0]["status"], "skipped_unavailable")
        self.assertEqual(execution.attempted_providers[1]["provider"], "mock_commercial_ocr")
        self.assertEqual(execution.attempted_providers[1]["status"], "ok")

    def test_provider_error_is_preserved_before_fallback(self):
        with patch.dict(
            "os.environ",
            {
                "COMMERCIAL_OCR_ENABLED": "true",
                "PDF_PARSE_PRIMARY_PROVIDER": "baidu_paper_cut_edu",
                "PDF_PARSE_FALLBACK_PROVIDERS": "mock_commercial_ocr,local_parser",
                "BAIDU_ACCESS_TOKEN": "token-for-test",
            },
            clear=False,
        ), patch.object(
            BaiduPaperCutEduProvider,
            "_post_page",
            return_value={"error_code": 18, "error_msg": "Open api qps request limit reached"},
        ):
            execution = run_commercial_ocr_pipeline(FakeExtractor(), total_pages=1, debug_dir=None)

        self.assertEqual(execution.effective_provider, "mock_commercial_ocr")
        self.assertTrue(execution.fallback_used)
        self.assertEqual(execution.attempted_providers[0]["status"], "error")
        self.assertEqual(execution.attempted_providers[0]["provider_error"]["code"], "18")
        self.assertEqual(execution.attempted_providers[1]["status"], "ok")

    def test_local_parser_selection_short_circuits(self):
        with patch.dict(
            "os.environ",
            {
                "COMMERCIAL_OCR_ENABLED": "true",
                "PDF_PARSE_PRIMARY_PROVIDER": "local_parser",
                "PDF_PARSE_FALLBACK_PROVIDERS": "mock_commercial_ocr",
            },
            clear=False,
        ):
            execution = run_commercial_ocr_pipeline(FakeExtractor(), total_pages=1, debug_dir=None)

        self.assertTrue(execution.should_use_local_parser)
        self.assertEqual(execution.effective_provider, "local_parser")
        self.assertIsNone(execution.provider_result)


class BaiduNormalizationTest(unittest.TestCase):
    def test_baidu_normalization_maps_question_fields_into_blocks(self):
        provider = BaiduPaperCutEduProvider()
        page = provider._normalize_page_result(
            page_no=1,
            response_json={
                "log_id": 1,
                "qus_result": [
                    {
                        "question_id": "17",
                        "qus_probability": 0.96,
                        "qus_location": {"left": 10, "top": 20, "width": 300, "height": 180},
                        "stem_text": "根据以下资料，回答17-20题",
                        "option_text": "A. 甲 B. 乙 C. 丙 D. 丁",
                        "answer_text": "A",
                        "interpretation_text": "解析内容",
                    }
                ],
            },
        )

        by_type = {block.block_type for block in page.blocks}
        self.assertIn("stem", by_type)
        self.assertIn("option", by_type)
        self.assertIn("answer", by_type)
        self.assertIn("analysis", by_type)


if __name__ == "__main__":
    unittest.main()
