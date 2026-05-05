from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.data_analysis_real_smoke_lib import ensure_dir, read_json, timestamp_slug, write_json


def build_visual_summary(batch_summary: dict[str, Any]) -> dict[str, Any]:
    groups = []
    qwen_timeout_count = 0
    ark_hedge_success_count = 0
    mimo_skipped_count = 0
    for item in batch_summary.get("group_summaries") or []:
        visual_meta = item.get("visual_meta") or {}
        attempts = list(visual_meta.get("attempts") or [])
        qwen_timeout_count += sum(
            1
            for attempt in attempts
            if attempt.get("provider") == "qwen_vl"
            and str(attempt.get("error_type") or "").lower() in {"timeout", "soft_timeout", "readtimeout"}
        )
        if visual_meta.get("selected_provider") == "volcengine_ark_vl" and any(
            attempt.get("provider") == "qwen_vl" and attempt.get("status") != "ok"
            for attempt in attempts
        ):
            ark_hedge_success_count += 1
        mimo_skipped_count += sum(
            1
            for attempt in attempts
            if attempt.get("provider") == "mimo_vl" and attempt.get("status") == "skipped"
        )
        groups.append(
            {
                "group_key": item.get("group_key"),
                "page_no": item.get("page_no"),
                "ocr_provider": item.get("ocr_provider"),
                "question_range": item.get("question_range") or [],
                "provider_attempts": attempts,
                "selected_provider": visual_meta.get("selected_provider"),
                "selected_model": visual_meta.get("selected_model"),
                **(item.get("visual_context") or {}),
                "needs_human_review": bool(
                    (item.get("data_analysis_quality_gate") or {}).get("needs_human_review")
                    or not (item.get("visual_context") or {}).get("source_material_complete", False)
                ),
                "warnings": list(dict.fromkeys([
                    *list((item.get("visual_context") or {}).get("warnings") or []),
                    *list((item.get("data_analysis_quality_gate") or {}).get("warnings") or []),
                ])),
            }
        )
    return {
        "generated_at": batch_summary.get("generated_at") or timestamp_slug(),
        "pdf_ref": batch_summary.get("pdf_ref"),
        "provider_strategy": batch_summary.get("provider_strategy") or {},
        "qwen_timeout_count": qwen_timeout_count,
        "ark_hedge_success_count": ark_hedge_success_count,
        "mimo_skipped_count": mimo_skipped_count,
        "group_summaries": groups,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract visual-context summary from batch OCR smoke output.")
    parser.add_argument("batch_ocr_summary_json", help="Path to batch-ocr-summary.json")
    parser.add_argument(
        "--output-dir",
        default="",
        help="Optional output directory; defaults to the batch summary directory",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary_path = Path(args.batch_ocr_summary_json).expanduser().resolve()
    batch_summary = read_json(summary_path)
    output_dir = ensure_dir(Path(args.output_dir).expanduser().resolve()) if args.output_dir else summary_path.parent
    target = output_dir / "batch-visual-context-summary.json"
    write_json(target, build_visual_summary(batch_summary))
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
