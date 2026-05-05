# COCR-M20D Commercial vs Local BBox Comparison

## Summary

The comparison harness is implemented and was executed on 2026-05-06, but the current comparison is diagnostic-only because the commercial provider run produced no bbox output.

- commercial summary: `debug/real-commercial-ocr-smoke/current/batch-commercial-ocr-summary.json`
- local summary: `debug/real-data-data-analysis/batch-tiben-selected/batch-ocr-summary.json`
- output: `debug/real-commercial-ocr-smoke/current/bbox-comparison.json`

## Result

For pages `1`, `6`, and `16`:

- commercial provider: `baidu_paper_cut_edu`
- commercial status: `skipped_unavailable`
- commercial skipped_reason: `key_missing`
- recommended source: `local`

Per-page comparison output currently reports:

- `commercial_bbox_count=0`
- `local_bbox_count=0` in the existing local batch summary payload
- `material_bbox_overlap=null`
- `question_bbox_overlap=null`

## Why Overlap Is Unavailable

- The current commercial batch produced no question or material bboxes because the provider never authenticated.
- The older local fallback summary that M20C generated does not carry full bbox coordinate arrays for overlap math.
- The new comparison script now supports coordinate overlap when future summaries include `question_bboxes` and `material_bboxes`.

## Interpretation

- There is no evidence yet that commercial OCR can replace `tesseract_local_ocr` for pages `1/6/16`.
- The comparison harness is usable for the next rerun once a real provider succeeds.
- Until a real provider returns structured question/material bbox payloads, `recommended_source` must remain `local`.

## Next Required Rerun

1. Provide real Baidu or Tencent credentials through env or reachable backend config.
2. Re-run `run_real_commercial_ocr_batch.py` on `1,6,16`.
3. Re-run `compare_commercial_vs_local_bbox.py` against the new batch output and local fallback summary.
4. Promote `recommended_source=commercial` only when at least one real provider returns usable bbox data.
