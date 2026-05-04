# Commercial OCR Main Branch Report

## Summary

- Branch strategy: stay on `main`
- Merge source: `ralph/xingce-e2e-git-hygiene-delivery`
- Merge commit: `d411a90`
- Post-merge hygiene commit: `2fbf506`
- Current code baseline after overnight implementation: `d7b26a0`

## Delivered Through M8-pre

- mock fixture providers:
  - `mock_commercial_ocr`
  - `mock_tencent_question_split`
  - `mock_tencent_question_split_layout`
- real providers:
  - `baidu_paper_cut_edu`
  - `tencent_question_split`
  - `tencent_question_split_layout`
- unified modules:
  - `normalizer.py`
  - `semantic_assembler.py`
  - `quality_gate.py`
- eval hook:
  - `pdf-service/scripts/eval_commercial_ocr.py`

## Verification Snapshot

- `backend pnpm build`: passed
- `admin-web pnpm build`: passed
- `pdf-service targeted commercial OCR suite`: `27 passed / 1 skipped`
- `pdf-service full pytest`: `136 passed / 3 failed / 2 skipped`
- remaining failures are known regressions in provider health and visual smoke retry cache

## Risk Notes

- Tencent real API is still smoke-gated to explicit single-page runs.
- Visual understanding layer is still pending.
- Review UI / publish hard gate is still pending.
- Baidu Key was previously exposed in chat and should be rotated.
