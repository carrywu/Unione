# Real Commercial OCR Provider Integration Report

## Status

- branch: `mimo`
- head before local changes: `52e3851b9ac8e316c7286678774d2bfd66881a2d`
- date: `2026-05-06`
- overall: `BLOCKED`

## What Was Completed

- Added real-provider single-page smoke CLI.
- Added real-provider batch CLI for pages `1,6,16`.
- Added commercial-vs-local bbox comparison CLI.
- Added documented `scripts/provider_health_report.py` entrypoint.
- Enriched existing real data-analysis batch summary fields for future bbox comparison.
- Fixed the E2E stack launcher so it can honor real provider env instead of always forcing mock.
- Added a workbench commercial OCR Playwright spec plus root discovery wrapper.

## What Was Proven

- Current Baidu run fails before auth attempt because the workspace has no `BAIDU_API_KEY` / `BAIDU_SECRET_KEY` / `BAIDU_ACCESS_TOKEN`.
- Current Tencent run fails before auth attempt because the workspace has no `TENCENT_SECRET_ID` / `TENCENT_SECRET_KEY`.
- `TENCENT_OCR_REAL_SMOKE=true` is now honored by the smoke CLI, so future Tencent unavailability will not be hidden behind the smoke flag.
- Existing `skipped_unavailable` output is now concretely classified as `key_missing`.

## What Is Still Missing

- Real Baidu success on page `1`, `6`, or `16`
- Real Tencent success on page `1`, `6`, or `16`
- `bbox_source` promotion away from `tesseract_local_ocr`
- Workbench runtime E2E against a commercial fixture
- VLM/LLM rerun under real commercial bbox

## Key Evidence

- `debug/real-commercial-ocr-smoke/current/baidu-page-1-summary.json`
- `debug/real-commercial-ocr-smoke/current/tencent-page-1-summary.json`
- `debug/real-commercial-ocr-smoke/current/batch-commercial-ocr-summary.json`
- `debug/real-commercial-ocr-smoke/current/bbox-comparison.json`
- `docs/commercial-ocr-phase-reports/COCR-M20D-real-commercial-ocr-provider-integration.md`
- `docs/commercial-ocr-phase-reports/COCR-M20D-commercial-vs-local-bbox-comparison.md`
- `docs/commercial-ocr-phase-reports/COCR-M20D-workbench-commercial-ocr-e2e.md`

## Immediate Next Step

Inject one working Baidu or Tencent credential set into env or into a reachable backend config source, then rerun the new smoke and batch CLIs before attempting workbench import or quality-gate promotion.
