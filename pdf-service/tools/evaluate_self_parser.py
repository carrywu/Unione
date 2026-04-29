from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategies.markdown_question_strategy import MarkdownQuestionStrategy


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the self-built PDF parser and write quality metrics.")
    parser.add_argument("pdf", help="Path to the PDF sample.")
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "tmp" / "self-parser-eval"),
        help="Directory for debug bundles and reports.",
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf).expanduser().resolve()
    if not pdf_path.exists():
        raise SystemExit(f"PDF does not exist: {pdf_path}")

    output_dir = Path(args.output_dir).expanduser().resolve()
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    parsed = MarkdownQuestionStrategy().parse(str(pdf_path), output_dir=str(output_dir))
    report = summarize_parse(pdf_path, output_dir, parsed)

    (output_dir / "self_parser_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "self_parser_report.md").write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def summarize_parse(pdf_path: Path, output_dir: Path, parsed: dict[str, Any]) -> dict[str, Any]:
    questions = parsed.get("questions") or []
    materials = parsed.get("materials") or []
    debug_dir = output_dir / "debug"
    visuals = read_json(debug_dir / "visuals.json", [])
    elements = read_json(debug_dir / "layout-elements.json", [])
    warning_counts = Counter(
        warning
        for question in questions
        for warning in (question.get("parse_warnings") or [])
    )
    question_indices = [question.get("index") for question in questions]

    return {
        "pdf": str(pdf_path),
        "extractor": (parsed.get("stats") or {}).get("extractor"),
        "debug_dir": str(output_dir),
        "questions": len(questions),
        "materials": len(materials),
        "layout_elements": len(elements),
        "visuals": len(visuals),
        "assigned_visuals": sum(1 for visual in visuals if visual.get("assigned_to")),
        "questions_with_images": sum(1 for question in questions if question.get("images")),
        "needs_review": sum(1 for question in questions if question.get("needs_review")),
        "question_indices": question_indices,
        "duplicate_indices": duplicate_values(question_indices),
        "suspicious_indices": [
            index
            for index in question_indices
            if isinstance(index, int) and (index <= 0 or index > max(len(questions) + 20, 200))
        ],
        "warning_counts": dict(sorted(warning_counts.items())),
        "first_question": summarize_question(questions[0]) if questions else None,
    }


def summarize_question(question: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": question.get("index"),
        "page_range": question.get("page_range"),
        "material_id": question.get("material_id"),
        "options_count": len(question.get("options") or {}),
        "images_count": len(question.get("images") or []),
        "needs_review": bool(question.get("needs_review")),
        "warnings": question.get("parse_warnings") or [],
        "content_preview": (question.get("content") or "")[:240],
    }


def duplicate_values(values: list[Any]) -> list[Any]:
    counts = Counter(value for value in values if value is not None)
    return [value for value, count in counts.items() if count > 1]


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Self Parser Evaluation",
        "",
        f"- PDF: `{report['pdf']}`",
        f"- Extractor: `{report.get('extractor') or '-'}`",
        f"- Debug dir: `{report['debug_dir']}`",
        "",
        "| Questions | Materials | Visuals | Assigned visuals | With images | Needs review | Duplicate indices | Suspicious indices |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
        "| {questions} | {materials} | {visuals} | {assigned_visuals} | {questions_with_images} | "
        "{needs_review} | {duplicate_indices} | {suspicious_indices} |".format(
            questions=report["questions"],
            materials=report["materials"],
            visuals=report["visuals"],
            assigned_visuals=report["assigned_visuals"],
            questions_with_images=report["questions_with_images"],
            needs_review=report["needs_review"],
            duplicate_indices=", ".join(str(value) for value in report["duplicate_indices"]) or "-",
            suspicious_indices=", ".join(str(value) for value in report["suspicious_indices"]) or "-",
        ),
        "",
        "## Warnings",
        "",
    ]
    warnings = report.get("warning_counts") or {}
    if warnings:
        lines.extend(f"- `{key}`: {value}" for key, value in warnings.items())
    else:
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
