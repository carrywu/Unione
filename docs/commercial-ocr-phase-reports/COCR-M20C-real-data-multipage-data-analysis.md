# COCR-M20C: Real Data Multi-Page Data Analysis Hardening

## 1. Baseline

- 阶段名: `COCR-M20C: Real Data Multi-Page Data Analysis Hardening`
- 分支: `mimo`
- 本轮开始时 commit: `f0ad797812f7177387325521448da3ae22c8c86a`
- baseline tag: `pre-data-analysis-ocr-api-first-20260505-221735`
- 结论: `GO_WITH_RISK`

## 2. 真实输入与 key 状态

| 项目 | 状态 |
| --- | --- |
| 真实题本 | `题本/题本篇.pdf` |
| `DASHSCOPE_API_KEY` | yes |
| `ARK_API_KEY` | yes |
| `MIMO_API_KEY` | yes |
| `BAIDU_API_KEY` / `BAIDU_SECRET_KEY` | no |
| `TENCENT_SECRET_ID` / `TENCENT_SECRET_KEY` | no |

约束执行情况：

- 未提交 `.env`
- 未提交真实题本/答本
- 未提交 raw provider response
- 报告只记录 yes/no/redacted 和 debug 路径

## 3. 候选页发现

来源：

- 候选全集：`debug/real-data-data-analysis/discover-tiben-local-1-20/candidate-pages.json`
- 选中页：`debug/real-data-data-analysis/discover-tiben-local-1-20/candidate-pages-selected.json`

结果：

- 扫描页数：`20`
- 本地 OCR 命中的候选页：`12`
- 为限量真实 smoke 选中的起始页：`3`
- 实际跑页：`1`、`6`、`16`

| page_no | likely_question_range | provider | status | 备注 |
| --- | --- | --- | --- | --- |
| 1 | `1-5` | `tesseract_local_ocr` | `matched_local_ocr` | 纯文字材料，材料完整 |
| 6 | `1-5` | `tesseract_local_ocr` | `matched_local_ocr` | 图表材料，命中表/图关键词 |
| 16 | `16-20` | `tesseract_local_ocr` | `matched_local_ocr` | 17-20 共用材料，后续 workbench import 选这组 |

## 4. 多页 OCR smoke

来源：

- `debug/real-data-data-analysis/batch-tiben-selected/batch-ocr-summary.json`

执行策略：

- 期望 OCR providers：`baidu_paper_cut_edu`、`tencent_question_split`、`tencent_question_split_layout`
- 真实 key 缺失时不伪造成功，显式记为 `skipped_unavailable`
- 为了继续完成多页真实资料分析验证，落到 `tesseract_local_ocr`

结果摘要：

- 商业 OCR provider 调用：`9` 次均 `skipped_unavailable`
- 本地 OCR fallback group：`3`
- `local_parser_fallback_count=0`
- `bbox_from_ocr_provider_rate=1.0`
- workbench import 的 `bbox_source=tesseract_local_ocr`，不是 `local_parser`

| page_no | expected_range | selected_provider | status | question_count | source_page_span | warnings |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `1-5` | `tesseract_local_ocr` | `ok_local_fallback` | 5 | `1-2` | 无 |
| 6 | `1-5` | `tesseract_local_ocr` | `ok_local_fallback` | 4 | `6-7` | `local_ocr_missing_questions:5` |
| 16 | `16-20` | `tesseract_local_ocr` | `ok_local_fallback` | 4 | `16-18` | `local_ocr_missing_questions:16` |

结论：

- 本轮没有真实百度/腾讯 OCR 证据，因此不宣称 OCR provider 排序结论。
- `tesseract_local_ocr` 只作为真实题本候选发现、材料分组和 workbench import 的硬化兜底，不冒充商业 OCR 成功。

## 5. 多页 VLM visual context

来源：

- `debug/real-data-data-analysis/batch-tiben-selected/batch-visual-context-summary.json`

策略：

- preferred: `qwen_vl`
- per-provider soft timeout: `12s`
- hedge/fallback: `volcengine_ark_vl`
- `mimo_vl` 不参与第一备援

真实结果：

- `qwen_vl` timeout：`3/3`
- Ark hedge 成功：`3/3`
- selected provider：全部为 `volcengine_ark_vl`
- selected model：全部为 `doubao-seed-2-0-lite-260215`
- `source_material_complete=true`：`3/3`

