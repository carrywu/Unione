# COCR-M2 Mock Provider

## 1. 本阶段目标

固化 deterministic commercial OCR fixture，让 `mock_commercial_ocr`、`mock_tencent_question_split`、`mock_tencent_question_split_layout` 在默认无真实 API 的情况下稳定回归 pipeline、fallback 和 semantic/quality 逻辑。

## 2. 修改范围

- 新增 `pdf-service/tests/fixtures/commercial_ocr/`
- 新增 fixture：
  - `baidu_paper_cut_edu_single_page_normalized.json`
  - `tencent_question_split_single_page_normalized.json`
  - `tencent_question_split_layout_single_page_normalized.json`
  - `shared_material_17_20_blocks.json`
  - `incomplete_answer_analysis_blocks.json`
  - `provider_failure_response.json`
- 新增 `pdf-service/commercial_ocr/fixtures.py`
- 更新 `pdf-service/commercial_ocr/adapters.py`
- 更新 `pdf-service/tests/test_commercial_ocr_pipeline.py`

## 3. 架构变化

- mock provider 从“读 page_text 猜 block_type”升级为“读脱敏 fixture 产出统一 `ProviderOCRResult`”。
- layout-only mock provider 不再被当作完整 OCR 成功，而是触发 fallback。
- mock provider 支持通过环境变量控制 `provider_status`、`provider_error`、`provider_latency_ms`。

## 4. 数据结构

fixture 统一最小化为：

- `provider_name`
- `provider_version`
- `provider_status`
- `provider_latency_ms`
- `response` 或 `page_results`
- `warnings`

脱敏规则：

- 不保留真实 key/token/SecretId/SecretKey/access_token
- 不保留大段 base64/raw response
- 只保留测试所需 bbox/text/block_type/reading_order/provider_ref

## 5. 测试与验证

- `cd pdf-service && ./.venv/bin/python -m pytest tests/test_commercial_ocr_pipeline.py -v`
- 结果：通过
- 覆盖：
  - mock provider deterministic
  - mock tencent provider normalized blocks
  - mock layout provider bbox-only fallback
  - provider failure triggers fallback
  - fixture secret scan
  - no-network guarantee

## 6. 证据路径

- [fixtures 目录](/home/carry/project2/pdf-service/tests/fixtures/commercial_ocr)
- [test_commercial_ocr_pipeline.py](/home/carry/project2/pdf-service/tests/test_commercial_ocr_pipeline.py)

## 7. 风险与遗留问题

- fixture 仍是最小版本，不代表真实多页复杂卷面的全部边界。
- mock provider 目前偏向单页 deterministic regression，不替代真实 provider smoke。

## 8. 回滚方案

1. `git revert` 本阶段 mock fixture / adapter 提交。
2. 运行时把 `PDF_PARSE_PRIMARY_PROVIDER=local_parser`。

## 9. 是否允许进入下一阶段

`GO`

