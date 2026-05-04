# COCR-M4 Semantic Assembler

## 1. 本阶段目标

实现 commercial OCR 侧 semantic assembler，把 OCR blocks 编排成 `material_groups`、`question_groups`、`normalized_questions`，重点覆盖 “根据以下资料，回答17-20题”。

## 2. 修改范围

- 新增 `pdf-service/commercial_ocr/semantic_assembler.py`
- 更新 `pdf-service/commercial_ocr/types.py`
- 更新 `pdf-service/commercial_ocr/service.py`
- 新增 `pdf-service/tests/test_commercial_ocr_semantic_assembler.py`

## 3. 架构变化

- provider result 成功后，先进入 semantic assembler，再进入 quality gate。
- assembler 输出进入 `CommercialOCRExecution.semantic_assembly`，随 parse stats/debug 一起暴露。
- 不替换现有 parser kernel question builder；先作为 commercial OCR sidecar 结构化层落地。

## 4. 数据结构

核心结构：

- `MaterialGroup`
  - `material_id`
  - `group_type`
  - `question_range`
  - `shared_stem`
  - `shared_assets`
  - `source_page_span`
  - `source_blocks`
  - `grouping_evidence`
  - `grouping_confidence`
  - `needs_human_review`
  - `warnings`
- `NormalizedQuestion`
  - `question_id`
  - `question_no`
  - `material_id`
  - `parent_group_id`
  - `group_type`
  - `question_role`
  - `question_range`
  - `shared_stem_ref`
  - `local_stem`
  - `full_stem`
  - `options`
  - `answer`
  - `analysis`
  - `category`
  - `bbox`
  - `provider`
  - `provider_trace_ref`
  - `missing_fields`
  - `grouping_evidence`
  - `grouping_confidence`

## 5. 测试与验证

- `cd pdf-service && ./.venv/bin/python -m pytest tests/test_commercial_ocr_semantic_assembler.py -v`
- 结果：通过
- 覆盖：
  - 17-20 -> 1 material group + 4 child questions
  - 17/18/19/20 共享同一 `material_id`
  - `local_stem` 不重复 `shared_stem`
  - `full_stem` 可组合 `shared_stem + local_stem`
  - `shared_assets` 不只挂第17题
  - ambiguous grouping -> `needs_human_review=true`
  - standalone remains standalone
  - layout-only result 不强行变完整题目

## 6. 证据路径

- [semantic_assembler.py](/home/carry/project2/pdf-service/commercial_ocr/semantic_assembler.py)
- [shared_material_17_20_blocks.json](/home/carry/project2/pdf-service/tests/fixtures/commercial_ocr/shared_material_17_20_blocks.json)
- [test_commercial_ocr_semantic_assembler.py](/home/carry/project2/pdf-service/tests/test_commercial_ocr_semantic_assembler.py)
- mock-only eval：`/home/carry/project2/pdf-service/debug/commercial-ocr-eval/20260504-233354/evaluation.json`

## 7. 风险与遗留问题

- 当前是 OCR-block heuristics assembler，还没有接入独立 VLM summary。
- 跨页 shared material 目前只做页跨度预留，复杂跨页图表仍需 M5 支撑。

## 8. 回滚方案

1. `git revert` semantic assembler 提交。
2. 运行时仅保留 `provider_result`，忽略 `semantic_assembly` summary。

## 9. 是否允许进入下一阶段

`GO_WITH_RISK`

