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
            x1 = 1000.0
            y1 = 1400.0

        rect = _Rect()

    doc = [_Page()]

    def get_page_text(self, page_num: int) -> str:
        return ""

    def get_page_screenshot(self, page_num: int, dpi: int = 150, max_side: int | None = None) -> str:
        return "ZmFrZS1wYWdl"

    def get_page_screenshot_size(self, page_num: int, dpi: int = 150, max_side: int | None = None):
        return {"width": 1000, "height": 1400}

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
            requested_primary_provider="baidu_paper_cut_edu",
            effective_provider="local_parser",
            should_use_local_parser=True,
            attempted_providers=[{"provider": "baidu_paper_cut_edu", "status": "skipped_unavailable"}],
            warnings=["missing_baidu_api_key"],
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


if __name__ == "__main__":
    unittest.main()
