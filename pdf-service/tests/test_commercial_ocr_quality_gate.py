import json
import unittest
from pathlib import Path

from commercial_ocr.quality_gate import evaluate_parse_quality
from commercial_ocr.semantic_assembler import assemble_semantic_result
from commercial_ocr.types import MaterialGroup, NormalizedOCRBlock, NormalizedQuestion, ProviderPageResult, SemanticAssemblyResult


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "commercial_ocr"


def _load_shared_material_page() -> ProviderPageResult:
    payload = json.loads((FIXTURE_ROOT / "shared_material_17_20_blocks.json").read_text(encoding="utf-8"))
    blocks = [
        NormalizedOCRBlock(
            block_id=item["block_id"],
            provider_ref=item["provider_ref"],
            page_no=item["page_no"],
            text=item["text"],
            bbox=item["bbox"],
            block_type=item["block_type"],
            confidence=item.get("confidence"),
            reading_order=item["reading_order"],
            parent_block_id=item.get("parent_block_id"),
            raw=item.get("raw") or {},
            warnings=item.get("warnings") or [],
        )
        for item in payload["blocks"]
    ]
    return ProviderPageResult(page_no=1, blocks=blocks, raw={}, warnings=[])


class CommercialOCRQualityGateTest(unittest.TestCase):
    def test_incomplete_answer_and_unknown_analysis_mark_parse_incomplete(self):
        payload = json.loads((FIXTURE_ROOT / "incomplete_answer_analysis_blocks.json").read_text(encoding="utf-8"))
        questions = [NormalizedQuestion(**item) for item in payload["normalized_questions"]]
        gate = evaluate_parse_quality(SemanticAssemblyResult(normalized_questions=questions))

        self.assertTrue(gate.extracted_but_incomplete)
        self.assertFalse(gate.review_ready)
        self.assertIn("answer_missing", gate.blocking_reasons)
        self.assertIn("analysis_unknown", gate.blocking_reasons)

    def test_shared_material_group_can_be_semantically_consistent(self):
        page = _load_shared_material_page()
        for block in page.blocks:
            if block.block_id == "fixture-q19-analysis":
                block.text = "同比增速最高的是丁市。"
            if block.block_id == "fixture-q20-option-a":
                continue
        page.blocks.extend(
            [
                NormalizedOCRBlock(
                    block_id="fixture-q20-answer",
                    provider_ref="fixture:question:20",
                    page_no=1,
                    text="C",
                    bbox=[110, 910, 1110, 970],
                    block_type="answer",
                    confidence=0.94,
                    reading_order=25,
                    parent_block_id="fixture-q20-stem",
                    raw={},
                    warnings=[]
                ),
                NormalizedOCRBlock(
                    block_id="fixture-q20-analysis",
                    provider_ref="fixture:question:20",
                    page_no=1,
                    text="乙市位列第三。",
                    bbox=[130, 1015, 700, 1060],
                    block_type="analysis",
                    confidence=0.91,
                    reading_order=26,
                    parent_block_id="fixture-q20-stem",
                    raw={},
                    warnings=[]
                )
            ]
        )
        assembly = assemble_semantic_result([page], provider_name="mock_commercial_ocr")
        gate = evaluate_parse_quality(assembly)

        self.assertTrue(gate.semantic_consistent)
        self.assertTrue(gate.review_ready)

    def test_missing_shared_assets_fails_visual_asset_check(self):
        page = _load_shared_material_page()
        page.blocks = [block for block in page.blocks if block.block_type not in {"chart", "table"}]
        assembly = assemble_semantic_result([page], provider_name="mock_commercial_ocr")
        gate = evaluate_parse_quality(assembly)

        self.assertFalse(gate.visual_assets_preserved)
        self.assertIn("visual_assets_not_preserved", gate.blocking_reasons)

    def test_provider_fallback_requires_human_review(self):
        question = NormalizedQuestion(
            question_id="q-1",
            question_no=1,
            group_type="standalone",
            question_role="standalone_question",
            question_range=[1],
            local_stem="1. 第一题",
            full_stem="1. 第一题",
            options={"A": "甲", "B": "乙"},
            answer="A",
            analysis="解析",
            category="未知",
            source_page_span=[1, 1],
            bbox=[50, 80, 900, 150],
            question_image_ref=None,
            provider="mock_commercial_ocr",
            confidence=0.95,
            needs_human_review=False,
            missing_fields=[],
            validation_warnings=[],
            grouping_evidence=["standalone_question"],
            grouping_confidence=0.9
        )
        gate = evaluate_parse_quality(SemanticAssemblyResult(normalized_questions=[question]), fallback_used=True)

        self.assertTrue(gate.needs_human_review)
        self.assertIn("provider_fallback_used", gate.warnings)

    def test_layout_only_result_is_not_review_ready(self):
        payload = json.loads((FIXTURE_ROOT / "tencent_question_split_layout_single_page_normalized.json").read_text(encoding="utf-8"))
        page_payload = payload["page_results"][0]
        page = ProviderPageResult(
            page_no=1,
            blocks=[
                NormalizedOCRBlock(
                    block_id=item["block_id"],
                    provider_ref=item["provider_ref"],
                    page_no=item["page_no"],
                    text=item["text"],
                    bbox=item["bbox"],
                    block_type=item["block_type"],
                    confidence=item.get("confidence"),
                    reading_order=item["reading_order"],
                    parent_block_id=item.get("parent_block_id"),
                    raw=item.get("raw") or {},
                    warnings=item.get("warnings") or [],
                )
                for item in page_payload["blocks"]
            ],
            raw=page_payload.get("raw") or {},
            warnings=page_payload.get("warnings") or [],
        )
        assembly = assemble_semantic_result([page], provider_name="mock_tencent_question_split_layout")
        gate = evaluate_parse_quality(assembly)

        self.assertFalse(gate.review_ready)
        self.assertTrue(gate.needs_human_review)
        self.assertIn("semantic_grouping_inconsistent", gate.blocking_reasons)

    def test_complete_standalone_questions_can_be_review_ready(self):
        questions = [
            NormalizedQuestion(
                question_id="q-1",
                question_no=1,
                group_type="standalone",
                question_role="standalone_question",
                question_range=[1],
                local_stem="1. 第一题",
                full_stem="1. 第一题",
                options={"A": "甲", "B": "乙"},
                answer="A",
                analysis="解析1",
                category="未知",
                source_page_span=[1, 1],
                bbox=[50, 80, 900, 150],
                question_image_ref=None,
                provider="mock_commercial_ocr",
                confidence=0.95,
                needs_human_review=False,
                missing_fields=[],
                validation_warnings=[],
                grouping_evidence=["standalone_question"],
                grouping_confidence=0.9
            ),
            NormalizedQuestion(
                question_id="q-2",
                question_no=2,
                group_type="standalone",
                question_role="standalone_question",
                question_range=[2],
                local_stem="2. 第二题",
                full_stem="2. 第二题",
                options={"A": "甲", "B": "乙"},
                answer="B",
                analysis="解析2",
                category="未知",
                source_page_span=[1, 1],
                bbox=[50, 170, 900, 240],
                question_image_ref=None,
                provider="mock_commercial_ocr",
                confidence=0.95,
                needs_human_review=False,
                missing_fields=[],
                validation_warnings=[],
                grouping_evidence=["standalone_question"],
                grouping_confidence=0.9
            )
        ]
        gate = evaluate_parse_quality(SemanticAssemblyResult(normalized_questions=questions))

        self.assertTrue(gate.review_ready)
        self.assertTrue(gate.extraction_complete)
        self.assertTrue(gate.ocr_complete)


if __name__ == "__main__":
    unittest.main()
