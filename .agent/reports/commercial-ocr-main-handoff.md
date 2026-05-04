# Commercial OCR Main Branch Report

## Summary

- Branch strategy: stay on `main`
- Merge source: `ralph/xingce-e2e-git-hygiene-delivery`
- Merge commit: `d411a90`
- Post-merge hygiene commit: `2fbf506`
- Current phase docs:
  - `docs/commercial-ocr-phase-reports/COCR-M0-baseline.md`
  - `docs/commercial-ocr-phase-reports/COCR-M1-merge-main-and-provider-baseline.md`

## Code Delivered In M1

- `pdf-service/commercial_ocr/types.py`
- `pdf-service/commercial_ocr/adapters.py`
- `pdf-service/commercial_ocr/service.py`
- `pdf-service/tests/test_commercial_ocr_pipeline.py`
- `pdf-service/tests/test_commercial_ocr_kernel_integration.py`

## Verification Snapshot

- `backend pnpm test`: failed because no `test` script exists
- `backend pnpm build`: passed
- `admin-web pnpm build`: passed
- `pdf-service python3 -m pytest tests/ -v`: failed because system Python lacks dependencies
- `pdf-service .venv targeted commercial OCR tests`: 6 passed
- `pdf-service .venv full pytest`: 115 passed, 3 failed, 1 skipped
- `baidu paper_cut_edu` real smoke: passed on one page

## Risks

- semantic assembler still pending
- Tencent real adapter still pending
- quality gate still only defined as contract
- browser verification not refreshed in this round
- existing full-suite failures remain in provider health and visual smoke cache tests
