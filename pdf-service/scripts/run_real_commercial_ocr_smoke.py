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
from scripts.data_analysis_real_smoke_lib import ensure_dir, load_project_env, timestamp_slug, write_json
from scripts.run_real_data_analysis_batch_smoke import provider_page_summary, run_provider_on_page


def bool_arg(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def provider_env_status(provider_name: str) -> dict[str, Any]:
    if provider_name.startswith("baidu_"):
        return {
            "provider_enabled": True,
            "api_key_present": bool(str(os.getenv("BAIDU_API_KEY") or "").strip()),
            "secret_key_present": bool(str(os.getenv("BAIDU_SECRET_KEY") or "").strip()),
            "access_token_present": bool(str(os.getenv("BAIDU_ACCESS_TOKEN") or "").strip()),
            "endpoint_present": True,
        }
    if provider_name.startswith("tencent_"):
        return {
            "provider_enabled": True,
            "secret_id_present": bool(str(os.getenv("TENCENT_SECRET_ID") or "").strip()),
            "secret_key_present": bool(str(os.getenv("TENCENT_SECRET_KEY") or "").strip()),
            "region_present": True,
            "endpoint_present": True,
            "version_present": True,
            "real_smoke_enabled": bool_arg(os.getenv("TENCENT_OCR_REAL_SMOKE", "false")),
        }
    return {"provider_enabled": False}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one real commercial OCR provider on one PDF page.")
    parser.add_argument("--pdf", required=True, help="Path to the source PDF")
    parser.add_argument("--page", required=True, type=int, help="1-based page number")
    parser.add_argument("--provider", required=True, help="Provider id, for example baidu_paper_cut_edu")
    parser.add_argument("--real-smoke", default="false", help="Enable real smoke guard for providers that require it")
    parser.add_argument(
        "--out",
        default="",
        help="Optional summary JSON path. Default: debug/real-commercial-ocr-smoke/<timestamp>/<provider>-page-<n>-summary.json",
    )
    return parser


def run_single_page_smoke(
    *,
    pdf_path: str,
    provider_name: str,
    page_no: int,
    output_path: Path,
    real_smoke: bool,
) -> dict[str, Any]:
    if real_smoke and provider_name.startswith("tencent_"):
        os.environ["TENCENT_OCR_REAL_SMOKE"] = "true"

    extractor = PDFExtractor(pdf_path)
    try:
        provider_run = run_provider_on_page(
            extractor=extractor,
            provider_name=provider_name,
            page_no=page_no,
            output_dir=output_path.parent,
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
        summary["provider_config_status"] = provider_env_status(provider_name)
        summary["real_smoke_requested"] = real_smoke
        summary["pdf_ref"] = str(Path(pdf_path).name)
        write_json(output_path, summary)
        return summary
    finally:
        extractor.close()


def main(argv: list[str] | None = None) -> int:
    load_project_env()
    args = build_parser().parse_args(argv)
    pdf_path = str(Path(args.pdf).expanduser().resolve())
    page_no = max(1, int(args.page))
    provider_name = str(args.provider).strip()
    real_smoke = bool_arg(args.real_smoke)

    if args.out:
        output_path = Path(args.out).expanduser().resolve()
    else:
        output_dir = ensure_dir(ROOT.parent / "debug" / "real-commercial-ocr-smoke" / timestamp_slug())
        output_path = output_dir / f"{provider_name}-page-{page_no}-summary.json"
    ensure_dir(output_path.parent)

    run_single_page_smoke(
        pdf_path=pdf_path,
        provider_name=provider_name,
        page_no=page_no,
        output_path=output_path,
        real_smoke=real_smoke,
    )
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
