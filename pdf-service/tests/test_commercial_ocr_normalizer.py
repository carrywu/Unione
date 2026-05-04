import json
import unittest
from pathlib import Path

from commercial_ocr.normalizer import build_normalized_block, normalize_baidu_page_result, normalize_tencent_question_split_response


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "commercial_ocr"


class CommercialOCRNormalizerTest(unittest.TestCase):
    def test_baidu_fixture_normalizes(self):
        payload = json.loads((FIXTURE_ROOT / "baidu_paper_cut_edu_single_page_normalized.json").read_text(encoding="utf-8"))
        page = normalize_baidu_page_result(page_no=1, response_json=payload["response"], provider_name="baidu_paper_cut_edu")

        block_types = {block.block_type for block in page.blocks}
        self.assertIn("stem", block_types)
        self.assertIn("option", block_types)
        self.assertIn("answer", block_types)
        self.assertIn("analysis", block_types)

    def test_tencent_fixture_normalizes(self):
        payload = json.loads((FIXTURE_ROOT / "tencent_question_split_single_page_normalized.json").read_text(encoding="utf-8"))
        page = normalize_tencent_question_split_response(
            page_no=1,
            response_json=payload["response"],
            provider_name="tencent_question_split",
            layout_only=False,
        )
        self.assertGreaterEqual(len(page.blocks), 4)

    def test_tencent_layout_fixture_normalizes(self):
        payload = json.loads((FIXTURE_ROOT / "tencent_question_split_layout_single_page_normalized.json").read_text(encoding="utf-8"))
        page = normalize_tencent_question_split_response(
            page_no=1,
            response_json=payload["response"],
            provider_name="tencent_question_split_layout",
            layout_only=True,
        )
        self.assertTrue(all(block.block_type == "bbox_only" for block in page.blocks))

    def test_malformed_bbox_is_warned_and_cleared(self):
        block = build_normalized_block(
            block_id="bad-bbox",
            provider_ref="fixture:question:1",
            page_no=1,
            text="1. 第一题",
            bbox=[10, 20, 10, 5],
            block_type="stem",
            confidence=0.9,
            reading_order=1,
            raw={"ImageBase64": "abc"},
        )
        self.assertEqual(block.bbox, [])
        self.assertIn("bbox_invalid", block.warnings)

    def test_missing_confidence_adds_warning(self):
        block = build_normalized_block(
            block_id="missing-confidence",
            provider_ref="fixture:question:1",
            page_no=1,
            text="A. 甲",
            bbox=[10, 20, 30, 40],
            block_type="option",
            confidence=None,
            reading_order=1,
            raw={"access_token": "should-be-redacted"},
        )
        self.assertIn("confidence_missing", block.warnings)
        self.assertEqual(block.raw["access_token"], "[redacted]")

    def test_provider_ref_missing_is_rejected(self):
        with self.assertRaises(ValueError):
            build_normalized_block(
                block_id="missing-provider-ref",
                provider_ref="",
                page_no=1,
                text="1. 第一题",
                bbox=[10, 20, 30, 40],
                block_type="stem",
                confidence=0.9,
                reading_order=1,
            )


if __name__ == "__main__":
    unittest.main()
