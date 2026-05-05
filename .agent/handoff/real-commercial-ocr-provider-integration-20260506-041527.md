# Handoff: Real Commercial OCR Provider Integration

## Context

- branch: `mimo`
- starting head: `52e3851b9ac8e316c7286678774d2bfd66881a2d`
- date: `2026-05-06 04:15:27 CST (+0800)`

## Finished In This Session

- Added:
  - `pdf-service/scripts/run_real_commercial_ocr_smoke.py`
  - `pdf-service/scripts/run_real_commercial_ocr_batch.py`
  - `pdf-service/scripts/compare_commercial_vs_local_bbox.py`
  - `pdf-service/scripts/provider_health_report.py`
  - `pdf-service/tests/test_real_commercial_ocr_scripts.py`
  - `admin-web/e2e/data-analysis-commercial-ocr-workbench.spec.ts`
  - `e2e/data-analysis-commercial-ocr-workbench.spec.ts`
- Updated:
  - `pdf-service/scripts/run_real_data_analysis_batch_smoke.py`
  - `scripts/e2e/start-commercial-ocr-stack.sh`
- Wrote M20D reports under `docs/commercial-ocr-phase-reports/` and `.agent/reports/`.

## Current Blocker

Real commercial OCR is blocked by configuration availability, not by the smoke harness anymore.

- Shell env has no Baidu/Tencent commercial OCR keys.
- Project/backend/pdf-service `.env` files have no Baidu/Tencent commercial OCR keys.
- Backend DB config source could not be checked because MySQL connection failed: `ECONNREFUSED 127.0.0.1:3306`.

## Verified Outputs

- Baidu page 1 smoke: `skipped_unavailable` -> `key_missing`
- Tencent page 1 smoke: `skipped_unavailable` -> `key_missing`
- Baidu batch pages `1,6,16`: `blocked=true`
- bbox comparison currently recommends `local`

## Commands Already Validated

- `cd pdf-service && ./.venv/bin/python -m pytest tests/test_data_analysis_real_smoke_scripts.py tests/test_commercial_ocr_pipeline.py tests/test_real_commercial_ocr_scripts.py -q`
- `cd pdf-service && ./.venv/bin/python scripts/run_real_commercial_ocr_smoke.py --help`
- `cd pdf-service && ./.venv/bin/python scripts/run_real_commercial_ocr_batch.py --help`
- `cd pdf-service && ./.venv/bin/python scripts/compare_commercial_vs_local_bbox.py --help`
- `cd pdf-service && ./.venv/bin/python scripts/provider_health_report.py`
- `bash -n scripts/e2e/start-commercial-ocr-stack.sh`
- `cd admin-web && pnpm exec tsc --noEmit`
- `cd admin-web && pnpm build`
- `cd /home/carry/project2 && pnpm exec playwright test e2e/data-analysis-commercial-ocr-workbench.spec.ts --list`

## Next Commands Once Keys Exist

1. `cd pdf-service && ./.venv/bin/python scripts/run_real_commercial_ocr_smoke.py --pdf '/home/carry/project2/题本/题本篇.pdf' --page 1 --provider baidu_paper_cut_edu --real-smoke true`
2. `cd pdf-service && ./.venv/bin/python scripts/run_real_commercial_ocr_smoke.py --pdf '/home/carry/project2/题本/题本篇.pdf' --page 1 --provider tencent_question_split --real-smoke true`
3. `cd pdf-service && ./.venv/bin/python scripts/run_real_commercial_ocr_batch.py --pdf '/home/carry/project2/题本/题本篇.pdf' --pages '1,6,16' --provider <baidu_paper_cut_edu|tencent_question_split|tencent_question_split_layout> --max-pages 3 --real-smoke true`
4. `cd pdf-service && ./.venv/bin/python scripts/compare_commercial_vs_local_bbox.py 'debug/real-commercial-ocr-smoke/current/batch-commercial-ocr-summary.json' 'debug/real-data-data-analysis/batch-tiben-selected/batch-ocr-summary.json'`
5. Export `E2E_REAL_BATCH_FIXTURE_ROOT`, `E2E_REAL_BATCH_FIXTURE_NAME`, `E2E_REAL_BATCH_EXPECTED_BBOX_SOURCE`
6. `cd /home/carry/project2 && pnpm exec playwright test e2e/data-analysis-commercial-ocr-workbench.spec.ts --trace=on`

## Not Done

- No real Baidu/Tencent auth success
- No real `bbox_source` promotion away from `tesseract_local_ocr`
- No runtime workbench commercial OCR E2E
- No VLM/LLM rerun under real commercial bbox
