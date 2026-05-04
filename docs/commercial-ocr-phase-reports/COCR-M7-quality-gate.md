# COCR-M7 Quality Gate

## 1. 本阶段目标

把 “question_count 看起来对了就算成功” 改成结构化质量门禁，明确识别 answer 缺失、analysis=unknown、bbox 缺失、layout-only、shared material 冲突、fallback 等不应直接 review-ready 的场景。

## 2. 修改范围

- 新增 `pdf-service/commercial_ocr/quality_gate.py`
- 更新 `pdf-service/commercial_ocr/service.py`
- 新增 `pdf-service/tests/test_commercial_ocr_quality_gate.py`

## 3. 架构变化

- quality gate 现在在 commercial OCR execution 成功后立即计算。
- 结果进入 `CommercialOCRExecution.quality_gate` 和 parse stats summary。
- 本阶段先作为 review/publish 前的结构化信号，不直接改写现有业务 publish 逻辑。

## 4. 数据结构

`ParseQualityGateResult`：

- `extraction_complete`
- `ocr_complete`
- `visual_assets_preserved`
- `semantic_consistent`
- `reasoning_verified`
- `review_ready`
- `extracted_but_incomplete`
- `needs_human_review`
- `blocking_reasons`
- `warnings`
- `per_question_status`

## 5. 测试与验证

- `cd pdf-service && ./.venv/bin/python -m pytest tests/test_commercial_ocr_quality_gate.py -v`
- 结果：通过
- 覆盖：
  - 20/20 extracted but answer=null -> incomplete
  - analysis=unknown -> incomplete
  - valid shared material group -> semantic consistent
  - missing shared assets -> visual assets false
  - provider fallback -> needs human review
  - layout-only result -> review ready false
  - complete standalone -> review ready true

## 6. 证据路径

- [quality_gate.py](/home/carry/project2/pdf-service/commercial_ocr/quality_gate.py)
- [incomplete_answer_analysis_blocks.json](/home/carry/project2/pdf-service/tests/fixtures/commercial_ocr/incomplete_answer_analysis_blocks.json)
- [test_commercial_ocr_quality_gate.py](/home/carry/project2/pdf-service/tests/test_commercial_ocr_quality_gate.py)

## 7. 风险与遗留问题

- `reasoning_verified` 目前仍固定为 `false` + `reasoning_verification_skipped`，因为还没有独立 VLM/LLM consistency verifier。
- publish hard gate 还没接业务链，当前仍主要用于 stats/debug/handoff。

## 8. 回滚方案

1. `git revert` quality gate 提交。
2. 运行时忽略 `quality_gate`，仅保留 `semantic_assembly` summary。

## 9. 是否允许进入下一阶段

`GO_WITH_RISK`

