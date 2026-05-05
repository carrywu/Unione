import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from commercial_ocr.service import (
    build_question_enrichment_payloads,
    provider_result_to_page_contents,
    run_commercial_ocr_pipeline,
)


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "commercial_ocr"


class FakeExtractor:
    total_pages = 1
    pdf_path = "/tmp/mock-paper.pdf"

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

    def get_region_screenshot(self, page_num: int, rect, padding: int = 10) -> str:
        return "ZmFrZS1yZWdpb24="


class CommercialOCRPipelineTest(unittest.TestCase):
    def test_mock_provider_is_deterministic_and_does_not_call_network(self):
        with patch.dict(
            "os.environ",
            {
                "COMMERCIAL_OCR_ENABLED": "true",
                "PDF_PARSE_PRIMARY_PROVIDER": "mock_commercial_ocr",
                "PDF_PARSE_FALLBACK_PROVIDERS": "local_parser,mock_commercial_ocr",
            },
            clear=False,
        ), patch("commercial_ocr.adapters.httpx.Client.post", side_effect=AssertionError("real http should not be called")):
            first_execution = run_commercial_ocr_pipeline(FakeExtractor(), total_pages=1, debug_dir=None)
            second_execution = run_commercial_ocr_pipeline(FakeExtractor(), total_pages=1, debug_dir=None)

        self.assertEqual(first_execution.effective_provider, "mock_commercial_ocr")
        self.assertEqual(second_execution.effective_provider, "mock_commercial_ocr")
        self.assertEqual(
            [block.to_dict() for block in first_execution.provider_result.page_results[0].blocks],
            [block.to_dict() for block in second_execution.provider_result.page_results[0].blocks],
        )
        pages = provider_result_to_page_contents(FakeExtractor(), first_execution.provider_result)
        self.assertIn("根据以下资料，回答17-20题", pages[0].text)

    def test_mock_tencent_provider_returns_normalized_blocks(self):
        with patch.dict(
            "os.environ",
            {
                "COMMERCIAL_OCR_ENABLED": "true",
                "PDF_PARSE_PRIMARY_PROVIDER": "mock_tencent_question_split",
                "PDF_PARSE_FALLBACK_PROVIDERS": "local_parser",
            },
            clear=False,
        ):
            execution = run_commercial_ocr_pipeline(FakeExtractor(), total_pages=1, debug_dir=None)

        self.assertEqual(execution.effective_provider, "mock_tencent_question_split")
        block_types = {block.block_type for block in execution.provider_result.page_results[0].blocks}
        self.assertIn("stem", block_types)
        self.assertIn("option", block_types)
        self.assertIn("answer", block_types)
        self.assertIn("chart", block_types)

    def test_mock_layout_provider_triggers_local_parser_fallback(self):
        with patch.dict(
            "os.environ",
            {
                "COMMERCIAL_OCR_ENABLED": "true",
                "PDF_PARSE_PRIMARY_PROVIDER": "mock_tencent_question_split_layout",
                "PDF_PARSE_FALLBACK_PROVIDERS": "local_parser",
            },
            clear=False,
        ):
            execution = run_commercial_ocr_pipeline(FakeExtractor(), total_pages=1, debug_dir=None)

        self.assertEqual(execution.effective_provider, "local_parser")
        self.assertTrue(execution.should_use_local_parser)
        self.assertIn("provider_output_requires_fallback:mock_tencent_question_split_layout", execution.warnings)

    def test_missing_baidu_keys_skip_real_provider_and_fall_back_to_mock(self):
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
        self.assertEqual(execution.attempted_providers[0]["status"], "skipped_unavailable")

    def test_provider_failure_triggers_fallback(self):
        with patch.dict(
            "os.environ",
            {
                "COMMERCIAL_OCR_ENABLED": "true",
                "PDF_PARSE_PRIMARY_PROVIDER": "mock_tencent_question_split",
                "PDF_PARSE_FALLBACK_PROVIDERS": "mock_commercial_ocr,local_parser",
                "MOCK_TENCENT_QUESTION_SPLIT_STATUS": "error",
                "MOCK_TENCENT_QUESTION_SPLIT_ERROR_CODE": "timeout",
                "MOCK_TENCENT_QUESTION_SPLIT_ERROR_MESSAGE": "fixture timeout",
            },
            clear=False,
        ):
            execution = run_commercial_ocr_pipeline(FakeExtractor(), total_pages=1, debug_dir=None)

        self.assertEqual(execution.effective_provider, "mock_commercial_ocr")
        self.assertEqual(execution.attempted_providers[0]["provider_error"]["code"], "timeout")
        self.assertEqual(execution.attempted_providers[1]["status"], "ok")

    def test_mock_provider_fixture_override_can_switch_to_publishable_shared_material_case(self):
        with patch.dict(
            "os.environ",
            {
                "COMMERCIAL_OCR_ENABLED": "true",
                "PDF_PARSE_PRIMARY_PROVIDER": "mock_commercial_ocr",
                "PDF_PARSE_FALLBACK_PROVIDERS": "local_parser",
                "MOCK_COMMERCIAL_OCR_FIXTURE_NAME": "shared_material_17_20_complete_blocks.json",
            },
            clear=False,
        ):
            execution = run_commercial_ocr_pipeline(FakeExtractor(), total_pages=1, debug_dir=None)

        self.assertEqual(execution.effective_provider, "mock_commercial_ocr")
        self.assertTrue(str(execution.provider_result.raw_response_ref).endswith("shared_material_17_20_complete_blocks.json"))
        self.assertEqual(
            [question.question_no for question in execution.semantic_assembly.normalized_questions],
            [17, 18, 19, 20],
        )
        self.assertTrue(execution.quality_gate.review_ready)
        self.assertFalse(execution.quality_gate.extracted_but_incomplete)

    def test_single_page_fixture_is_not_replicated_across_multi_page_pdf_requests(self):
        with patch.dict(
            "os.environ",
            {
                "COMMERCIAL_OCR_ENABLED": "true",
                "PDF_PARSE_PRIMARY_PROVIDER": "mock_commercial_ocr",
                "PDF_PARSE_FALLBACK_PROVIDERS": "local_parser",
                "MOCK_COMMERCIAL_OCR_FIXTURE_NAME": "shared_material_17_20_complete_blocks.json",
            },
            clear=False,
        ):
            execution = run_commercial_ocr_pipeline(FakeExtractor(), total_pages=5, debug_dir=None)

        self.assertEqual(execution.effective_provider, "mock_commercial_ocr")
        self.assertEqual(len(execution.provider_result.page_results), 1)
        self.assertEqual(
            [question.question_no for question in execution.semantic_assembly.normalized_questions],
            [17, 18, 19, 20],
        )
        self.assertTrue(execution.quality_gate.review_ready)

    def test_fixture_files_do_not_contain_secrets(self):
        forbidden_tokens = [
            "AKID",
            "8cvtLMOjDgFQfBvGEujwpi0v",
            "371QkcTrZoHo0Qz3wTTZaKWTERrGIstY",
            "access_token",
            "SecretId",
            "SecretKey"
        ]
        for path in FIXTURE_ROOT.glob("*.json"):
            content = path.read_text(encoding="utf-8")
            for token in forbidden_tokens:
                self.assertNotIn(token, content, msg=f"fixture {path.name} unexpectedly contains {token}")

    def test_precomputed_data_analysis_import_overrides_enrichment_and_bbox_source(self):
        base_payload = json.loads((FIXTURE_ROOT / "shared_material_17_20_complete_blocks.json").read_text(encoding="utf-8"))
        base_payload["precomputed_data_analysis"] = {
            "import_metadata": {
                "source": "real_data_analysis_batch_smoke",
                "bbox_source": "baidu_paper_cut_edu",
                "per_question": {
                    "17": {"bbox_source": "baidu_paper_cut_edu"},
                    "18": {"bbox_source": "baidu_paper_cut_edu"},
                    "19": {"bbox_source": "baidu_paper_cut_edu"},
                    "20": {"bbox_source": "baidu_paper_cut_edu"},
                },
            },
            "data_analysis_visual_context": {
                "model_provider": "volcengine_ark_vl",
                "model_name": "doubao-seed-vision",
                "source_material_complete": False,
                "chart_title_present": False,
                "table_header_present": False,
                "unit_present": False,
                "legend_present": True,
                "table_or_chart_readable": True,
                "material_group_visual_consistent": True,
                "suspected_crop_errors": ["source_material_incomplete"],
                "suspected_ocr_errors": ["table_header_missing"],
                "critical_data_points_visible": ["云浮 22016 423.9 296.0"],
                "visual_summary": "材料不完整，缺少表头和上半页地市。",
                "warnings": ["materials_incomplete"],
            },
            "data_analysis_understanding_results": [
                {
                    "model_provider": "qwen_text",
                    "model_name": "qwen-plus",
                    "question_no": 17,
                    "can_understand_material": False,
                    "can_solve_question": False,
                    "answer_suggestion": None,
                    "calculation_reasoning": "缺表头、缺单位、缺前半页地市，无法可靠计算。",
                    "formula_used": "比重变化比较",
                    "data_points_used": [],
                    "missing_information": ["table_header", "unit", "full_city_list"],
                    "ocr_answer_agreement": "no_ocr_answer",
                    "conflict_with_ocr_answer": False,
                    "comprehension_confidence": 0.25,
                    "needs_human_review": True,
                    "warnings": ["materials_incomplete"],
                }
            ],
            "data_analysis_quality_gate": {
                "has_shared_material": True,
                "has_valid_question_range": True,
                "children_share_same_material_id": True,
                "shared_assets_preserved": True,
                "table_header_complete": False,
                "unit_complete": False,
                "chart_title_complete": False,
                "local_stem_not_polluted": True,
                "llm_can_understand_material": False,
                "llm_can_solve_question": False,
                "calculation_reasoning_present": True,
                "answer_conflict": False,
                "comprehension_confidence": 0.25,
                "review_ready": False,
                "needs_human_review": True,
                "blocking_reasons": ["table_header_missing", "llm_cannot_understand_material"],
                "warnings": ["materials_incomplete"],
            },
        }
        with TemporaryDirectory() as tmpdir:
            fixture_path = Path(tmpdir) / "real-smoke-import.json"
            fixture_path.write_text(json.dumps(base_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            with patch.dict(
                "os.environ",
                {
                    "COMMERCIAL_OCR_ENABLED": "true",
                    "PDF_PARSE_PRIMARY_PROVIDER": "mock_commercial_ocr",
                    "PDF_PARSE_FALLBACK_PROVIDERS": "local_parser",
                    "COMMERCIAL_OCR_FIXTURE_ROOT": tmpdir,
                    "MOCK_COMMERCIAL_OCR_FIXTURE_NAME": fixture_path.name,
                },
                clear=False,
            ):
                execution = run_commercial_ocr_pipeline(FakeExtractor(), total_pages=1, debug_dir=None)

        self.assertEqual(execution.data_analysis_visual_context.model_provider, "volcengine_ark_vl")
        self.assertTrue(execution.data_analysis_quality_gate.needs_human_review)
        self.assertEqual(execution.import_metadata["bbox_source"], "baidu_paper_cut_edu")
        enrichments = build_question_enrichment_payloads(execution)
        self.assertEqual(enrichments[17]["bbox_source"], "baidu_paper_cut_edu")
        self.assertEqual(
            enrichments[17]["question_quality"]["commercial_ocr"]["bbox_source"],
            "baidu_paper_cut_edu",
        )
        self.assertTrue(execution.quality_gate.needs_human_review)


if __name__ == "__main__":
    unittest.main()
