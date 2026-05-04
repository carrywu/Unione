# COCR-M8 Tencent OCR Adapter

## 1. 本阶段目标

加入腾讯云 OCR provider：

- `tencent_question_split`
- `tencent_question_split_layout`

并默认关闭真实调用，只在显式 smoke flag 打开且密钥完整时允许 1 页调用。

## 2. 修改范围

- 新增 `pdf-service/commercial_ocr/tencent_provider.py`
- 更新 `pdf-service/commercial_ocr/adapters.py`
- 更新 `pdf-service/commercial_ocr/service.py`
- 更新 `pdf-service/requirements.txt`
- 更新 `pdf-service/.env.example`
- 更新 `backend/.env.example`
- 更新 `pdf-service/main.py`
- 更新 `pdf-service/monitor.py`
- 新增 `pdf-service/tests/test_tencent_ocr_provider.py`

## 3. 架构变化

- 腾讯 provider 采用官方 Python SDK `tencentcloud-sdk-python==3.1.89`。
- `QuestionSplitOCR` 与 `QuestionSplitLayoutOCR` 分开建 provider。
- `QuestionSplitLayoutOCR` 只作为 bbox/layout 证据，不再伪装为完整 OCR 成功。
- provider 输出统一走 normalizer -> semantic assembler -> quality gate。

## 4. 数据结构

provider 输出统一为 `ProviderOCRResult`：

- `provider_name`
- `provider_version`
- `source_document_id`
- `task_id`
- `page_results`
- `raw_response_ref`
- `provider_latency_ms`
- `provider_status`
- `provider_error`
- `fallback_used`
- `warnings`

Tencent env vars：

- `TENCENT_SECRET_ID`
- `TENCENT_SECRET_KEY`
- `TENCENT_REGION`
- `TENCENT_OCR_ENDPOINT=https://ocr.tencentcloudapi.com`
- `TENCENT_OCR_VERSION=2018-11-19`
- `TENCENT_OCR_TIMEOUT_MS=60000`
- `TENCENT_OCR_USE_NEW_MODEL=false`
- `TENCENT_OCR_ENABLE_IMAGE_CROP=false`
- `TENCENT_OCR_ENABLE_ONLY_DETECT_BORDER=false`
- `TENCENT_OCR_REAL_SMOKE=false`

## 5. 测试与验证

- `cd pdf-service && ./.venv/bin/python -m pytest tests/test_tencent_ocr_provider.py tests/test_commercial_ocr_normalizer.py -v`
- 结果：通过
- 默认 smoke：`SKIPPED`
- 只有当以下条件同时满足时才允许真实腾讯调用：
  - `TENCENT_SECRET_ID` 存在
  - `TENCENT_SECRET_KEY` 存在
  - `TENCENT_OCR_REAL_SMOKE=true`
  - 请求页数必须为 1

## 6. 证据路径

- [tencent_provider.py](/home/carry/project2/pdf-service/commercial_ocr/tencent_provider.py)
- [test_tencent_ocr_provider.py](/home/carry/project2/pdf-service/tests/test_tencent_ocr_provider.py)
- 腾讯官方文档：
  - `QuestionSplitOCR`: https://cloud.tencent.com/document/product/866/115930
  - `QuestionSplitLayoutOCR`: https://cloud.tencent.com/document/product/866/124456

## 7. 风险与遗留问题

- 当前真实腾讯 provider 仍处于 M8-pre，只允许 1 页 smoke，避免误消耗额度。
- `UseNewModel=true` 对 layout-only 可用于高精度外框，但不适合作为完整结构化结果。
- 真实腾讯 SecretId/SecretKey 绝对不能写入代码、fixture、debug、报告。
- 用户此前在对话中明文暴露过百度 Key，必须尽快轮换。

## 8. 回滚方案

1. `git revert` 腾讯 adapter 提交。
2. 运行时回退：
   - `PDF_PARSE_PRIMARY_PROVIDER=mock_commercial_ocr`
   - `PDF_PARSE_FALLBACK_PROVIDERS=local_parser,mock_commercial_ocr`
   - `TENCENT_OCR_REAL_SMOKE=false`

## 9. 是否允许进入下一阶段

`GO_WITH_RISK`

