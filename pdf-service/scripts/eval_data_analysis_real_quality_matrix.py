from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.data_analysis_real_smoke_lib import ensure_dir, read_json, timestamp_slug, write_json


def build_quality_matrix(
    batch_summary: dict[str, Any],
    visual_summary: dict[str, Any],
    llm_summary: dict[str, Any],
) -> dict[str, Any]:
    visual_groups = list(visual_summary.get("group_summaries") or [])
    questions = list(llm_summary.get("questions") or [])
    group_gate_map = {
        item.get("group_key"): item.get("data_analysis_quality_gate") or {}
        for item in batch_summary.get("group_summaries") or []
    }
    provider_timeout_count = sum(
        1
        for group in visual_groups
        for attempt in group.get("provider_attempts") or []
        if str(attempt.get("error_type") or "").lower() in {"timeout", "soft_timeout", "readtimeout"}
    )
    provider_hedge_success_count = sum(
        1
        for group in visual_groups
        if group.get("selected_provider") == "volcengine_ark_vl"
        and any(
            attempt.get("provider") == "qwen_vl" and attempt.get("status") != "ok"
            for attempt in group.get("provider_attempts") or []
        )
    )
    local_parser_fallback_count = sum(
        1 for group in visual_groups if str(group.get("ocr_provider") or "") == "local_parser"
    )
    bbox_provider_count = sum(
        1 for group in visual_groups if str(group.get("ocr_provider") or "") not in {"", "local_parser"}
    )
    questions_by_group: dict[str, list[dict[str, Any]]] = {}
    for question in questions:
        questions_by_group.setdefault(str(question.get("material_group_id") or ""), []).append(question)

    question_rows = []
    for question in questions:
        gate = group_gate_map.get(str(question.get("material_group_id") or ""), {})
        review_ready = bool(gate.get("review_ready"))
        needs_human_review = bool(gate.get("needs_human_review", True) or question.get("needs_human_review"))
        question_rows.append(
            {
                "question_no": question.get("question_no"),
                "material_group_id": question.get("material_group_id"),
                "review_ready": review_ready,
                "needs_human_review": needs_human_review,
                "blocking_reasons": gate.get("blocking_reasons") or [],
                "warnings": list(dict.fromkeys([*(gate.get("warnings") or []), *(question.get("warnings") or [])])),
                "confidence": question.get("comprehension_confidence", 0.0),
                "decision_reason": "review_ready" if review_ready and not needs_human_review else "needs_human_review",
            }
        )

    total_groups = len(visual_groups)
    return {
        "generated_at": timestamp_slug(),
        "pdf_ref": batch_summary.get("pdf_ref"),
        "material_groups_total": total_groups,
        "groups_complete": sum(1 for group in visual_groups if group.get("source_material_complete")),
        "groups_incomplete": sum(1 for group in visual_groups if not group.get("source_material_complete")),
        "questions_total": len(questions),
        "can_solve_count": sum(1 for question in questions if question.get("can_solve_question")),
        "refuse_count": sum(1 for question in questions if not question.get("can_solve_question")),
        "answer_conflict_count": sum(1 for question in questions if question.get("conflict_with_ocr_answer")),
        "high_confidence_count": sum(1 for question in questions if float(question.get("comprehension_confidence") or 0.0) >= 0.9),
        "needs_human_review_count": sum(1 for question in question_rows if question.get("needs_human_review")),
        "blocked_count": sum(1 for question in question_rows if not question.get("review_ready")),
        "provider_timeout_count": provider_timeout_count,
        "provider_hedge_success_count": provider_hedge_success_count,
        "bbox_from_ocr_provider_rate": round(bbox_provider_count / total_groups, 4) if total_groups else 0.0,
        "local_parser_fallback_count": local_parser_fallback_count,
        "questions": question_rows,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate the real data-analysis quality matrix.")
    parser.add_argument("batch_ocr_summary_json", help="Path to batch-ocr-summary.json")
    parser.add_argument("batch_visual_context_summary_json", help="Path to batch-visual-context-summary.json")
    parser.add_argument("batch_llm_understanding_summary_json", help="Path to batch-llm-understanding-summary.json")
    parser.add_argument(
        "--output-dir",
        default="",
        help="Optional output directory; defaults to the batch summary directory",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    batch_summary_path = Path(args.batch_ocr_summary_json).expanduser().resolve()
    batch_summary = read_json(batch_summary_path)
    visual_summary = read_json(Path(args.batch_visual_context_summary_json).expanduser().resolve())
    llm_summary = read_json(Path(args.batch_llm_understanding_summary_json).expanduser().resolve())
    output_dir = ensure_dir(Path(args.output_dir).expanduser().resolve()) if args.output_dir else batch_summary_path.parent
    target = output_dir / "quality-matrix.json"
    write_json(target, build_quality_matrix(batch_summary, visual_summary, llm_summary))
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
