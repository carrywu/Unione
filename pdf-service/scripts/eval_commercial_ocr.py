from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from commercial_ocr.fixtures import fixture_path, load_fixture
from commercial_ocr.quality_gate import evaluate_parse_quality
from commercial_ocr.semantic_assembler import assemble_semantic_result
from commercial_ocr.types import NormalizedOCRBlock, ProviderPageResult


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate commercial OCR fixtures without calling real APIs.")
    parser.add_argument("--provider", default="mock_commercial_ocr")
    parser.add_argument("--fixture", default="shared_material_17_20_blocks.json")
    args = parser.parse_args()

    page_results = load_page_results(args.fixture)
    assembly = assemble_semantic_result(page_results, provider_name=args.provider)
    gate = evaluate_parse_quality(assembly)
    output_root = Path(__file__).resolve().parents[1] / "debug" / "commercial-ocr-eval" / datetime.now().strftime("%Y%m%d-%H%M%S")
    output_root.mkdir(parents=True, exist_ok=True)
    evaluation = {
        "provider": args.provider,
        "latency": 0,
        "question_count": len(assembly.normalized_questions),
        "material_group_count": len(assembly.material_groups),
        "missing_fields_count": sum(len(question.missing_fields) for question in assembly.normalized_questions),
        "answer_null_count": sum(1 for question in assembly.normalized_questions if question.answer in {None, ""}),
        "analysis_unknown_count": sum(
            1 for question in assembly.normalized_questions if str(question.analysis or "").strip().lower() == "unknown"
        ),
        "grouping_accuracy_for_fixture": _grouping_accuracy(assembly),
        "quality_gate_summary": gate.to_dict(),
        "fallback_used": False,
        "errors": gate.blocking_reasons,
    }
    target = output_root / "evaluation.json"
    target.write_text(json.dumps(evaluation, ensure_ascii=False, indent=2), encoding="utf-8")
    print(target)
    return 0


def load_page_results(fixture_name: str) -> list[ProviderPageResult]:
    payload = load_fixture(fixture_name)
    if payload.get("page_results"):
        return [
            ProviderPageResult(
                page_no=int(page.get("page_no") or 0),
                blocks=[
                    NormalizedOCRBlock(
                        block_id=block["block_id"],
                        provider_ref=block["provider_ref"],
                        page_no=block["page_no"],
                        text=block.get("text") or "",
                        bbox=block.get("bbox") or [],
                        block_type=block.get("block_type") or "unknown",
                        confidence=block.get("confidence"),
                        reading_order=block.get("reading_order") or 0,
                        parent_block_id=block.get("parent_block_id"),
                        raw=block.get("raw") or {},
                        warnings=block.get("warnings") or [],
                    )
                    for block in page.get("blocks") or []
                ],
                figures=page.get("figures") or [],
                tables=page.get("tables") or [],
                raw=page.get("raw") or {},
                warnings=page.get("warnings") or [],
            )
            for page in payload["page_results"]
        ]
    if payload.get("blocks"):
        return [
            ProviderPageResult(
                page_no=1,
                blocks=[
                    NormalizedOCRBlock(
                        block_id=block["block_id"],
                        provider_ref=block["provider_ref"],
                        page_no=block["page_no"],
                        text=block.get("text") or "",
                        bbox=block.get("bbox") or [],
                        block_type=block.get("block_type") or "unknown",
                        confidence=block.get("confidence"),
                        reading_order=block.get("reading_order") or 0,
                        parent_block_id=block.get("parent_block_id"),
                        raw=block.get("raw") or {},
                        warnings=block.get("warnings") or [],
                    )
                    for block in payload["blocks"]
                ],
                raw={},
                warnings=[],
            )
        ]
    raise ValueError(f"fixture {fixture_name} does not expose page_results or blocks: {fixture_path(fixture_name)}")


def _grouping_accuracy(assembly) -> float:
    if not assembly.normalized_questions:
        return 0.0
    material_question_count = sum(1 for question in assembly.normalized_questions if question.material_id)
    return round(material_question_count / len(assembly.normalized_questions), 4)


if __name__ == "__main__":
    raise SystemExit(main())
