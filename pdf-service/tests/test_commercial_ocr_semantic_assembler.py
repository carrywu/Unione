import json
import unittest
from pathlib import Path

from commercial_ocr.semantic_assembler import assemble_semantic_result
from commercial_ocr.types import NormalizedOCRBlock, ProviderPageResult


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


class CommercialOCRSemanticAssemblerTest(unittest.TestCase):
    def test_shared_material_fixture_builds_one_group_and_four_child_questions(self):
        assembly = assemble_semantic_result([_load_shared_material_page()], provider_name="mock_commercial_ocr")

        self.assertEqual(len(assembly.material_groups), 1)
        material_group = assembly.material_groups[0]
        self.assertEqual(material_group.question_range, [17, 18, 19, 20])
        self.assertGreaterEqual(len(material_group.shared_assets), 2)

        by_no = {question.question_no: question for question in assembly.normalized_questions}
        self.assertEqual(sorted(by_no), [17, 18, 19, 20])
        self.assertEqual(len({by_no[number].material_id for number in (17, 18, 19, 20)}), 1)
        self.assertNotIn(material_group.shared_stem, by_no[17].local_stem)
        self.assertIn(material_group.shared_stem, by_no[17].full_stem)
        self.assertEqual(by_no[17].question_role, "child_question")
        self.assertEqual(by_no[20].question_role, "child_question")

    def test_ambiguous_material_intro_requires_human_review(self):
        page = _load_shared_material_page()
        page.blocks[2].text = "根据以下资料，回答下列问题"
        assembly = assemble_semantic_result([page], provider_name="mock_commercial_ocr")

        self.assertEqual(len(assembly.material_groups), 1)
        self.assertTrue(assembly.material_groups[0].needs_human_review)
        self.assertIn("material_group_range_uncertain", assembly.material_groups[0].warnings)

    def test_standalone_questions_remain_standalone(self):
        page = _load_shared_material_page()
        page.blocks = [block for block in page.blocks if block.block_type not in {"material_intro", "chart", "table", "header", "title"}]
        assembly = assemble_semantic_result([page], provider_name="mock_commercial_ocr")

        self.assertEqual(len(assembly.material_groups), 0)
        self.assertTrue(all(question.group_type == "standalone" for question in assembly.normalized_questions))

    def test_layout_only_blocks_do_not_produce_complete_questions(self):
        payload = json.loads((FIXTURE_ROOT / "tencent_question_split_layout_single_page_normalized.json").read_text(encoding="utf-8"))
        page_payload = payload["page_results"][0]
        page = ProviderPageResult(
            page_no=page_payload["page_no"],
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
        self.assertEqual(sorted(question.question_no for question in assembly.normalized_questions if question.question_no is not None), [17, 18])
        self.assertTrue(all(question.needs_human_review for question in assembly.normalized_questions))
        self.assertTrue(all("full_stem" in question.missing_fields for question in assembly.normalized_questions))


if __name__ == "__main__":
    unittest.main()
