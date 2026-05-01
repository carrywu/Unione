from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

import fitz

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from debug_tools.draw_overlay import draw_overlays
from debug_tools.visual_assertions import run_visual_assertions
from strategies.markdown_question_strategy import MarkdownQuestionStrategy


def main() -> int:
    parser = argparse.ArgumentParser(description="Export visual debug overlays for PDF review regressions.")
    parser.add_argument("--case", required=True, help="Path to debug case YAML.")
    parser.add_argument("--out", required=True, help="Output directory for layout, overlays, and report.")
    args = parser.parse_args()

    case_path = Path(args.case)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    case = load_case(case_path)
    pdf_path = resolve_pdf_path(case_path, str(case["pdf"]))
    working_pdf = prepare_case_pdf(pdf_path=pdf_path, pages=case.get("pages") or [], out_dir=out_dir)
    parsed = MarkdownQuestionStrategy().parse(str(working_pdf), output_dir=str(out_dir))
    layout = build_layout(case=case, parsed=parsed, output_dir=out_dir, source_pdf=pdf_path, working_pdf=working_pdf)
    assertions = run_visual_assertions(layout, case)
    layout["assertions"] = assertions
    (out_dir / "layout.json").write_text(json.dumps(layout, ensure_ascii=False, indent=2), encoding="utf-8")
    overlay_files = draw_overlays(pdf_path=working_pdf, layout=layout, assertions=assertions, out_dir=out_dir)
    report = render_report(case=case, layout=layout, assertions=assertions, overlay_files=overlay_files)
    (out_dir / "VISUAL_DEBUG_REPORT.md").write_text(report, encoding="utf-8")
    print(f"Visual debug {'PASS' if assertions['passed'] else 'FAIL'}: {assertions['failed_count']} failed assertions")
    print(f"Artifacts: {out_dir}")
    return 0 if assertions["passed"] else 1


def load_case(case_path: Path) -> dict[str, Any]:
    case: dict[str, Any] = {"questions": {}}
    section: str | None = None
    current_question: str | None = None
    for raw_line in case_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if indent == 0:
            key, value = _split_key_value(stripped)
            if value is None:
                section = key
                current_question = None
                if section == "questions":
                    case.setdefault("questions", {})
                continue
            case[key] = _parse_scalar(value)
            section = None
            current_question = None
            continue
        if section == "questions" and indent == 2 and stripped.endswith(":"):
            current_question = stripped[:-1]
            case["questions"][current_question] = {}
            continue
        if section == "questions" and current_question and indent >= 4:
            key, value = _split_key_value(stripped)
            if value is not None:
                case["questions"][current_question][key] = _parse_scalar(value)
            continue
        raise ValueError(f"Unsupported case line: {raw_line}")
    if not case.get("name") or not case.get("pdf"):
        raise ValueError("case must define name and pdf")
    return case


def resolve_pdf_path(case_path: Path, value: str) -> Path:
    raw = Path(value).expanduser()
    candidates = [
        raw,
        case_path.parent / raw,
        ROOT / raw,
        ROOT.parent / raw,
    ]
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.exists():
            return resolved
    raise FileNotFoundError(f"PDF not found for case {case_path}: {value}")


def prepare_case_pdf(*, pdf_path: Path, pages: list[int], out_dir: Path) -> Path:
    if not pages:
        return pdf_path
    subset = out_dir / "_case_subset.pdf"
    src = fitz.open(str(pdf_path))
    dst = fitz.open()
    try:
        for page_num in pages:
            page_index = int(page_num) - 1
            if page_index < 0 or page_index >= len(src):
                raise ValueError(f"case page {page_num} is outside PDF page range 1-{len(src)}")
            dst.insert_pdf(src, from_page=page_index, to_page=page_index)
        dst.save(str(subset))
    finally:
        dst.close()
        src.close()
    return subset


