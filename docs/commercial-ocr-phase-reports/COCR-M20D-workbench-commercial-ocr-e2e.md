# COCR-M20D Workbench Commercial OCR E2E

## Summary

The workbench E2E path was updated so a real commercial OCR fixture can be validated once available. The runtime E2E itself remains BLOCKED in this session because no real commercial OCR fixture was generated.

## Changes

- Added `admin-web/e2e/data-analysis-commercial-ocr-workbench.spec.ts`
- Added root wrapper `e2e/data-analysis-commercial-ocr-workbench.spec.ts`
- Fixed `scripts/e2e/start-commercial-ocr-stack.sh` so it:
  - loads project/backend/pdf-service `.env`
  - respects external `COMMERCIAL_OCR_*`, `PDF_PARSE_*`, and `TENCENT_OCR_REAL_SMOKE`
  - no longer hard-locks `PDF_PARSE_PRIMARY_PROVIDER=mock_commercial_ocr`

## Validation

- `cd admin-web && pnpm exec tsc --noEmit`
  - pass
- `cd admin-web && pnpm build`
  - pass
- `cd /home/carry/project2 && pnpm exec playwright test e2e/data-analysis-commercial-ocr-workbench.spec.ts --list`
  - pass
  - listed test:
    - `data analysis commercial OCR workbench › renders commercial OCR bbox source and keeps shared material visible`

## Runtime Status

Not executed end-to-end on 2026-05-06 because:

- no real commercial OCR fixture root/name was produced
- no Baidu/Tencent credentials were available to generate that fixture

## Expected Runtime Inputs For Next Pass

- `E2E_REAL_BATCH_FIXTURE_ROOT`
- `E2E_REAL_BATCH_FIXTURE_NAME`
- `E2E_REAL_BATCH_EXPECTED_BBOX_SOURCE`
- optional: `E2E_REAL_BATCH_LAYOUT_ONLY=true`

## Blocking Condition

Until at least one real provider produces a fixture with `bbox_source=baidu_paper_cut_edu`, `tencent_question_split`, or `tencent_question_split_layout`, the workbench commercial OCR E2E cannot move beyond static discovery and build validation.
