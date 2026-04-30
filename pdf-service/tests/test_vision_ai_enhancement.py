from __future__ import annotations

import os
import unittest
from copy import deepcopy
from tempfile import TemporaryDirectory
from unittest.mock import patch

from vision_ai.enhancer import enhance_questions_with_vision_ai, should_call_vision_ai
from vision_ai.schema import VisionAIResponse


class FakeProvider:
    def __init__(self, response=None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls = []

    def review_page(self, request):
        self.calls.append(request)
        if self.error:
            raise self.error
        return self.response


def q5_q6_questions():
    return [
        {
            "id": "q5",
            "index": 5,
            "content": "2016 年全国参加失业保险的人数超过1.8 亿人\n例5题干",
            "images": [],
            "visual_refs": [],
            "image_refs": [],
            "source_bbox": [65.22, 224.69, 476.18, 339.37],
            "source_page_start": 3,
            "source_page_end": 3,
            "parse_confidence": 0.9,
            "needs_review": False,
            "parse_warnings": [],
        },
        {
            "id": "q6",
            "index": 6,
            "content": "（2025 浙江事业单位）若保持2023 年同比增量不变，哪一年全国规模以上文化新业态企业营业收入第一次超过60000 亿元？",
            "images": [],
            "visual_refs": [],
            "image_refs": [],
            "source_bbox": [65.22, 100.85, 476.01, 224.23],
            "source_page_start": 4,
            "source_page_end": 4,
            "parse_confidence": 0.9,
            "needs_review": False,
            "parse_warnings": [],
        },
    ]


def page_elements():
    return [
        {"id": "e59", "page": 3, "type": "caption", "text": "2023 年全国规模以上文化及相关产业企业相关指标情况", "bbox": [148.32, 348.54, 392.69, 359.78]},
        {"id": "e60", "page": 3, "type": "image", "text": "", "bbox": [138.72, 362.92, 402.0, 519.46]},
        {"id": "e61", "page": 3, "type": "image", "text": "", "bbox": [138.72, 519.46, 402.0, 676.0]},
        {"id": "e65", "page": 4, "type": "question_marker", "text": "例6", "bbox": [85.2, 100.85, 476.01, 112.33]},
    ]


def visual_payloads():
    return {
        "p3-img1": {
            "visual_ref": {
                "id": "p3-img1",
                "page": 3,
                "bbox": [132.72, 344.54, 408.0, 680.0],
                "same_visual_group_id": "vg_p3_1",
                "child_visual_ids": ["p3-img1", "p3-img2"],
                "absorbed_texts": [{"text": "2023 年全国规模以上文化及相关产业企业相关指标情况", "type": "caption"}],
            },
            "image": {
                "ref": "p3-img1",
                "page": 3,
                "bbox": [132.72, 344.54, 408.0, 680.0],
                "same_visual_group_id": "vg_p3_1",
                "child_visual_ids": ["p3-img1", "p3-img2"],
                "role": "question_material",
            },
        }
    }


class VisionAIEnhancementTest(unittest.TestCase):
    def test_should_call_vision_ai_for_visual_low_confidence_or_overlap_cases(self):
        self.assertTrue(
            should_call_vision_ai(
                page_blocks=page_elements(),
                parsed_questions=[{**q5_q6_questions()[0], "parse_confidence": 0.7}],
                visual_refs=[],
                confidence_threshold=0.75,
            )
        )
        self.assertTrue(
            should_call_vision_ai(
                page_blocks=page_elements(),
                parsed_questions=q5_q6_questions(),
                visual_refs=[visual_payloads()["p3-img1"]["visual_ref"]],
                confidence_threshold=0.75,
            )
        )
        self.assertFalse(
            should_call_vision_ai(
                page_blocks=[],
                parsed_questions=[{**q5_q6_questions()[0], "parse_confidence": 0.95, "needs_review": False}],
                visual_refs=[],
                confidence_threshold=0.75,
            )
        )

    def test_disabled_feature_leaves_questions_unchanged(self):
        questions = q5_q6_questions()
        original = deepcopy(questions)
        provider = FakeProvider(response=VisionAIResponse(page=3, corrections=[]))
        with patch.dict(os.environ, {"ENABLE_VISION_AI": "false"}, clear=False):
            result = enhance_questions_with_vision_ai(
                pdf_path="",
                output_dir="",
                questions=questions,
                page_elements=page_elements(),
                visual_payloads=visual_payloads(),
                provider=provider,
            )

        self.assertEqual(result.questions, original)
        self.assertEqual(provider.calls, [])
        self.assertEqual(result.stats["called_pages"], [])

    def test_missing_dashscope_key_skips_without_failing(self):
        questions = q5_q6_questions()
        with patch.dict(os.environ, {"ENABLE_VISION_AI": "true", "DASHSCOPE_API_KEY": ""}, clear=False):
            result = enhance_questions_with_vision_ai(
                pdf_path="",
                output_dir="",
                questions=questions,
                page_elements=page_elements(),
                visual_payloads=visual_payloads(),
            )

        self.assertEqual(result.questions, questions)
        self.assertIn("vision_ai_api_key_missing", result.stats["warnings"])

    def test_high_confidence_correction_updates_visual_refs(self):
        response = VisionAIResponse(
            page=3,
            corrections=[
                {
                    "question_id": "q6",
                    "action": "update_visual_refs",
                    "reason": "该表格标题和表格主体属于第6题前置资料",
                    "confidence": 0.92,
                    "updates": {
                        "visual_refs": ["p3-img1"],
                        "same_visual_group_id": "vg_p3_1",
                        "need_review": False,
                    },
                }
            ],
            warnings=[{"type": "uncertain_table_ownership", "message": "表格标题明显属于第6题"}],
        )
        provider = FakeProvider(response=response)
        with patch.dict(os.environ, {"ENABLE_VISION_AI": "true"}, clear=False), TemporaryDirectory() as tmpdir:
            result = enhance_questions_with_vision_ai(
                pdf_path="",
                output_dir=tmpdir,
                questions=q5_q6_questions(),
                page_elements=page_elements(),
                visual_payloads=visual_payloads(),
                provider=provider,
            )

        q5, q6 = result.questions
        self.assertEqual(q5["images"], [])
        self.assertEqual(q5["visual_refs"], [])
        self.assertEqual([item["id"] for item in q6["visual_refs"]], ["p3-img1"])
        self.assertEqual([item["ref"] for item in q6["images"]], ["p3-img1"])
        self.assertEqual(q6["image_refs"], ["p3-img1"])
        self.assertEqual(q6["ai_provider"], "qwen-vl")
        self.assertEqual(q6["ai_confidence"], 0.92)
        self.assertEqual(q6["ai_corrections"][0]["status"], "applied")
        self.assertFalse(q6["needs_review"])

    def test_medium_confidence_correction_is_suggestion_only(self):
        response = VisionAIResponse(
            page=3,
            corrections=[
                {
                    "question_id": "q6",
                    "action": "update_visual_refs",
                    "reason": "可能属于第6题",
                    "confidence": 0.74,
                    "updates": {"visual_refs": ["p3-img1"]},
                }
            ],
        )
        provider = FakeProvider(response=response)
        with patch.dict(os.environ, {"ENABLE_VISION_AI": "true"}, clear=False):
            result = enhance_questions_with_vision_ai(
                pdf_path="",
                output_dir="",
                questions=q5_q6_questions(),
                page_elements=page_elements(),
                visual_payloads=visual_payloads(),
                provider=provider,
            )

        q6 = result.questions[1]
        self.assertEqual(q6["visual_refs"], [])
        self.assertEqual(q6["images"], [])
        self.assertTrue(q6["needs_review"])
        self.assertIn("vision_ai_suggestion_pending", q6["parse_warnings"])
        self.assertEqual(q6["ai_corrections"][0]["status"], "suggested")

    def test_provider_failure_records_warning_without_failing_parse(self):
        provider = FakeProvider(error=ValueError("invalid json"))
        with patch.dict(os.environ, {"ENABLE_VISION_AI": "true"}, clear=False):
            result = enhance_questions_with_vision_ai(
                pdf_path="",
                output_dir="",
                questions=q5_q6_questions(),
                page_elements=page_elements(),
                visual_payloads=visual_payloads(),
                provider=provider,
            )

        self.assertEqual(result.questions[0]["images"], [])
        self.assertIn("vision_ai_failed", result.stats["warnings"])


if __name__ == "__main__":
    unittest.main()
