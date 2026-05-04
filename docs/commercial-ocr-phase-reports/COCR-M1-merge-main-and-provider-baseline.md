# COCR-M1 Merge Main And Provider Baseline

## 1. 本阶段目标

在 `main` 上完成商业 OCR provider baseline：统一 provider interface、mock provider、百度 `paper_cut_edu` adapter、腾讯 stub、fallback orchestrator，并把结果接入 scanned question book 的 parser 入口。

## 2. 修改范围

新增/更新的核心文件：

- `pdf-service/commercial_ocr/__init__.py`
- `pdf-service/commercial_ocr/types.py`
- `pdf-service/commercial_ocr/adapters.py`
- `pdf-service/commercial_ocr/service.py`
- `pdf-service/parser_kernel/adapter.py`
- `pdf-service/pipeline.py`
- `pdf-service/models.py`
- `pdf-service/monitor.py`
- `pdf-service/main.py`
- `pdf-service/.env.example`
- `backend/.env.example`
- `pdf-service/tests/test_commercial_ocr_pipeline.py`
- `pdf-service/tests/test_commercial_ocr_kernel_integration.py`

## 3. 架构变化

新主链入口：

1. `parse_extractor_with_kernel`
2. 若 `pdf_kind == scanned_question_book`，先执行 `run_commercial_ocr_pipeline`
3. provider 顺序由 `PDF_PARSE_PRIMARY_PROVIDER` + `PDF_PARSE_FALLBACK_PROVIDERS` 决定
4. 成功时把 provider 结果归一化为 `PageContent`
5. 失败或不可用时保留 `local_parser` 旧链路
6. 在 `ParseStats.commercial_ocr` 中保留 attempted providers、primary error、fallback_used、raw_response_ref

本阶段仍未实现：

- semantic assembler 真正把材料组和题组重新编排
- visual understanding 作为独立 VLM 层
- quality gate 阻断 publish

## 4. 数据结构

新增统一契约位于 `pdf-service/commercial_ocr/types.py`：

- `ProviderOCRResult`
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
- `NormalizedOCRBlock`
  - `block_id`
  - `provider_ref`
  - `page_no`
  - `text`
  - `bbox`
  - `block_type`
  - `confidence`
  - `reading_order`
  - `raw`
  - `warnings`
- 预留未来结构：
  - `MaterialGroup`
  - `NormalizedQuestion`
  - `ParseQualityGateResult`

`block_type` 已支持：

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
- `unknown`

## 5. 测试与验证

新增测试：

- `cd pdf-service && ./.venv/bin/python -m pytest tests/test_commercial_ocr_pipeline.py tests/test_commercial_ocr_kernel_integration.py -v`
  - 结果：`6 passed`
  - 覆盖：
    - provider selection
    - fallback order
    - missing keys skip real API
    - mock provider 不触发真实 HTTP
    - local parser fallback 保留
    - 百度字段映射到统一 block schema

继承 M0 的必跑命令结果：

- `cd backend && pnpm test`
  - 失败：无 `test` script
- `cd admin-web && pnpm build`
  - 通过
- `cd pdf-service && python3 -m pytest tests/ -v`
  - 失败：系统 Python 缺依赖

补充验证：

- `cd backend && pnpm build`
  - 结果：通过
- `cd pdf-service && ./.venv/bin/python -m pytest tests/ -v`
  - 结果：`115 passed / 3 failed / 1 skipped`
  - 失败项：
    - `tests/test_provider_health_report.py::ProviderHealthReportTest::test_ark_provider_smoke_classifies_auth_error`
    - `tests/test_provider_health_report.py::ProviderHealthReportTest::test_ark_provider_smoke_falls_back_from_endpoint_id_to_default_model`
    - `tests/test_visual_api_smoke_tool.py::VisualApiSmokeToolTest::test_retry_failed_pages_only_bypasses_failed_cache_and_merges_manifest`
  - 判断：这三项属于既有 provider health / visual smoke 缓存回归，新增 commercial OCR baseline 测试未失败

## 6. 证据路径

- 新 provider 测试：`/home/carry/project2/pdf-service/tests/test_commercial_ocr_pipeline.py`
- local parser fallback 集成测试：`/home/carry/project2/pdf-service/tests/test_commercial_ocr_kernel_integration.py`
- COCR handoff：`/home/carry/project2/.agent/handoff/README.md`
- Agent phase 报告：`/home/carry/project2/.agent/reports/commercial-ocr-main-handoff.md`

百度样例识别结论：

- provider 类型：百度 OCR `paper_cut_edu`
- endpoint：`https://aip.baidubce.com/rest/2.0/ocr/v1/paper_cut_edu`
- auth：AK/SK 换 `access_token`，或直接注入 `BAIDU_ACCESS_TOKEN`
- 真实 smoke：成功，基于 `backend/sample-题本篇-3-7.pdf` 首页返回 33 个 blocks
- 真实 response 顶层字段：`log_id`、`qus_figure`、`qus_result`、`qus_result_num`
- 真实题目字段：`qus_location`、`qus_probability`、`qus_type`、`qus_element`
- 真实元素字段：`elem_type`、`elem_location`、`elem_probability`、`elem_word`
- 样例文件：本地 `rest2.0ocrv1paper_cut_edu.js`
- 安全处置：样例文件保留为本地参考，不纳入 Git；业务 adapter 只从环境变量读取密钥

## 7. 风险与遗留问题

- 百度 adapter 目前按“逐页图片”方式调用，未验证真实 PDF 大批量成本与吞吐
- 真实 `paper_cut_edu` response 细节来自官方文档和兼容字段推断，仍需用真实 key/响应包验证
- 腾讯 provider 当前仅 stub，占位 fallback，不可用于生产
- `commercial_ocr` 结果目前只进入 `PageContent` 与 `ParseStats`，尚未完成 semantic assembler
- `17-20` 共用材料题的数据模型已预留，但还未完成端到端编排验收
- quality gate 仅定义结构，未阻断 publish

## 8. 回滚方案

1. `git revert` 本阶段 provider baseline 提交
2. 运行时回滚：
   - `COMMERCIAL_OCR_ENABLED=false`
   - 或 `PDF_PARSE_PRIMARY_PROVIDER=local_parser`
3. 保留 `PDF_PARSE_FALLBACK_PROVIDERS=local_parser`，确保旧链持续可用

## 9. 是否允许进入下一阶段

`GO_WITH_RISK`

允许进入 M2/M3，但前提是：

- 用真实百度 key 跑一份 provider trace
- 把 semantic assembler 与 material/question group 真正接起来
- 把 quality gate 变成入库门禁，而不是文档约定
