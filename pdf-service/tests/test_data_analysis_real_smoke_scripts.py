import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts.eval_data_analysis_real_quality_matrix import build_quality_matrix
from scripts.run_real_data_analysis_batch_smoke import (
    run_visual_context_with_strategy,
    select_fixture_questions,
)


class DataAnalysisRealSmokeScriptsTest(unittest.TestCase):
    def test_qwen_timeout_hedges_to_ark(self):
        configs = {
            "qwen_vl": {
                "configured": True,
                "provider": "qwen_vl",
                "api_key": "redacted",
                "base_url": "https://example.com",
                "model": "qwen-vl-max",
            },
            "volcengine_ark_vl": {
                "configured": True,
                "provider": "volcengine_ark_vl",
                "api_key": "redacted",
                "base_url": "https://ark.example.com",
                "model_candidates": [{"model": "doubao-seed-vision", "type": "model_name"}],
            },
        }
        ark_payload = {
            "source_material_complete": False,
            "chart_title_present": True,
            "table_header_present": False,
            "unit_present": False,
            "legend_present": True,
            "table_or_chart_readable": True,
            "material_group_visual_consistent": True,
            "suspected_crop_errors": ["source_material_incomplete"],
            "suspected_ocr_errors": ["table_header_missing"],
            "critical_data_points_visible": [],
            "visual_summary": "材料不完整。",
            "warnings": ["materials_incomplete"],
        }
        with TemporaryDirectory() as tmpdir, patch(
            "scripts.run_real_data_analysis_batch_smoke.ai_client.vision_provider_configs",
            return_value=configs,
        ), patch(
            "scripts.run_real_data_analysis_batch_smoke.call_openai_vision_json",
            side_effect=TimeoutError("soft timeout"),
        ), patch(
            "scripts.run_real_data_analysis_batch_smoke.call_ark_vision_json",
            return_value=(ark_payload, {"provider": "volcengine_ark_vl", "model": "doubao-seed-vision", "elapsed_ms": 321}),
        ):
            result, meta = run_visual_context_with_strategy(
                image_b64="ZmFrZS1pbWFnZQ==",
                prompt="{}",
                output_dir=Path(tmpdir),
                group_key="group-1",
            )

        self.assertEqual(result.model_provider, "volcengine_ark_vl")
        self.assertEqual(meta["selected_provider"], "volcengine_ark_vl")
        self.assertTrue(meta["fallback_used"])
        self.assertEqual(meta["attempts"][0]["provider"], "qwen_vl")
        self.assertEqual(meta["attempts"][0]["status"], "failed")
        self.assertEqual(meta["attempts"][1]["provider"], "volcengine_ark_vl")
        self.assertEqual(meta["attempts"][1]["status"], "ok")

    def test_mimo_is_deprioritized_when_primary_visual_providers_are_unavailable(self):
        configs = {
            "mimo_vl": {
                "configured": True,
                "provider": "mimo_vl",
                "api_key": "redacted",
                "base_url": "https://mimo.example.com",
                "model": "mimo-vl",
            }
        }
        with patch(
            "scripts.run_real_data_analysis_batch_smoke.ai_client.vision_provider_configs",
            return_value=configs,
        ):
            with self.assertRaises(RuntimeError) as context:
                run_visual_context_with_strategy(
                    image_b64="ZmFrZS1pbWFnZQ==",
                    prompt="{}",
                    output_dir=Path("/tmp"),
                    group_key="group-2",
                )
        payload = json.loads(str(context.exception))
        self.assertEqual(payload["attempts"][0]["provider"], "mimo_vl")
        self.assertEqual(payload["attempts"][0]["status"], "skipped")
        self.assertEqual(payload["attempts"][0]["error_type"], "deprioritized")

    def test_select_fixture_questions_prefers_real_17_20_subset(self):
        entry = {
            "questions": [
                {"question_no": 16},
                {"question_no": 17},
                {"question_no": 18},
                {"question_no": 19},
                {"question_no": 20},
            ]
        }
        selected = select_fixture_questions(entry, max_questions_per_group=4)
        self.assertEqual([item["question_no"] for item in selected], [17, 18, 19, 20])

    def test_quality_matrix_counts_timeout_hedge_and_non_local_bbox_sources(self):
        batch_summary = {
            "pdf_ref": "题本/题本篇.pdf",
            "group_summaries": [
                {
                    "group_key": "group-1",
                    "data_analysis_quality_gate": {
                        "review_ready": False,
                        "needs_human_review": True,
                        "blocking_reasons": ["source_material_incomplete"],
                        "warnings": ["materials_incomplete"],
                    },
                }
            ],
        }
        visual_summary = {
            "group_summaries": [
                {
                    "group_key": "group-1",
                    "ocr_provider": "tesseract_local_ocr",
                    "selected_provider": "volcengine_ark_vl",
                    "source_material_complete": False,
                    "provider_attempts": [
                        {"provider": "qwen_vl", "status": "failed", "error_type": "timeout"},
                        {"provider": "volcengine_ark_vl", "status": "ok"},
                    ],
                }
            ]
        }
        llm_summary = {
            "questions": [
                {
                    "question_no": 17,
                    "material_group_id": "group-1",
                    "can_solve_question": False,
                    "conflict_with_ocr_answer": False,
                    "comprehension_confidence": 0.25,
                    "needs_human_review": True,
                    "warnings": ["materials_incomplete"],
                }
            ]
        }
        matrix = build_quality_matrix(batch_summary, visual_summary, llm_summary)
        self.assertEqual(matrix["provider_timeout_count"], 1)
        self.assertEqual(matrix["provider_hedge_success_count"], 1)
        self.assertEqual(matrix["local_parser_fallback_count"], 0)
        self.assertEqual(matrix["bbox_from_ocr_provider_rate"], 1.0)
        self.assertEqual(matrix["needs_human_review_count"], 1)


if __name__ == "__main__":
    unittest.main()
