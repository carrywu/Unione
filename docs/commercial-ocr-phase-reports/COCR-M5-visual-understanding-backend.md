# COCR-M5 Visual Understanding Backend Integration

## 1. 本阶段目标

把 visual understanding 从“后续想法”前推进到 commercial OCR pipeline 的真实输出中，但默认只用 mock 结果，不消耗真实 VLM 额度，也不把 VLM 当主 OCR。

## 2. 修改范围

- 新增 `pdf-service/commercial_ocr/visual_understanding.py`
- 新增 `pdf-service/commercial_ocr/config.py`
- 更新 `pdf-service/commercial_ocr/service.py`
- 更新 `pdf-service/commercial_ocr/types.py`
- 更新 `pdf-service/tests/test_commercial_ocr_visual_understanding.py`
- 更新 `pdf-service/tests/test_commercial_ocr_pipeline.py`

## 3. 架构变化

- visual understanding 现在位于 `semantic assembler -> visual understanding -> quality gate`。
- 触发策略改为 selected cases only：
  - shared material / chart / table
  - low confidence OCR
  - missing answer / analysis
  - missing bbox / image
  - provider fallback / provider conflict
- 纯文本高置信题默认跳过 visual understanding，并明确返回 `skipped` 原因。

## 4. 数据结构/API 变化

新增 `visual_understanding` 摘要字段，典型内容包括：

- `provider`
- `triggered`
- `trigger_reasons`
- `visual_grouping_summary`
- `detected_diagram_elements`
- `table_structure_notes`
- `ocr_error_suspicions`
- `material_ownership_assessment`
- `cross_page_suspicion`
- `answer_consistency_check`
- `confidence`
- `warnings`

该字段已进入：

- `CommercialOCRExecution`
- `pdf-service` parse response
- backend review DTO
- admin review candidate payload

## 5. 测试与验证

- `cd pdf-service && ./.venv/bin/python -m pytest tests/test_commercial_ocr_visual_understanding.py -v`
  - `3 passed`
- `cd pdf-service && ./.venv/bin/python -m pytest tests/test_commercial_ocr_pipeline.py tests/test_commercial_ocr_kernel_integration.py -v`
  - `10 passed`
- `cd pdf-service && ./.venv/bin/python -m pytest tests/ -v`
  - `144 passed / 2 skipped`

验证点：

- pure text high-confidence question skips VLM
- 17-20 shared material question triggers visual understanding
- missing chart title warning enters review payload / quality gate

## 6. 证据路径

- [visual_understanding.py](/home/carry/project2/pdf-service/commercial_ocr/visual_understanding.py)
- [service.py](/home/carry/project2/pdf-service/commercial_ocr/service.py)
- [test_commercial_ocr_visual_understanding.py](/home/carry/project2/pdf-service/tests/test_commercial_ocr_visual_understanding.py)
- Playwright review evidence: `debug/e2e-commercial-ocr/20260505-014457/admin/complete-preview-publish/`

## 7. 风险与遗留问题

- 当前仍是 mock visual understanding，不代表真实 VLM 视觉判定能力。
- cross-page material ownership 仍以规则和 OCR 结构为主，真实跨页复杂图表还需要 M5 后续 hardening。
- 真实百度/腾讯 OCR smoke 本轮继续默认 skip。

## 8. 回滚方案

1. `git revert` 本阶段 visual understanding 相关提交。
2. 运行时保持 `COMMERCIAL_OCR_ENABLED=true`，但忽略 `visual_understanding` 字段。
3. 如需彻底回退，设置 `PDF_PARSE_PRIMARY_PROVIDER=local_parser`。

## 9. 是否允许进入下一阶段

`GO_WITH_RISK`
