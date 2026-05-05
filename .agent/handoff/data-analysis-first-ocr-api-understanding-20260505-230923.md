# COCR-M20A Handoff

## 当前分支

- `mimo`

## 当前 commit

- `02b02bb`
- 说明: 这是 docs/handoff 提交前的实现头，包含资料分析主链路代码、admin/workbench、E2E。最终 push 后的最新 HEAD 见 CLI 汇总。

## baseline tag

- `pre-data-analysis-ocr-api-first-20260505-221735`
- push 状态: 已 push

## 已完成内容

- OCR API First 资料分析 17-20 主链路接入
- `MaterialGroup` 扩展为 `data_analysis_material`，保留 `table_blocks` / `chart_blocks`
- `DataAnalysisVisualContext` / `DataAnalysisUnderstandingResult` / `DataAnalysisQualityGate` 已落地
- workbench 展示 shared material、VLM visual context、LLM calculation reasoning、quality gate
- `/banks` 主入口已切到 `/workbench`
- 旧 `/banks/:bankId/questions` 已 redirect 到 `/workbench`
- workbench header 文案已切换为 `待审核 / 审核通过 / 需复核 / 打开 H5 预览 / 发布到题库`
- Playwright 覆盖 admin workbench + H5 shared material + conflict review

## 未完成内容

- 真实 `qwen-vl` / `doubao-vl` visual context smoke
- 真实 `deepseek` / `qwen_text` / `mimo_text` understanding smoke
- 非资料分析题型扩展
- 旧 `page_understanding` / `semantic_groups` / `recrop_plan` 清理决策

## 测试结果

- `./scripts/e2e/start-commercial-ocr-stack.sh`: PASS
- `cd pdf-service && ./.venv/bin/python -m pytest tests/test_commercial_ocr_pipeline.py tests/test_commercial_ocr_quality_gate.py tests/test_commercial_ocr_visual_understanding.py tests/test_commercial_ocr_semantic_assembler.py -q`: `21 passed`
- `cd backend && node --require ts-node/register --require tsconfig-paths/register test/pdf-review-workflow.test.ts`: PASS
- `cd backend && pnpm build`: PASS
- `cd admin-web && pnpm build`: PASS
- `cd h5-web && pnpm build`: PASS
- `pnpm exec playwright test e2e/ --trace=on`: `9 passed`
- `cd backend && pnpm test`: skipped，原因是 `backend/package.json` 无 `test` script

## Playwright 证据路径

- `debug/e2e-commercial-ocr/2026-05-05T15-03-11-354Z/`
- `test-results/`

## 服务启动/停止命令

```bash
# 启动
bash -lc './scripts/e2e/start-commercial-ocr-stack.sh; while true; do sleep 3600; done'

# 单独跑 Playwright
pnpm exec playwright test e2e/ --trace=on

# 停止
./scripts/e2e/stop-commercial-ocr-stack.sh
```

## 报告路径

- `docs/commercial-ocr-phase-reports/COCR-M20A-data-analysis-first.md`
- `.agent/reports/data-analysis-first-ocr-api-understanding-report.md`

## 下一轮 resume prompt

继续在 `/home/carry/project2` 的 `mimo` 分支推进 COCR。保持 OCR API First，不扩全题型。优先做真实 `qwen-vl` / `doubao-vl` visual context smoke，再决定是否把资料分析 mock understanding 切到真实 text model；随后再评估图形推理或言语理解的下一条单题型闭环。不要把 `page_understanding`/`semantic_groups` 旧链路重新拉回主流程。
