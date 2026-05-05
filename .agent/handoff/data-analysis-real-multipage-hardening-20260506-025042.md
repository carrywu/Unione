# COCR-M20C Handoff

## 当前分支

- `mimo`

## 本轮开始时 commit

- `f0ad797812f7177387325521448da3ae22c8c86a`

## baseline tag

- `pre-data-analysis-ocr-api-first-20260505-221735`

## 已完成内容

- 真实题本 `题本/题本篇.pdf` 已完成多页候选发现，20 页中命中 12 个资料分析候选页，限量选中 3 组起始页：`1`、`6`、`16`
- 新增并验证：
  - `pdf-service/scripts/data_analysis_local_ocr.py`
  - `pdf-service/scripts/discover_data_analysis_pages.py`
  - `pdf-service/scripts/run_real_data_analysis_batch_smoke.py`
  - `pdf-service/scripts/run_real_visual_context_batch_smoke.py`
  - `pdf-service/scripts/run_real_data_analysis_understanding_batch_smoke.py`
  - `pdf-service/scripts/eval_data_analysis_real_quality_matrix.py`
- 真实多页 visual 结果已固化：
  - `qwen_vl` `3/3 timeout`
  - `volcengine_ark_vl` `3/3` hedge success
  - `mimo_vl` 继续不作为第一备援
- 真实 `17-20` understanding 结果已固化：
  - `17` 题低置信尝试，答案建议 `B`
  - `18-20` 题不放行，均进入 `needs_human_review`
- real batch workbench import / H5 preview 已通过
- `bbox_source=tesseract_local_ocr` 显式可见，不会伪装成 `local_parser`
- `page_understanding` / `semantic_groups` / `recrop_plan` 的主链地位已在 M20C 报告中收缩归类

## 本轮关键结论

1. 真实资料分析多页里，`qwen_vl` 不能被描述成稳定第一 provider；它只能作为“先试一下”的 provider，并且必须有短超时。
2. Ark 是真实多页批量里的有效 hedge，但仍有单独 endpoint / local-data-url 风险，不能写成无条件稳定。
3. 没有真实百度/腾讯 key 时，不得冒充商业 OCR 成功；当前 `tesseract_local_ocr` 只是为了继续完成真实题本发现、材料组导入和 UI 验收。
4. 当前 `17-20` 组 `review_ready=0/4`，这是正确行为，不是回归。

## 未完成内容

- 真实百度或腾讯 OCR provider 的多页成功验证仍缺失
- 当前 workbench real batch 仍依赖 import fixture，而不是生产默认链路直接放行
- 非资料分析题型没有扩展

## 测试结果

- `cd pdf-service && ./.venv/bin/python -m pytest tests/test_commercial_ocr_pipeline.py tests/test_data_analysis_real_smoke_scripts.py -q`: `13 passed`
- `cd pdf-service && ./.venv/bin/python -m pytest tests/ -q`: `158 passed, 2 skipped`
- `cd backend && pnpm exec tsc -p tsconfig.build.json --noEmit`: PASS
- `cd backend && pnpm build`: PASS
- `cd admin-web && pnpm exec vue-tsc --noEmit`: PASS
- `cd admin-web && pnpm build`: PASS
- `cd h5-web && pnpm build`: PASS
- `pnpm exec playwright test e2e/data-analysis-workbench.spec.ts e2e/data-analysis-real-batch-workbench.spec.ts --trace=on`: `3 passed`
- `cd backend && pnpm test`: skipped，原因是 `backend/package.json` 无 `test` script

## 证据路径

- 候选页：`debug/real-data-data-analysis/discover-tiben-local-1-20/`
- batch smoke：`debug/real-data-data-analysis/batch-tiben-selected/`
- workbench import fixture：`debug/real-data-data-analysis/batch-tiben-selected/workbench-import-fixtures/page016-local-group1-import.json`
- provider health：`.agent/reports/provider-health-report.json`
- Ark report：`.agent/reports/volcengine-ark-provider-report.md`

## 报告路径

- `docs/commercial-ocr-phase-reports/COCR-M20C-real-data-multipage-data-analysis.md`
- `docs/commercial-ocr-phase-reports/COCR-M20C-legacy-pdfserver-chain-contraction.md`
- `docs/commercial-ocr-phase-reports/COCR-M20C-provider-strategy.md`
- `docs/commercial-ocr-phase-reports/COCR-M20C-real-quality-matrix.md`
- `docs/commercial-ocr-phase-reports/COCR-M20C-workbench-real-batch-e2e.md`
- `.agent/reports/data-analysis-real-multipage-hardening-report.md`

## 服务与命令

```bash
# 停止当前 E2E 栈
./scripts/e2e/stop-commercial-ocr-stack.sh

# 重新跑真实批量 E2E
E2E_REAL_BATCH_FIXTURE_ROOT=/home/carry/project2/debug/real-data-data-analysis/batch-tiben-selected/workbench-import-fixtures \
E2E_REAL_BATCH_FIXTURE_NAME=page016-local-group1-import.json \
pnpm exec playwright test e2e/data-analysis-real-batch-workbench.spec.ts --trace=on
```

## 下一轮建议

1. 先拿到一个真实 OCR provider key，再复跑 `page 1 / 6 / 16` 三组，把 `bbox_source` 从 `tesseract_local_ocr` 换成真实 OCR provider。
2. 保持 `qwen_vl -> Ark` 的短超时 hedge，不要把 `mimo_vl` 放回第一备援。
3. 在真实 OCR 成功前，不要尝试把当前 real batch 结果提升为自动审核通过。
