from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from extractor import PDFExtractor
from scripts.data_analysis_real_smoke_lib import (
    ensure_dir,
    load_project_env,
    parse_page_spec,
    timestamp_slug,
    write_json,
)
from scripts.run_real_data_analysis_batch_smoke import provider_page_summary, run_provider_on_page


def bool_arg(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one real commercial OCR provider on multiple PDF pages.")
    parser.add_argument("--pdf", required=True, help="Path to the source PDF")
    parser.add_argument("--pages", required=True, help="Page spec, for example 1,6,16")
    parser.add_argument("--provider", required=True, help="Provider id")
    parser.add_argument("--max-pages", type=int, default=3, help="Maximum number of pages to execute")
    parser.add_argument("--real-smoke", default="false", help="Enable real smoke guard for providers that require it")
    parser.add_argument(
        "--out",
        default="",
        help="Optional batch summary JSON path. Default: debug/real-commercial-ocr-smoke/<timestamp>/batch-commercial-ocr-summary.json",
    )
    return parser


def build_page_summary(
    *,
    extractor: PDFExtractor,
    provider_name: str,
    page_no: int,
    output_dir: Path,
) -> dict[str, Any]:
    provider_run = run_provider_on_page(
        extractor=extractor,
        provider_name=provider_name,
        page_no=page_no,
        output_dir=output_dir,
    )
    summary = provider_page_summary(
        candidate={"page_no": page_no},
        provider_name=provider_run["provider_name"],
        provider_status=provider_run["provider_status"],
        provider_latency_ms=int(getattr(provider_run["provider_result"], "provider_latency_ms", 0) or 0),
        assembly=provider_run["assembly"],
        result=provider_run["provider_result"],
        warnings=list(provider_run["warnings"]),
    )
    return {
        "provider": summary["provider"],
        "page_no": summary["page_no"],
        "status": summary["status"],
        "skipped_reason": summary.get("skipped_reason"),
        "bbox_count": summary["bbox_count"],
        "question_count": summary["question_count"],
        "question_numbers": summary.get("question_numbers") or [],
        "question_bboxes": summary.get("question_bboxes") or [],
        "material_bboxes": summary.get("material_bboxes") or [],
        "material_group_candidates": summary["material_group_candidates"],
        "shared_material_detected": summary.get("shared_material_detected", False),
        "question_range": summary.get("question_range") or [],
        "has_table_or_chart": summary["has_table_or_chart"],
        "has_answer_candidate": summary["has_answer_candidate"],
        "has_analysis_candidate": summary["has_analysis_candidate"],
        "layout_only": summary.get("layout_only", False),
        "fallback_used": summary.get("fallback_used", False),
        "errors": summary.get("errors") or [],
        "warnings": summary.get("warnings") or [],
        "raw_ref_redacted": summary.get("raw_ref_redacted"),
        "latency_ms": summary["latency_ms"],
    }


def run_batch(
    *,
    pdf_path: str,
    provider_name: str,
    pages: list[int],
    output_dir: Path,
    real_smoke: bool,
) -> dict[str, Any]:
    if real_smoke and provider_name.startswith("tencent_"):
        os.environ["TENCENT_OCR_REAL_SMOKE"] = "true"

    extractor = PDFExtractor(pdf_path)
    try:
        page_summaries = [
            build_page_summary(
                extractor=extractor,
                provider_name=provider_name,
                page_no=page_no,
                output_dir=output_dir,
            )
            for page_no in pages
        ]
    finally:
        extractor.close()

    successful_pages = [item for item in page_summaries if item["status"] == "ok"]
    partial_pages = [item for item in page_summaries if item["status"] == "partial"]
    blocked_pages = [
        item for item in page_summaries if item["status"] not in {"ok", "partial"}
    ]
    return {
        "generated_at": timestamp_slug(),
        "pdf_ref": str(Path(pdf_path).name),
        "provider": provider_name,
        "requested_pages": pages,
        "real_smoke_requested": real_smoke,
        "commercial_success_page_count": len(successful_pages),
        "commercial_partial_page_count": len(partial_pages),
        "blocked_page_count": len(blocked_pages),
        "blocked": len(successful_pages) == 0,
        "page_summaries": page_summaries,
    }


def main(argv: list[str] | None = None) -> int:
    load_project_env()
    args = build_parser().parse_args(argv)
    pdf_path = str(Path(args.pdf).expanduser().resolve())
    provider_name = str(args.provider).strip()
    real_smoke = bool_arg(args.real_smoke)
    temp_extractor = PDFExtractor(pdf_path)
    try:
        pages = parse_page_spec(args.pages, total_pages=temp_extractor.total_pages)
    finally:
        temp_extractor.close()
    pages = pages[: max(1, int(args.max_pages))]
    if args.out:
        output_path = Path(args.out).expanduser().resolve()
    else:
        output_dir = ensure_dir(ROOT.parent / "debug" / "real-commercial-ocr-smoke" / timestamp_slug())
        output_path = output_dir / "batch-commercial-ocr-summary.json"
    ensure_dir(output_path.parent)

    summary = run_batch(
        pdf_path=pdf_path,
        provider_name=provider_name,
        pages=pages,
        output_dir=output_path.parent,
        real_smoke=real_smoke,
    )
    write_json(output_path, summary)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
