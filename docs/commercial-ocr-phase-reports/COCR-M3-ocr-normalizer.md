# COCR-M3 OCR Normalizer

## 1. 本阶段目标

把百度 `paper_cut_edu`、腾讯 `QuestionSplitOCR`、腾讯 `QuestionSplitLayoutOCR`、local parser 的输出统一为 `NormalizedOCRBlock`，并补齐 bbox/provider_ref/raw redaction 校验。

## 2. 修改范围

- 新增 `pdf-service/commercial_ocr/normalizer.py`
- 更新 `pdf-service/commercial_ocr/types.py`
- 更新 `pdf-service/commercial_ocr/adapters.py`
- 新增 `pdf-service/tests/test_commercial_ocr_normalizer.py`

## 3. 架构变化

- provider 不再各自直接拼 block，而是复用 normalizer。
- `NormalizedOCRBlock` 增加：
  - `parent_block_id`
  - `bbox_only`
- local parser 页面也可以投影到相同 block 契约，便于后续 A/B 与 fallback 对照。

## 4. 数据结构

统一 block 字段：

- `block_id`
- `provider_ref`
- `page_no`
- `text`
- `bbox`
- `block_type`
- `confidence`
- `reading_order`
- `parent_block_id`
- `raw`
- `warnings`

支持 block_type：

- `text`
- `title`
- `question_no`
- `stem`
- `option`
- `answer`
- `analysis`
- `material_intro`
- `table`
- `figure`
- `chart`
- `header`
- `footer`
- `bbox_only`
- `unknown`

## 5. 测试与验证

- `cd pdf-service && ./.venv/bin/python -m pytest tests/test_commercial_ocr_normalizer.py tests/test_tencent_ocr_provider.py -v`
- 结果：通过
- 覆盖：
  - 百度 fixture normalize
  - 腾讯 QuestionSplitOCR fixture normalize
  - 腾讯 QuestionSplitLayoutOCR fixture normalize
  - malformed bbox warning/reject
  - missing confidence warning
  - provider_ref missing reject
  - raw redaction

## 6. 证据路径

- [normalizer.py](/home/carry/project2/pdf-service/commercial_ocr/normalizer.py)
- [test_commercial_ocr_normalizer.py](/home/carry/project2/pdf-service/tests/test_commercial_ocr_normalizer.py)

## 7. 风险与遗留问题

- 腾讯真实返回字段仍可能有更多变体，当前主要按官方文档示例和 mock fixture 覆盖。
- `bbox_only` 结果只能做 overlay/fallback 证据，不能直接视为完整 OCR。

## 8. 回滚方案

1. `git revert` 本阶段 normalizer 提交。
2. 临时恢复 provider 内联 normalize，但不建议长期保留。

## 9. 是否允许进入下一阶段

`GO_WITH_RISK`

