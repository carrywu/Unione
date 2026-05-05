# COCR-M20D Real Commercial OCR Provider Integration

## Summary

As of 2026-05-06, the M20D code path for real commercial OCR provider validation is in place, but the actual Baidu/Tencent provider run is still BLOCKED by missing runtime credentials in the current workspace.

- branch: `mimo`
- base commit before local M20D edits: `52e3851b9ac8e316c7286678774d2bfd66881a2d`
- PDF ref: `题本/题本篇.pdf`

## Root Cause

`skipped_unavailable` is now reduced to concrete causes instead of a generic unavailable bucket.

- Shell environment on 2026-05-06 contained no `BAIDU_*`, `TENCENT_*`, `COMMERCIAL_OCR_*`, or `PDF_PARSE_*` commercial OCR runtime variables.
- `/home/carry/project2/.env`, `/home/carry/project2/backend/.env`, and `/home/carry/project2/pdf-service/.env` contained no commercial OCR provider keys.
- The backend alternate config source could not be verified because the configured MySQL target was unreachable during this run: `ECONNREFUSED 127.0.0.1:3306`.
- `scripts/e2e/start-commercial-ocr-stack.sh` previously hard-forced `PDF_PARSE_PRIMARY_PROVIDER=mock_commercial_ocr`; this was fixed so future E2E runs can honor real provider env once keys exist.

## Implemented Changes

- Added `pdf-service/scripts/run_real_commercial_ocr_smoke.py` for single-page real-provider smoke with redacted summaries.
- Added `pdf-service/scripts/run_real_commercial_ocr_batch.py` for `pages=1,6,16` style commercial-only batch runs.
- Added `pdf-service/scripts/compare_commercial_vs_local_bbox.py` for commercial vs local bbox comparison summaries.
- Added `pdf-service/scripts/provider_health_report.py` wrapper so the documented script path works.
- Enriched `pdf-service/scripts/run_real_data_analysis_batch_smoke.py` summaries with:
  - `skipped_reason`
  - `question_numbers`
  - `question_bboxes`
  - `material_bboxes`
  - `shared_material_detected`
  - `layout_only`
  - `raw_ref_redacted`
- Added `admin-web/e2e/data-analysis-commercial-ocr-workbench.spec.ts` plus root wrapper `e2e/data-analysis-commercial-ocr-workbench.spec.ts`.
- Updated `scripts/e2e/start-commercial-ocr-stack.sh` to load `.env` files and preserve external real-provider overrides instead of forcing mock forever.

## Real Smoke Results

### Baidu

- command: `./.venv/bin/python scripts/run_real_commercial_ocr_smoke.py --pdf '/home/carry/project2/题本/题本篇.pdf' --page 1 --provider baidu_paper_cut_edu --real-smoke true`
- status: `skipped_unavailable`
- skipped_reason: `key_missing`
- warnings:
  - `missing_baidu_api_key`
  - `missing_baidu_secret_key`
- provider_config_status:
  - `api_key_present=false`
  - `secret_key_present=false`
  - `access_token_present=false`
  - `endpoint_present=true`

### Tencent

- command: `./.venv/bin/python scripts/run_real_commercial_ocr_smoke.py --pdf '/home/carry/project2/题本/题本篇.pdf' --page 1 --provider tencent_question_split --real-smoke true`
- status: `skipped_unavailable`
- skipped_reason: `key_missing`
- warnings:
  - `missing_tencent_secret_id`
  - `missing_tencent_secret_key`
- provider_config_status:
  - `secret_id_present=false`
  - `secret_key_present=false`
  - `region_present=true`
  - `endpoint_present=true`
  - `version_present=true`
  - `real_smoke_enabled=true`

## Batch Result For Pages 1 / 6 / 16

- command: `./.venv/bin/python scripts/run_real_commercial_ocr_batch.py --pdf '/home/carry/project2/题本/题本篇.pdf' --pages '1,6,16' --provider baidu_paper_cut_edu --max-pages 3 --real-smoke true`
- result:
  - `commercial_success_page_count=0`
  - `commercial_partial_page_count=0`
  - `blocked_page_count=3`
  - `blocked=true`
- per-page status:
  - page 1: `skipped_unavailable` / `key_missing`
  - page 6: `skipped_unavailable` / `key_missing`
  - page 16: `skipped_unavailable` / `key_missing`

## Validation

- `cd pdf-service && ./.venv/bin/python -m pytest tests/test_data_analysis_real_smoke_scripts.py tests/test_commercial_ocr_pipeline.py tests/test_real_commercial_ocr_scripts.py -q`
  - result: `16 passed`
- `cd pdf-service && ./.venv/bin/python scripts/provider_health_report.py`
  - result: report files regenerated under `.agent/reports/`
- `bash -n scripts/e2e/start-commercial-ocr-stack.sh`
  - result: pass
- `cd admin-web && pnpm exec tsc --noEmit`
  - result: pass
- `cd admin-web && pnpm build`
  - result: pass
- `cd /home/carry/project2 && pnpm exec playwright test e2e/data-analysis-commercial-ocr-workbench.spec.ts --list`
  - result: spec discoverable, 1 test listed

## Evidence

- smoke:
  - `debug/real-commercial-ocr-smoke/current/baidu-page-1-summary.json`
  - `debug/real-commercial-ocr-smoke/current/tencent-page-1-summary.json`
  - `debug/real-commercial-ocr-smoke/current/batch-commercial-ocr-summary.json`
- comparison:
  - `debug/real-commercial-ocr-smoke/current/bbox-comparison.json`
- provider health:
  - `.agent/reports/provider-health-report.json`
  - `.agent/reports/provider-health-report.md`
  - `.agent/reports/volcengine-ark-provider-report.md`

## Conclusion

The M20D code and validation harness are ready, but the true commercial OCR success criterion is still unmet in the current environment because no Baidu/Tencent credentials were available to the smoke scripts and the backend DB config source could not be reached.
