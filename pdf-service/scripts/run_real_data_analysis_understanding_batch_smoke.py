from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.data_analysis_real_smoke_lib import ensure_dir, read_json, timestamp_slug, write_json


def build_understanding_summary(batch_summary: dict[str, Any]) -> dict[str, Any]:
    questions = []
    for item in batch_summary.get("group_summaries") or []:
        for result in item.get("text_results") or []:
            questions.append(
                {
                    "question_no": result.get("question_no"),
                    "material_group_id": item.get("group_key"),
                    "page_no": item.get("page_no"),
                    "ocr_provider": item.get("ocr_provider"),
                    "visual_provider": (item.get("visual_meta") or {}).get("selected_provider"),
                    **result,
                }
            )
    return {
        "generated_at": batch_summary.get("generated_at") or timestamp_slug(),
        "pdf_ref": batch_summary.get("pdf_ref"),
        "questions_total": len(questions),
        "questions": questions,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract text-understanding summary from batch OCR smoke output.")
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
    target = output_dir / "batch-llm-understanding-summary.json"
    write_json(target, build_understanding_summary(batch_summary))
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