def build_layout(
    *,
    case: dict[str, Any],
    parsed: dict[str, Any],
    output_dir: Path,
    source_pdf: Path,
    working_pdf: Path,
) -> dict[str, Any]:
    debug_dir = output_dir / "debug"
    exercise_blocks = _read_json(debug_dir / "exercise_blocks.json", [])
    questions = parsed.get("questions") or []
    by_index = {int(question.get("index") or question.get("index_num") or 0): question for question in questions}
    for exercise in exercise_blocks:
        core = exercise.get("question_core") or {}
        question = by_index.get(int(core.get("index") or 0))
        if question is not None:
            question["visual_ids"] = exercise.get("visual_ids") or []
    return {
        "case": case.get("name"),
        "source_pdf": str(source_pdf),
        "working_pdf": str(working_pdf),
        "source_pages": case.get("pages") or [],
        "stats": parsed.get("stats") or {},
        "layout_elements": _read_json(debug_dir / "layout-elements.json", []),
        "visuals": _read_json(debug_dir / "visuals.json", []),
        "question_cores": _read_json(debug_dir / "question_cores.json", []),
        "exercise_blocks": exercise_blocks,
        "materials": parsed.get("materials") or [],
        "questions": questions,
    }


def render_report(
    *,
    case: dict[str, Any],
    layout: dict[str, Any],
    assertions: dict[str, Any],
    overlay_files: list[str],
) -> str:
    lines = [
        f"# Visual Debug Report: {case.get('name')}",
        "",
        "## Summary",
        f"- {'PASS' if assertions['passed'] else 'FAIL'}",
        f"- Failed assertions count: {assertions['failed_count']}",
        f"- Parsed questions count: {len(layout.get('questions') or [])}",
        f"- Parsed visuals count: {len(layout.get('visuals') or [])}",
        "",
        "## Question Visual Assignments",
    ]
    for record in assertions.get("questions") or []:
        lines.append(
            f"- {record['question']}: expected={record['expected_visuals']} actual={record['actual_visuals']} "
            f"source_page={record['source_page']} source_bbox={record['source_bbox']}"
        )
    lines.extend(["", "## Visual Expansion Debug"])
    visual_by_id = {visual.get("id"): visual for visual in layout.get("visuals") or []}
    questions_by_key = case.get("questions") or {}
    for q_key, expected in questions_by_key.items():
        lines.append(f"- {q_key}:")
        for visual_id in expected.get("expected_visuals") or []:
            visual = visual_by_id.get(visual_id) or {}
            absorbed = [
                str(item.get("text") or "")
                for item in visual.get("absorbed_texts") or []
                if str(item.get("text") or "").strip()
            ]
            lines.append(
                f"  - {visual_id}: raw_bbox={visual.get('raw_bbox')} expanded_bbox={visual.get('expanded_bbox') or visual.get('bbox')} "
                f"crop={visual.get('image_path')} group={visual.get('same_visual_group_id') or visual.get('visual_group_id')} "
                f"children={visual.get('child_visual_ids') or []} absorbed_texts={absorbed}"
            )
        if not expected.get("expected_visuals"):
            lines.append("  - no visuals")
    lines.extend(["", "## Failed Assertions"])
    if assertions.get("failures"):
        for failure in assertions["failures"]:
            lines.append(f"- {failure['question']} {failure['kind']}: {failure['message']}")
    else:
        lines.append("- None")
    lines.extend(["", "## Artifacts"])
    lines.append("- layout.json")
    for file in overlay_files:
        lines.append(f"- {Path(file).name}")
    lines.extend(["", "## Agent Notes", "Inspect overlay PNGs before treating this report as complete."])
    return "\n".join(lines) + "\n"


def _read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def _split_key_value(line: str) -> tuple[str, str | None]:
    if ":" not in line:
        raise ValueError(f"Expected key/value line: {line}")
    key, value = line.split(":", 1)
    value = value.strip()
    return key.strip(), value or None


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part.strip()) for part in inner.split(",")]
    if value in {"true", "false"}:
        return value == "true"
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return ast.literal_eval(value)
    return value


if __name__ == "__main__":
    raise SystemExit(main())
