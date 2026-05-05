# COCR-M20C: Workbench Real Batch E2E

## 1. 目标

验证真实多页资料分析 smoke 结果导入 `/workbench` 后：

- `bbox_source` 不会退回 `local_parser`
- 真实 visual context / LLM understanding 能展示
- `needs_human_review` 会阻止“审核通过”
- H5 preview 的 shared material 不丢

## 2. 本轮关键修复

真实 batch E2E 能通过，依赖以下四点已经落地：

1. `pdf-service` `/admin/config` 接受 `commercial_ocr_fixture_root` 和 `mock_commercial_ocr_fixture_name`
2. `e2e/commercial-ocr.helpers.ts` 每次都显式下发 fixture root，避免 helper 状态泄漏
3. real batch fixture export 优先选 `page016` 的 `17-20` group，而不是别的 `1-5` 组
4. 使用 `h5-consistency-preview`，而不是 draft/publish-preview，因为当前质量门正确阻止 draft 创建

## 3. fixture

| 项目 | 值 |
| --- | --- |
| fixture root | `debug/real-data-data-analysis/batch-tiben-selected/workbench-import-fixtures/` |
| fixture name | `page016-local-group1-import.json` |
| question_range | `17-20` |
| `bbox_source` | `tesseract_local_ocr` |
| visual provider | `volcengine_ark_vl` |
| text model | `qwen-plus` |

## 4. Playwright 结果

执行结果：

- `E2E_REAL_BATCH_FIXTURE_ROOT=... E2E_REAL_BATCH_FIXTURE_NAME=page016-local-group1-import.json pnpm exec playwright test e2e/data-analysis-real-batch-workbench.spec.ts --trace=on`：PASS
- `E2E_REAL_BATCH_FIXTURE_ROOT=... E2E_REAL_BATCH_FIXTURE_NAME=page016-local-group1-import.json pnpm exec playwright test e2e/data-analysis-workbench.spec.ts e2e/data-analysis-real-batch-workbench.spec.ts --trace=on`：`3 passed`

主要断言：

- `/workbench?bankId=...&taskId=...` 能直接打开真实 batch 任务
- `data-analysis-material-group` 可见
- `data-analysis-visual-context` 显示 `material_complete`
- `data-analysis-understanding` 显示 `calculation_reasoning`
- `data-analysis-quality-gate` 显示 `需复核` 和 `llm_cannot_solve_question`
- 页面能看到 `bbox_source` 且值为 `tesseract_local_ocr`
- `审核通过` 按钮 disabled
- H5 preview 中 `shared-material-card` 存在且非空
- 页面没有 `undefined` / `null` / `[object Object]`

## 5. 证据

- fixture：`debug/real-data-data-analysis/batch-tiben-selected/workbench-import-fixtures/page016-local-group1-import.json`
- Playwright trace：`test-results/`
- Playwright 截图 / console / final-state：`debug/e2e-commercial-ocr/<timestamp>/admin/data-analysis-real-batch-workbench/`

## 6. 结论

- real batch import 已经能把真实 smoke 摘要稳定带到 workbench / H5
- gate 行为符合预期：材料不完整或 local OCR 风险存在时，review UI 不允许直接通过
- 当前 E2E 证明的是“真实 smoke 结果的审核链路正确”，不是“真实商业 OCR 已经可大规模放行”