| group | page_no | qwen_vl | ark | completeness | notable warnings |
| --- | --- | --- | --- | --- | --- |
| `page001-local-group1` | 1 | timeout at `12s` | success | complete | 下半页 6-10 题目存在裁切；OCR 把时间/百分比识别错字 |
| `page006-local-group1` | 6 | timeout at `12s` | success | complete | 表格数字 OCR 乱码；第 5 题 OCR 不完整 |
| `page016-local-group1` | 16 | timeout at `12s` | success | complete | 表格类别数据 OCR 漏识；`28.4%` 识别成 `28. 4锐` |

关键结论：

- provider health 的 toy smoke 不能代表真实资料分析页稳定性。
- 对资料分析页，`qwen_vl` 更适合当“先试一次的慢 provider”，不适合单独承担成功率。
- Ark 在真实多页资料分析里证明了 hedge 价值，但它自身仍有 endpoint-id `403` 和 local data-url health timeout 风险，因此应保留模型名 fallback 和短链路调用。

## 6. 多题文本 LLM understanding

来源：

- `debug/real-data-data-analysis/batch-tiben-selected/batch-llm-understanding-summary.json`

执行范围：

- 材料组：`page016-local-group1`
- 题号：`17-20`
- provider/model：`qwen_text / qwen-plus`

| question_no | can_understand_material | can_solve_question | answer_suggestion | confidence | needs_human_review | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| 17 | true | true | `B` | `0.78` | true | 给出计算链路，但依赖缺失表格数据和选项反推，只能低置信尝试 |
| 18 | false | false | 无 | `0.35` | true | 正确拒答，指出缺少 2019 基期和表格完整数据 |
| 19 | true | false | 无 | `0.45` | true | 能理解题意，但反推 2019 占比依赖超纲假设，正确不放行 |
| 20 | true | false | 无 | `0.45` | true | 能做局部计算，但关键表格缺失导致不能唯一判错项 |

结论：

- `qwen-plus` 在本轮更适合做“拒答正确性”和“低置信解释”验证。
- 本轮没有任何题达到高置信放行标准。
- `17` 题虽然给出答案建议，但仍被 quality gate 正确挡住。

## 7. Workbench 导入与验收入口

来源：

- 导入 fixture：`debug/real-data-data-analysis/batch-tiben-selected/workbench-import-fixtures/page016-local-group1-import.json`

导入摘要：

- `question_range=[17,18,19,20]`
- `bbox_source=tesseract_local_ocr`
- `visual_provider=volcengine_ark_vl`
- `text_model=qwen-plus`
- `needs_human_review=true`

这次导入优先选 `page016-local-group1`，原因是它与既有资料分析 17-20 workbench/H5 模板一致，不会把真实多页 smoke 变成和 UI 问题号不一致的假样本。

## 8. 验证

本轮与衔接验证：

- `cd pdf-service && ./.venv/bin/python -m py_compile ...`：PASS
- `cd pdf-service && ./.venv/bin/python -m pytest tests/test_commercial_ocr_pipeline.py tests/test_data_analysis_real_smoke_scripts.py -q`：`13 passed`
- `cd pdf-service && ./.venv/bin/python -m pytest tests/ -q`：`158 passed, 2 skipped`
- `cd backend && pnpm exec tsc -p tsconfig.build.json --noEmit`：PASS
- `cd backend && pnpm build`：PASS
- `cd admin-web && pnpm exec vue-tsc --noEmit`：PASS
- `cd admin-web && pnpm build`：PASS
- `cd h5-web && pnpm build`：PASS
- `pnpm exec playwright test e2e/data-analysis-workbench.spec.ts e2e/data-analysis-real-batch-workbench.spec.ts --trace=on`：`3 passed`

## 9. 风险与下一步

当前风险：

- 真实百度/腾讯 OCR key 缺失，商业 OCR 多页结论仍未建立
- `qwen_vl` toy smoke 健康，但真实资料分析页 `3/3` timeout
- Ark 在真实批量里表现更好，但 endpoint-id 和 local data-url health 仍有单独风险
- `tesseract_local_ocr` 只能说明真实材料组发现和 UI 导入没问题，不能替代商业 OCR 验收

建议：

1. 拿到一个真实 OCR provider key 后，复跑 `page 1 / 6 / 16` 三组，优先证明 `bbox_source` 从 `tesseract_local_ocr` 切到真实 OCR provider。
2. 保留 `qwen_vl` 先试，但把真实资料分析 visual 调用的 provider timeout 固定在短窗口。
3. 扩大样本前，继续以 `needs_human_review` 为硬门，不要让当前 local OCR 组进入审核通过。
