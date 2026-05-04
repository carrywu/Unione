from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def merge_question_numbers(*groups: list[int]) -> list[int]:
    merged: set[int] = set()
    for group in groups:
        for value in group or []:
            try:
                number = int(value)
            except (TypeError, ValueError):
                continue
            if number > 0:
                merged.add(number)
    return sorted(merged)


def expected_question_numbers(total: int) -> list[int]:
    return list(range(1, max(0, int(total)) + 1))


def missing_question_numbers(produced: list[int], expected_total: int) -> list[int]:
    produced_set = set(merge_question_numbers(produced))
    return [number for number in expected_question_numbers(expected_total) if number not in produced_set]


def build_verifier_report(
    *,
    task_id: str,
    produced_question_numbers: list[int],
    expected_total: int,
    fallback_failed_pages: list[int],
    provider_recovery: dict[str, Any],
    debug_live_consistency: str,
    live_api_counts: dict[str, int] | None = None,
    evidence_paths: list[str] | None = None,
    repair_actions: list[str] | None = None,
    root_cause: list[str] | None = None,
    authoritative_task_id: str | None = None,
) -> dict[str, Any]:
    produced_numbers = merge_question_numbers(produced_question_numbers)
    missing_numbers = missing_question_numbers(produced_numbers, expected_total)
    failed_checks: list[str] = []
    passed_checks: list[str] = []

    provider_health = str(provider_recovery.get("provider_health") or "fail")
    if fallback_failed_pages:
        failed_checks.append(f"fallback_failed_pages={fallback_failed_pages}")
    else:
        passed_checks.append("fallback_failed_pages_cleared")

    if produced_numbers and not missing_numbers and len(produced_numbers) == expected_total:
        passed_checks.append(f"produced_question_count={expected_total}")
    else:
        failed_checks.append(
            f"produced_question_count={len(produced_numbers)}/{expected_total}; missing={missing_numbers}"
        )

    if debug_live_consistency == "pass":
        passed_checks.append("debug_live_consistency=pass")
    else:
        failed_checks.append("debug_live_consistency=fail")

    if provider_recovery.get("used_for_page_5") and provider_health == "pass":
        passed_checks.append("page_5_provider_recovery=pass")
    elif provider_recovery.get("used_for_page_5"):
        failed_checks.append(
            f"page_5_provider_recovery=fail({provider_recovery.get('new_provider')}:{provider_health})"
        )

    m2_pass = not failed_checks
    next_action = "M3_READY" if m2_pass else "KEEP_BLOCKED"
    return {
        "task_id": task_id,
        "current_milestone": "M2",
        "m2_verdict": "M2_PASS" if m2_pass else "M2_FAIL",
        "m3_allowed": m2_pass,
        "provider_recovery": provider_recovery,
        "fallback_failed_pages": sorted({int(page) for page in fallback_failed_pages}),
        "missing_question_numbers": missing_numbers,
        "produced_question_count": len(produced_numbers),
        "expected_question_count": int(expected_total),
        "produced_question_numbers": produced_numbers,
        "debug_live_consistency": debug_live_consistency,
        "live_api_counts": live_api_counts or {
            "canAddToPaper_true": 0,
            "manualForceAddAllowed_true": 0,
        },
        "failed_checks": failed_checks,
        "passed_checks": passed_checks,
        "repair_actions": repair_actions or [],
        "root_cause": root_cause or [],
        "evidence_paths": evidence_paths or [],
        "authoritative_task_id": authoritative_task_id,
        "next_action": next_action,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Verifier Report",
        "",
        f"- task_id: {report.get('task_id')}",
        f"- current_milestone: {report.get('current_milestone')}",
        f"- m2_verdict: {report.get('m2_verdict')}",
        f"- m3_allowed: {report.get('m3_allowed')}",
        f"- produced_question_count: {report.get('produced_question_count')}/{report.get('expected_question_count')}",
        f"- missing_question_numbers: {json.dumps(report.get('missing_question_numbers') or [], ensure_ascii=False)}",
        f"- fallback_failed_pages: {json.dumps(report.get('fallback_failed_pages') or [], ensure_ascii=False)}",
        f"- debug_live_consistency: {report.get('debug_live_consistency')}",
        f"- next_action: {report.get('next_action')}",
        "",
        "## Provider Recovery",
        "",
        f"- new_provider: {report.get('provider_recovery', {}).get('new_provider')}",
        f"- used_for_page_5: {report.get('provider_recovery', {}).get('used_for_page_5')}",
        f"- provider_health: {report.get('provider_recovery', {}).get('provider_health')}",
        f"- api_mode: {report.get('provider_recovery', {}).get('api_mode') or ''}",
        f"- successful_model: {report.get('provider_recovery', {}).get('successful_model') or ''}",
        f"- successful_model_type: {report.get('provider_recovery', {}).get('successful_model_type') or ''}",
        "",
        "## Failed Checks",
        "",
    ]
    failed_checks = report.get("failed_checks") or []
    if failed_checks:
        lines.extend(f"- {item}" for item in failed_checks)
    else:
        lines.append("- none")
    lines.extend(["", "## Passed Checks", ""])
    passed_checks = report.get("passed_checks") or []
    if passed_checks:
        lines.extend(f"- {item}" for item in passed_checks)
    else:
        lines.append("- none")
    lines.extend(["", "## Root Cause", ""])
    root_cause = report.get("root_cause") or []
    if root_cause:
        lines.extend(f"- {item}" for item in root_cause)
    else:
        lines.append("- none")
    lines.extend(["", "## Repair Actions", ""])
    repair_actions = report.get("repair_actions") or []
    if repair_actions:
        lines.extend(f"- {item}" for item in repair_actions)
    else:
        lines.append("- none")
    lines.extend(["", "## Evidence Paths", ""])
    evidence_paths = report.get("evidence_paths") or []
    if evidence_paths:
        lines.extend(f"- {item}" for item in evidence_paths)
    else:
        lines.append("- none")
    return "\n".join(lines).strip() + "\n"


def write_report(report: dict[str, Any], *, json_path: str | Path, markdown_path: str | Path) -> None:
    json_file = Path(json_path)
    md_file = Path(markdown_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    md_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_file.write_text(render_markdown(report), encoding="utf-8")
