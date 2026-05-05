from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from commercial_ocr.adapters import provider_registry
from commercial_ocr.types import ProviderOCRRequest
from extractor import PDFExtractor
from scripts.data_analysis_local_ocr import (
    LOCAL_OCR_PROVIDER,
    extract_question_range,
    has_material_range_signal,
    local_ocr_page_text,
)
from scripts.data_analysis_real_smoke_lib import (
    ensure_dir,
    keyword_lines,
    load_project_env,
    parse_page_spec,
    project_relative_path,
    timestamp_slug,
    write_json,
)


KEYWORDS = [
    "根据以下资料",
    "根据所给资料",
    "根据所给材料",
    "请回答",
    "回答16-20题",
    "回答17-20题",
    "表",
    "图",
    "同比",
    "环比",
    "增长率",
    "比重",
    "百分点",
    "倍数",
]
STRONG_SIGNALS = ["根据以下资料", "根据所给资料", "回答16-20题", "回答17-20题", "【例", "（202"]


def normalize_text(text: str) -> str:
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def score_text(text: str) -> int:
    head = text[:240]
    if "目 录" in head:
        return 0
    if "专项" in head and not any(signal in head for signal in ("【例", "根据以下资料", "根据所给资料")):
        return 0
    score = 0
    for keyword in KEYWORDS:
        if keyword in text:
            score += 2 if keyword.startswith("根据") or keyword.startswith("回答") else 1
    if any(signal in text for signal in STRONG_SIGNALS):
        score += 2
    if extract_question_range(text):
        score += 3
    if has_material_range_signal(text):
        score += 4
    return score


def ocr_page_text(
    *,
    extractor: PDFExtractor,
    page_no: int,
    provider_name: str,
    debug_dir: Path,
) -> tuple[str, list[str], str]:
    providers = provider_registry()
    provider = providers.get(provider_name)
    if provider is None:
        return "", [f"unknown_provider:{provider_name}"], "skipped"
    available, missing = provider.is_available()
    if not available:
        return "", list(missing), "skipped_unavailable"
    request = ProviderOCRRequest(
        extractor=extractor,
        pdf_path=extractor.pdf_path,
        source_document_id=f"discover-{Path(extractor.pdf_path).stem}",
        task_id=f"discover-p{page_no}",
        page_numbers=[page_no],
        debug_dir=str(debug_dir),
        trace_enabled=True,
    )
    result = provider.analyze_document(request)
    blocks = []
    for page in result.page_results:
        for block in page.blocks:
            if block.text.strip():
                blocks.append(block.text.strip())
    return "\n".join(blocks), list(result.warnings), result.provider_status


def discover_candidates(
    *,
    pdf_path: str,
    page_spec: str | None,
    ocr_provider: str | None,
    max_pages: int,
    output_dir: Path,
) -> dict[str, Any]:
    extractor = PDFExtractor(pdf_path)
    try:
        page_numbers = parse_page_spec(page_spec, total_pages=extractor.total_pages)
        candidates: list[dict[str, Any]] = []
        for page_no in page_numbers:
            page_text = normalize_text(extractor.get_page_text(page_no - 1))
            provider = "text_layer"
            status = "matched_text_layer"
            warnings: list[str] = []
            score = score_text(page_text)
            if score == 0 and ocr_provider:
                ocr_text, ocr_warnings, ocr_status = ocr_page_text(
                    extractor=extractor,
                    page_no=page_no,
                    provider_name=ocr_provider,
                    debug_dir=output_dir,
                )
                if ocr_text.strip():
                    page_text = normalize_text(ocr_text)
                    provider = ocr_provider
                    status = ocr_status if score_text(page_text) == 0 else "matched_ocr"
                    warnings.extend(ocr_warnings)
                    score = score_text(page_text)
                else:
                    provider = ocr_provider
                    status = ocr_status
                    warnings.extend(ocr_warnings)
            if score == 0:
                try:
                    local_text = local_ocr_page_text(extractor=extractor, page_no=page_no)
                except Exception as exc:  # pragma: no cover - runtime integration path
                    warnings.append(f"local_ocr_failed:{exc}")
                else:
                    local_score = score_text(local_text)
                    if local_score > 0:
                        page_text = normalize_text(local_text)
                        provider = LOCAL_OCR_PROVIDER
                        status = "matched_local_ocr"
                        score = local_score
            if score <= 0:
                continue
            evidence = keyword_lines(page_text, KEYWORDS, limit=3)
            if not evidence and page_text:
                evidence = [page_text[:140]]
            candidates.append(
                {
                    "pdf_ref": project_relative_path(pdf_path),
                    "page_no": page_no,
                    "evidence_text": "\n".join(evidence)[:400],
                    "likely_question_range": extract_question_range(page_text),
                    "provider": provider,
                    "status": status,
                    "warnings": warnings,
                    "score": score,
                }
            )
        candidates.sort(key=lambda item: (-int(item.get("score") or 0), int(item.get("page_no") or 0)))
        limited = candidates[:max_pages]
        return {
            "generated_at": timestamp_slug(),
            "pdf_ref": project_relative_path(pdf_path),
            "page_range": page_numbers,
            "ocr_provider": ocr_provider,
            "scanned_pages": len(page_numbers),
            "candidate_count": len(limited),
            "candidates": limited,
        }
    finally:
        extractor.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Discover likely data-analysis pages from a real PDF.")
    parser.add_argument("pdf_path", help="Path to the source PDF")
    parser.add_argument("--pages", default="all", help="1-based page selection like 1-20,25")
    parser.add_argument("--ocr-provider", default="", help="Optional OCR provider fallback for text-poor pages")
    parser.add_argument("--max-pages", type=int, default=6, help="Maximum number of candidate pages to emit")
    parser.add_argument(
        "--output-dir",
        default=str(ROOT.parent / "debug" / "real-data-data-analysis" / timestamp_slug()),
        help="Directory used for candidate-pages.json and provider traces",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    load_project_env()
    args = build_parser().parse_args(argv)
    output_dir = ensure_dir(Path(args.output_dir).expanduser().resolve())
    result = discover_candidates(
        pdf_path=str(Path(args.pdf_path).expanduser().resolve()),
        page_spec=args.pages,
        ocr_provider=str(args.ocr_provider or "").strip() or None,
        max_pages=max(1, int(args.max_pages)),
        output_dir=output_dir,
    )
    target = output_dir / "candidate-pages.json"
    write_json(target, result)
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
