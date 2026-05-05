# Data Analysis Real Multipage Hardening Report

## Summary

- Branch: `mimo`
- Start commit for this stage: `f0ad797812f7177387325521448da3ae22c8c86a`
- Stage: `COCR-M20C`
- Scope: 继续只做资料分析，把真实验证从单页 smoke 推到多页、多题组、多 provider 策略和 workbench import 硬化

## Delivered

1. 新增真实题本候选页发现、批量 OCR smoke、批量 visual smoke、批量 understanding smoke、quality matrix 评估脚本。
2. 在无百度/腾讯 key 的前提下，显式记录 commercial OCR `skipped_unavailable`，并用 `tesseract_local_ocr` 完成真实题本材料组发现和 import 兜底，不伪装成商业 OCR 成功。
3. 真实批量 visual 证明：`qwen_vl` 在资料分析页 `3/3 timeout`，Ark `3/3` rescue 成功，`mimo_vl` 继续 deprioritize。
4. `qwen-plus` 对 `17-20` 的真实 understanding 表现符合预期：1 题低置信尝试，3 题拒答/不放行。
5. workbench real batch Playwright 已打通，`bbox_source=tesseract_local_ocr` 可见，`审核通过` 被正确阻止，H5 shared material 不丢。
6. 旧 `page_understanding` / `semantic_groups` / `recrop_plan` 的定位进一步收缩为 compat/debug，不再作为资料分析主链权威来源。

## Key Numbers

- real pages scanned: `20`
- candidate pages matched: `12`
- selected start pages run: `3` (`1`, `6`, `16`)
- commercial OCR real calls: `0` successful / `9 skipped_unavailable`
- local OCR groups: `3`
- `qwen_vl` timeouts: `3`
- Ark hedge successes: `3`
- `mimo_vl`: configured but quota exhausted in provider health
- understanding questions run: `4`
- `review_ready`: `0/4`
- `needs_human_review`: `4/4`

## Verification

- `cd pdf-service && ./.venv/bin/python -m pytest tests/test_commercial_ocr_pipeline.py tests/test_data_analysis_real_smoke_scripts.py -q`: `13 passed`
- `cd pdf-service && ./.venv/bin/python -m pytest tests/ -q`: `158 passed, 2 skipped`
- `cd backend && pnpm exec tsc -p tsconfig.build.json --noEmit`: PASS
- `cd backend && pnpm build`: PASS
- `cd admin-web && pnpm exec vue-tsc --noEmit`: PASS
- `cd admin-web && pnpm build`: PASS
- `cd h5-web && pnpm build`: PASS
- `pnpm exec playwright test e2e/data-analysis-workbench.spec.ts e2e/data-analysis-real-batch-workbench.spec.ts --trace=on`: `3 passed`

## Evidence

- candidate discovery: `debug/real-data-data-analysis/discover-tiben-local-1-20/`
- batch smoke: `debug/real-data-data-analysis/batch-tiben-selected/`
- provider health: `.agent/reports/provider-health-report.json`, `.agent/reports/provider-health-report.md`
- Ark detail: `.agent/reports/volcengine-ark-provider-report.md`
- reports:
  - `docs/commercial-ocr-phase-reports/COCR-M20C-real-data-multipage-data-analysis.md`
  - `docs/commercial-ocr-phase-reports/COCR-M20C-legacy-pdfserver-chain-contraction.md`
  - `docs/commercial-ocr-phase-reports/COCR-M20C-provider-strategy.md`
  - `docs/commercial-ocr-phase-reports/COCR-M20C-real-quality-matrix.md`
  - `docs/commercial-ocr-phase-reports/COCR-M20C-workbench-real-batch-e2e.md`

## Residual Risks

- 还没有真实百度/腾讯 OCR 多页成功样本，因此 OCR provider 排序仍未知
- `tesseract_local_ocr` 只能证明真实题本分组和 UI 导入稳定，不能替代商业 OCR 主链验收
- provider health 的 toy smoke 与真实资料分析批量表现不一致，后续不能只看 health report 决策
- Ark 当前仍有 endpoint-id `403` 和 local data-url timeout 风险，成功依赖模型名 fallback
