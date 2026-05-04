import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

from commercial_ocr.types import CommercialOCRExecution
from models import PageContent, TextBlock
from parser_kernel.adapter import parse_extractor_with_kernel


class FakeScannedExtractor:
    total_pages = 1
    pdf_path = "/tmp/题本篇.pdf"

    class _Page:
        class _Rect:
            x0 = 0.0
            y0 = 0.0
            x1 = 1400.0
            y1 = 1800.0

        rect = _Rect()

    doc = [_Page()]

    def get_page_text(self, page_num: int) -> str:
        return ""

    def get_page_screenshot(self, page_num: int, dpi: int = 150, max_side: int | None = None) -> str:
        return "ZmFrZS1wYWdl"

    def get_page_screenshot_size(self, page_num: int, dpi: int = 150, max_side: int | None = None):
        return {"width": 1400, "height": 1800}

    def get_region_screenshot(self, page_num: int, rect, padding: int = 10) -> str:
        return "ZmFrZS1yZWdpb24="


class CommercialOCRKernelIntegrationTest(unittest.TestCase):
    def test_local_parser_fallback_is_preserved_when_execution_requests_it(self):
        fallback_pages = [
            PageContent(
                page_num=1,
                text="1. 第一题\nA. 甲\nB. 乙",
                blocks=[
                    TextBlock(bbox=[0.0, 0.0, 100.0, 20.0], text="1. 第一题"),
                    TextBlock(bbox=[0.0, 30.0, 100.0, 50.0], text="A. 甲"),
                    TextBlock(bbox=[0.0, 60.0, 100.0, 80.0], text="B. 乙"),
                ],
                regions=[],
            )
        ]
        execution = CommercialOCRExecution(
            requested_primary_provider="mock_tencent_question_split_layout",
            effective_provider="local_parser",
            should_use_local_parser=True,
            attempted_providers=[{"provider": "mock_tencent_question_split_layout", "status": "ok"}],
            warnings=["provider_output_requires_fallback:mock_tencent_question_split_layout"],
        )

        with TemporaryDirectory() as tmpdir, patch(
            "parser_kernel.adapter.run_commercial_ocr_pipeline",
            return_value=execution,
        ), patch(
            "parser_kernel.adapter._pages_from_visual_fallback",
            return_value=fallback_pages,
        ):
            result = parse_extractor_with_kernel(FakeScannedExtractor(), debug_dir=tmpdir)

        self.assertEqual(result["stats"]["commercial_ocr"]["effective_provider"], "local_parser")
        self.assertTrue(result["stats"]["commercial_ocr"]["should_use_local_parser"])

    def test_mock_provider_summary_contains_semantic_assembly_and_quality_gate(self):
        with TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {
                "COMMERCIAL_OCR_ENABLED": "true",
                "PDF_PARSE_PRIMARY_PROVIDER": "mock_commercial_ocr",
                "PDF_PARSE_FALLBACK_PROVIDERS": "local_parser",
            },
            clear=False,
        ):
            result = parse_extractor_with_kernel(FakeScannedExtractor(), debug_dir=tmpdir)

        commercial_ocr = result["stats"]["commercial_ocr"]
        self.assertEqual(commercial_ocr["effective_provider"], "mock_commercial_ocr")
        self.assertIsNotNone(commercial_ocr["semantic_assembly"])
        self.assertIsNotNone(commercial_ocr["quality_gate"])
        self.assertGreaterEqual(len(commercial_ocr["semantic_assembly"]["material_groups"]), 1)
        self.assertGreaterEqual(len(commercial_ocr["semantic_assembly"]["normalized_questions"]), 1)


if __name__ == "__main__":
    unittest.main()
