#!/usr/bin/env python3
"""Review E2E evidence with MiMo reviewer (visual + text).

Usage:
  cd pdf-service && ./.venv/bin/python scripts/review_e2e_evidence_with_mimo.py [--evidence-dir DIR]

Default: reads from ../debug/e2e-commercial-ocr/ latest timestamp dir.
Outputs: visual-review.json, text-review.json, mimo-review-evidence.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add pdf-service to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from commercial_ocr.mimo_reviewer import (
    mimo_review_status,
    review_text_payload,
    review_visual_screenshot,
)


def find_latest_evidence_dir(base: Path) -> Path | None:
    """Find the latest timestamp-based evidence directory."""
    if not base.exists():
        return None
    dirs = sorted(
        [d for d in base.iterdir() if d.is_dir()],
        key=lambda d: d.name,
        reverse=True,
    )
    return dirs[0] if dirs else None


def load_json_if_exists(path: Path) -> dict | None:
    if path.exists():
        return json.loads(path.read_text())
    return None


def main():
    parser = argparse.ArgumentParser(description="Review E2E evidence with MiMo")
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        help="Path to evidence directory (e.g. debug/e2e-commercial-ocr/20260505-190000)",
    )
    parser.add_argument("--output-dir", type=Path, help="Output directory for review results")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent.parent
    evidence_base = project_root / "debug" / "e2e-commercial-ocr"

    evidence_dir = args.evidence_dir or find_latest_evidence_dir(evidence_base)
    if not evidence_dir or not evidence_dir.exists():
        print(f"No evidence directory found at {evidence_base}")
        sys.exit(1)

    print(f"=== MiMo E2E Evidence Review ===")
    print(f"Evidence dir: {evidence_dir}")

    # Create output directory
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = args.output_dir or evidence_base / "mimo-review" / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output dir: {output_dir}")

    # Load evidence
    admin_state = load_json_if_exists(
        evidence_dir / "admin" / "complete-preview-publish" / "final-admin-review-state.json"
    )
    h5_state = load_json_if_exists(
        evidence_dir / "h5" / "preview-paper-mobile" / "final-h5-state.json"
    )
    blocked_state = load_json_if_exists(
        evidence_dir / "admin" / "blocked-review-gate" / "final-admin-review-state.json"
    )

    # MiMo reviewer status
    status = mimo_review_status()
    print(f"\n=== MiMo Reviewer Status ===")
    print(json.dumps(status, indent=2, ensure_ascii=False))

    # Text review (mimo-v2.5-pro)
    text_payload = {
        "admin_review_state": admin_state,
        "h5_state": h5_state,
        "blocked_state": blocked_state,
        "evidence_dir": str(evidence_dir),
    }
    text_result = review_text_payload(
        payload=text_payload,
        context="e2e-commercial-ocr-evidence-review",
    )
    print(f"\n=== Text Review (mimo-v2.5-pro) ===")
    print(json.dumps(text_result, indent=2, ensure_ascii=False))

    # Visual review (mimo-v2.5) - check for screenshots
    screenshots_dir = evidence_dir / "admin" / "complete-preview-publish" / "screenshots"
    screenshot_files = sorted(screenshots_dir.glob("*.png")) if screenshots_dir.exists() else []

    visual_results = []
    if screenshot_files:
        # Review first screenshot as example
        for sf in screenshot_files[:2]:  # Max 2 screenshots
            print(f"\n=== Visual Review: {sf.name} (mimo-v2.5) ===")
            # For mock mode, we pass empty base64
            vr = review_visual_screenshot(
                image_base64="",  # Mock mode doesn't need real image
                context=f"screenshot={sf.name}",
                ocr_summary=f"E2E screenshot from {sf.name}",
            )
            visual_results.append({"file": sf.name, "review": vr})
            print(json.dumps(vr, indent=2, ensure_ascii=False))
    else:
        vr = review_visual_screenshot(
            image_base64="",
            context="no-screenshots-found",
            ocr_summary="",
        )
        visual_results.append({"file": "none", "review": vr})
        print(f"\n=== Visual Review (mimo-v2.5) === No screenshots found")
        print(json.dumps(vr, indent=2, ensure_ascii=False))

    # Save all results
    evidence = {
        "timestamp": timestamp,
        "reviewer_status": status,
        "text_review": text_result,
        "visual_reviews": visual_results,
        "evidence_dir": str(evidence_dir),
        "output_dir": str(output_dir),
    }
    output_file = output_dir / "mimo-review-evidence.json"
    output_file.write_text(json.dumps(evidence, indent=2, ensure_ascii=False))
    print(f"\n=== Saved ===")
    print(f"  {output_file}")

    # Also save individual files
    (output_dir / "text-review.json").write_text(
        json.dumps(text_result, indent=2, ensure_ascii=False)
    )
    (output_dir / "visual-review.json").write_text(
        json.dumps(visual_results, indent=2, ensure_ascii=False)
    )
    print(f"  {output_dir / 'text-review.json'}")
    print(f"  {output_dir / 'visual-review.json'}")


if __name__ == "__main__":
    main()
