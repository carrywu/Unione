# COCR-M20C: Real Quality Matrix

## 1. 总览

来源：

- `debug/real-data-data-analysis/batch-tiben-selected/quality-matrix.json`

| 指标 | 值 |
| --- | --- |
| `material_groups_total` | 3 |
| `groups_complete` | 3 |
| `groups_incomplete` | 0 |
| `questions_total` | 4 |
| `can_solve_count` | 1 |
| `refuse_count` | 3 |
| `answer_conflict_count` | 0 |
| `high_confidence_count` | 0 |
| `needs_human_review_count` | 4 |
| `blocked_count` | 4 |
| `provider_timeout_count` | 3 |
| `provider_hedge_success_count` | 3 |
| `bbox_from_ocr_provider_rate` | 1.0 |
| `local_parser_fallback_count` | 0 |

## 2. 组级结果

| group | page_no | selected_visual_provider | source_material_complete | needs_human_review | 说明 |
| --- | --- | --- | --- | --- | --- |
| `page001-local-group1` | 1 | `volcengine_ark_vl` | true | false | 材料完整，主要风险是 OCR 错字和另一组题目局部裁切 |
| `page006-local-group1` | 6 | `volcengine_ark_vl` | true | false | 材料完整，但表格 OCR 乱码、题目识别不完整 |
| `page016-local-group1` | 16 | `volcengine_ark_vl` | true | true | 17-20 材料完整，但 local OCR 漏掉题号 16 与表格明细，不能放行 |

说明：

- 这里的 `groups_complete=3` 指视觉材料完整性成立，不等于题目可自动审核通过。
- 真正用于审核通过的仍然是 question-level quality gate。

## 3. 题级结果

| question_no | can_understand_material | can_solve_question | answer | confidence | review_ready | needs_human_review | decision_reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 17 | true | true | `B` | 0.78 | false | true | `needs_human_review` |
| 18 | false | false | 无 | 0.35 | false | true | `needs_human_review` |
| 19 | true | false | 无 | 0.45 | false | true | `needs_human_review` |
| 20 | true | false | 无 | 0.45 | false | true | `needs_human_review` |

## 4. 统一阻断原因

`17-20` 四题都继承了同一组 group-level 阻断：

- `local_ocr_questions_incomplete`
- `llm_cannot_understand_material`
- `llm_cannot_solve_question`
- `calculation_reasoning_missing`

这不是矩阵 bug，而是当前实现刻意把 group 风险上提到 question gate，避免单题侥幸通过。

## 5. 关键观察

1. `17` 题虽然能给出一条低置信计算思路，但因为依赖表格漏识和选项反推，仍必须人工复核。
2. `18` 题是本轮“正确拒答”最典型样本：材料只给 2020 数据和部分同比信息，2019 基期不成立时不应硬算。
3. `19` 和 `20` 题体现了“能理解题意，不等于应该给答案”的 gate 价值。
4. `bbox_from_ocr_provider_rate=1.0` 说明 workbench import 没退回 `local_parser`，但并不代表已经拿到商业 OCR provider 的真实 bbox。

## 6. 结论

- `review_ready=0/4`
- `needs_human_review=4/4`
- 当前矩阵符合 M20C 目标：宁可保守拦截，也不让 local OCR 漏数题被误放行
