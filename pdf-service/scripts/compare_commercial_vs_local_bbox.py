from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.data_analysis_real_smoke_lib import ensure_dir, read_json, timestamp_slug, write_json


LOCAL_PROVIDERS = {"tesseract_local_ocr", "local_parser"}


def normalized_bbox(value: Any) -> list[float] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return None


def bbox_overlap(a: list[float] | None, b: list[float] | None) -> bool | None:
    if a is None or b is None:
        return None
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def extract_page_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload.get("page_summaries"), list):
        return [item for item in payload["page_summaries"] if isinstance(item, dict)]
    if isinstance(payload.get("page_provider_runs"), list):
        return [item for item in payload["page_provider_runs"] if isinstance(item, dict)]
    return []


def best_commercial_record(records: list[dict[str, Any]], page_no: int) -> dict[str, Any] | None:
    matches = [
        item
        for item in records
        if int(item.get("page_no") or 0) == page_no
        and str(item.get("provider") or "") not in LOCAL_PROVIDERS
    ]
    if not matches:
        return None
    ranked = sorted(
        matches,
        key=lambda item: (
            2 if str(item.get("status") or "") == "ok" else 1 if str(item.get("status") or "") == "partial" else 0,
            int(item.get("bbox_count") or 0),
            int(item.get("question_count") or 0),
        ),
        reverse=True,
    )
    return ranked[0]


def best_local_record(records: list[dict[str, Any]], page_no: int) -> dict[str, Any] | None:
    matches = [
        item
        for item in records
        if int(item.get("page_no") or 0) == page_no
        and str(item.get("provider") or "") in LOCAL_PROVIDERS
    ]
    if not matches:
        return None
    ranked = sorted(
        matches,
        key=lambda item: (
            int(item.get("bbox_count") or 0),
            int(item.get("question_count") or 0),
        ),
        reverse=True,
    )
    return ranked[0]


def question_overlap_ratio(commercial: dict[str, Any], local: dict[str, Any]) -> float | None:
    commercial_boxes = {
        int(item["question_no"]): normalized_bbox(item.get("bbox"))
        for item in commercial.get("question_bboxes") or []
        if item.get("question_no") is not None
    }
    local_boxes = {
        int(item["question_no"]): normalized_bbox(item.get("bbox"))
        for item in local.get("question_bboxes") or []
        if item.get("question_no") is not None
    }
    common = sorted(set(commercial_boxes) & set(local_boxes))
    if not common:
        return None
    hits = 0
    total = 0
    for question_no in common:
        overlap = bbox_overlap(commercial_boxes.get(question_no), local_boxes.get(question_no))
        if overlap is None:
            continue
        total += 1
        if overlap:
            hits += 1
    if total == 0:
        return None
    return round(hits / total, 3)


def material_overlap_ratio(commercial: dict[str, Any], local: dict[str, Any]) -> float | None:
    commercial_boxes = [normalized_bbox(item.get("bbox")) for item in commercial.get("material_bboxes") or []]
    local_boxes = [normalized_bbox(item.get("bbox")) for item in local.get("material_bboxes") or []]
    commercial_boxes = [item for item in commercial_boxes if item is not None]
    local_boxes = [item for item in local_boxes if item is not None]
    if not commercial_boxes or not local_boxes:
        return None
    hits = 0
    for commercial_box in commercial_boxes:
        if any(bbox_overlap(commercial_box, local_box) for local_box in local_boxes):
            hits += 1
    return round(hits / len(commercial_boxes), 3)


def compare_page_summaries(commercial: dict[str, Any] | None, local: dict[str, Any] | None, page_no: int) -> dict[str, Any]:
    warnings: list[str] = []
    commercial_question_numbers = set(int(item) for item in commercial.get("question_numbers") or []) if commercial else set()
    local_question_numbers = set(int(item) for item in local.get("question_numbers") or []) if local else set()
    material_bbox_overlap = material_overlap_ratio(commercial or {}, local or {}) if commercial and local else None
    question_bbox_overlap = question_overlap_ratio(commercial or {}, local or {}) if commercial and local else None

    if commercial and material_bbox_overlap is None:
        warnings.append("commercial_material_bbox_overlap_unavailable")
    if local and material_bbox_overlap is None:
        warnings.append("local_material_bbox_overlap_unavailable")
    if commercial and question_bbox_overlap is None:
        warnings.append("question_bbox_overlap_unavailable")

    commercial_status = str((commercial or {}).get("status") or "")
    recommended_source = "commercial" if commercial_status in {"ok", "partial"} and int((commercial or {}).get("bbox_count") or 0) > 0 else "local"
    if local is None and commercial is None:
        recommended_source = "none"
    elif local is None:
        recommended_source = "commercial"

    return {
        "page_no": page_no,
        "commercial_provider": (commercial or {}).get("provider"),
        "commercial_status": commercial_status or None,
        "commercial_bbox_count": int((commercial or {}).get("bbox_count") or 0),
        "local_provider": (local or {}).get("provider"),
        "local_bbox_count": int((local or {}).get("bbox_count") or 0),
        "material_bbox_overlap": material_bbox_overlap,
        "question_bbox_overlap": question_bbox_overlap,
        "commercial_missing": sorted(local_question_numbers - commercial_question_numbers),
        "local_missing": sorted(commercial_question_numbers - local_question_numbers),
        "recommended_source": recommended_source,
        "warnings": sorted(set(warnings)),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare commercial OCR bbox summaries against local fallback summaries.")
    parser.add_argument("commercial_summary_json", help="Path to commercial batch summary JSON")
    parser.add_argument(
        "local_summary_json",
        nargs="?",
        default="",
        help="Optional local batch summary JSON. If omitted, local provider rows are searched in the commercial summary.",
    )
    parser.add_argument(
        "--out",
        default="",
        help="Optional comparison JSON path. Default: debug/real-commercial-ocr-smoke/<timestamp>/bbox-comparison.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    commercial_path = Path(args.commercial_summary_json).expanduser().resolve()
    local_path = Path(args.local_summary_json).expanduser().resolve() if args.local_summary_json else commercial_path
    commercial_payload = read_json(commercial_path)
    local_payload = read_json(local_path)
    commercial_records = extract_page_records(commercial_payload)
    local_records = extract_page_records(local_payload)
    page_numbers = sorted(
        {
            int(item.get("page_no") or 0)
            for item in [*commercial_records, *local_records]
            if int(item.get("page_no") or 0) > 0
        }
    )

    comparisons = [
        compare_page_summaries(
            best_commercial_record(commercial_records, page_no),
            best_local_record(local_records, page_no),
            page_no,
        )
        for page_no in page_numbers
    ]
    payload = {
        "generated_at": timestamp_slug(),
        "commercial_summary_ref": str(commercial_path),
        "local_summary_ref": str(local_path),
        "pages": comparisons,
    }

    if args.out:
        output_path = Path(args.out).expanduser().resolve()
    else:
        output_dir = ensure_dir(ROOT.parent / "debug" / "real-commercial-ocr-smoke" / timestamp_slug())
        output_path = output_dir / "bbox-comparison.json"
    ensure_dir(output_path.parent)
    write_json(output_path, payload)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
