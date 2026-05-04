from __future__ import annotations

import json
from pathlib import Path
from unittest import TestCase

from commercial_ocr.quality_gate import evaluate_parse_quality
from commercial_ocr.semantic_assembler import assemble_semantic_result
from commercial_ocr.types import NormalizedOCRBlock, ProviderPageResult
from commercial_ocr.visual_understanding import build_visual_understanding_summary


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "commercial_ocr"


def _load_shared_material_page() -> ProviderPageResult:
    payload = json.loads(
        (FIXTURE_ROOT / "shared_material_17_20_blocks.json").read_text(encoding="utf-8")
    )
    return ProviderPageResult(
        page_no=1,
        blocks=[
            NormalizedOCRBlock(
                block_id=str(block["block_id"]),
                provider_ref=str(block["provider_ref"]),
                page_no=int(block["page_no"]),
                text=str(block.get("text") or ""),
                bbox=[float(item) for item in block.get("bbox") or []],
                block_type=str(block.get("block_type") or "unknown"),
                confidence=float(block["confidence"]) if block.get("confidence") is not None else None,
                reading_order=int(block.get("reading_order") or 0),
                parent_block_id=block.get("parent_block_id"),
                raw=dict(block.get("raw") or {}),
                warnings=[str(item) for item in block.get("warnings") or [] if str(item).strip()],
            )
            for block in payload.get("blocks") or []
        ],
    )


def _pure_text_page() -> ProviderPageResult:
    return ProviderPageResult(
        page_no=1,
        blocks=[
            NormalizedOCRBlock(
                block_id="q1-no",
                provider_ref="fixture:question:1",
                page_no=1,
                text="1",
                bbox=[40, 120, 70, 150],
                block_type="question_no",
                confidence=0.99,
                reading_order=1,
            ),
            NormalizedOCRBlock(
                block_id="q1-stem",
                provider_ref="fixture:question:1",
                page_no=1,
                text="1. 下列说法正确的是？",
                bbox=[90, 120, 620, 170],
                block_type="stem",
                confidence=0.98,
                reading_order=2,
            ),
            *[
                NormalizedOCRBlock(
                    block_id=f"q1-option-{label.lower()}",
                    provider_ref="fixture:question:1",
                    page_no=1,
                    text=f"{label}. 选项{label}",
                    bbox=[100 + offset * 120, 180, 200 + offset * 120, 220],
                    block_type="option",
                    confidence=0.98,
                    reading_order=3 + offset,
                    parent_block_id="q1-stem",
                )
                for offset, label in enumerate(["A", "B", "C", "D"])
            ],
            NormalizedOCRBlock(
                block_id="q1-answer",
                provider_ref="fixture:question:1",
                page_no=1,
                text="A",
                bbox=[90, 120, 620, 170],
                block_type="answer",
                confidence=0.97,
                reading_order=8,
                parent_block_id="q1-stem",
            ),
            NormalizedOCRBlock(
                block_id="q1-analysis",
                provider_ref="fixture:question:1",
                page_no=1,
                text="根据定义可知 A 正确。",
                bbox=[100, 240, 520, 280],
                block_type="analysis",
                confidence=0.96,
                reading_order=9,
                parent_block_id="q1-stem",
            ),
        ],
    )


class CommercialOCRVisualUnderstandingTest(TestCase):
    def test_shared_material_question_triggers_visual_understanding(self) -> None:
        assembly = assemble_semantic_result(
            [_load_shared_material_page()],
            provider_name="mock_commercial_ocr",
        )
        gate = evaluate_parse_quality(assembly)

        summary = build_visual_understanding_summary(
            assembly,
            quality_gate=gate,
            provider_name="mock_commercial_ocr",
            provider_trace_ref="/tmp/mock-trace.json",
            fallback_used=False,
        )

        self.assertTrue(summary["triggered"])
        self.assertIn("shared_material_detected", summary["trigger_reasons"])
        self.assertIn("data_analysis_question", summary["trigger_reasons"])
        self.assertTrue(summary["detected_diagram_elements"])

    def test_pure_text_high_confidence_question_skips_visual_understanding(self) -> None:
        assembly = assemble_semantic_result(
            [_pure_text_page()],
            provider_name="mock_commercial_ocr",
        )
        gate = evaluate_parse_quality(assembly)

        summary = build_visual_understanding_summary(
            assembly,
            quality_gate=gate,
            provider_name="mock_commercial_ocr",
            provider_trace_ref=None,
            fallback_used=False,
        )

        self.assertFalse(summary["triggered"])
        self.assertEqual(summary["visual_grouping_summary"], "high_confidence_text_only_skip")
        self.assertEqual(summary["trigger_reasons"], [])

    def test_missing_chart_title_emits_warning(self) -> None:
        assembly = assemble_semantic_result(
            [_load_shared_material_page()],
            provider_name="mock_commercial_ocr",
        )
        assembly.material_groups[0].shared_assets[0]["text"] = ""
        gate = evaluate_parse_quality(assembly)

        summary = build_visual_understanding_summary(
            assembly,
            quality_gate=gate,
            provider_name="mock_commercial_ocr",
            provider_trace_ref="/tmp/mock-trace.json",
            fallback_used=False,
        )

        self.assertTrue(summary["triggered"])
        self.assertIn("missing_chart_title", summary["warnings"])
