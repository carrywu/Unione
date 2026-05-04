import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from commercial_ocr.normalizer import normalize_tencent_question_split_response
from commercial_ocr.tencent_provider import TencentQuestionSplitLayoutProvider, TencentQuestionSplitProvider


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "commercial_ocr"


class FakeExtractor:
    total_pages = 1
    pdf_path = "/tmp/mock-paper.pdf"

    def get_page_screenshot(self, page_num: int, dpi: int = 160, max_side: int | None = None) -> str:
        return "ZmFrZS1wYWdl"


class TencentOCRProviderTest(unittest.TestCase):
    def test_tencent_provider_requires_secret_and_explicit_smoke_flag(self):
        with patch.dict(
            "os.environ",
            {
                "TENCENT_SECRET_ID": "AKIDMASKED",
                "TENCENT_SECRET_KEY": "masked-secret",
                "TENCENT_OCR_REAL_SMOKE": "false",
            },
            clear=False,
        ):
            provider = TencentQuestionSplitProvider()

        available, reasons = provider.is_available()
        self.assertFalse(available)
        self.assertIn("tencent_real_smoke_disabled", reasons)

    def test_tencent_question_split_fixture_normalizes_into_blocks(self):
        payload = json.loads((FIXTURE_ROOT / "tencent_question_split_single_page_normalized.json").read_text(encoding="utf-8"))
        page = normalize_tencent_question_split_response(
            page_no=1,
            response_json=payload["response"],
            provider_name="tencent_question_split",
            layout_only=False,
        )

        block_types = {block.block_type for block in page.blocks}
        self.assertIn("stem", block_types)
        self.assertIn("option", block_types)
        self.assertIn("answer", block_types)
        self.assertIn("chart", block_types)

    def test_tencent_layout_fixture_normalizes_into_bbox_only_blocks(self):
        payload = json.loads((FIXTURE_ROOT / "tencent_question_split_layout_single_page_normalized.json").read_text(encoding="utf-8"))
        page = normalize_tencent_question_split_response(
            page_no=1,
            response_json=payload["response"],
            provider_name="tencent_question_split_layout",
            layout_only=True,
        )

        self.assertTrue(page.blocks)
        self.assertTrue(all(block.block_type == "bbox_only" for block in page.blocks))

    @unittest.skipUnless(
        str(os.getenv("TENCENT_OCR_REAL_SMOKE") or "").strip().lower() in {"1", "true", "yes", "on"}
        and str(os.getenv("TENCENT_SECRET_ID") or "").strip()
        and str(os.getenv("TENCENT_SECRET_KEY") or "").strip(),
        "Tencent real smoke is disabled by default",
    )
    def test_tencent_real_smoke_single_page_is_explicitly_gated(self):
        provider = TencentQuestionSplitProvider()
        with patch.object(provider, "_invoke_sdk", return_value={"Response": {"QuestionInfo": [], "RequestId": "smoke"}}):
            result = provider.analyze_document(
                type(
                    "Request",
                    (),
                    {
                        "extractor": FakeExtractor(),
                        "pdf_path": "/tmp/mock-paper.pdf",
                        "source_document_id": "doc",
                        "task_id": "task",
                        "page_numbers": [1],
                        "debug_dir": None,
                        "trace_enabled": False,
                    },
                )()
            )
        self.assertEqual(result.provider_status, "ok")


if __name__ == "__main__":
    unittest.main()
