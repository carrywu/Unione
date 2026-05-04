# Commercial OCR Overnight Handoff

## 当前分支

- `main`

## 当前 commit

- code baseline at handoff generation: `d7b26a0`

## 已完成 story

- US-001 merge main safely
- US-002 provider baseline
- US-003 deterministic mock fixtures and tests
- US-004 OCR normalizer
- US-005 shared-material data model
- US-006 semantic assembler baseline
- US-008 parse quality gate
- US-009 provider trace/fallback evidence
- US-011 reports/eval assets
- US-012 git hygiene

## 未完成 story

- US-007 visual understanding assist layer
- US-010 admin review / publish hard gate

## 测试结果

- `cd pdf-service && ./.venv/bin/python -m pytest tests/test_commercial_ocr_pipeline.py tests/test_commercial_ocr_kernel_integration.py -v`
  - `8 passed`
- `cd pdf-service && ./.venv/bin/python -m pytest tests/test_commercial_ocr_pipeline.py tests/test_commercial_ocr_kernel_integration.py tests/test_commercial_ocr_normalizer.py tests/test_commercial_ocr_semantic_assembler.py tests/test_commercial_ocr_quality_gate.py tests/test_tencent_ocr_provider.py -v`
  - `27 passed / 1 skipped`
- `cd pdf-service && ./.venv/bin/python -m pytest tests/ -v`
  - `136 passed / 3 failed / 2 skipped`
- `cd backend && pnpm build`
  - passed
- `cd admin-web && pnpm build`
  - passed

## known regression

- `tests/test_provider_health_report.py::ProviderHealthReportTest::test_ark_provider_smoke_classifies_auth_error`
- `tests/test_provider_health_report.py::ProviderHealthReportTest::test_ark_provider_smoke_falls_back_from_endpoint_id_to_default_model`
- `tests/test_visual_api_smoke_tool.py::VisualApiSmokeToolTest::test_retry_failed_pages_only_bypasses_failed_cache_and_merges_manifest`

## 下一步命令

```bash
git checkout main
git pull --ff-only origin main
cd /home/carry/project2/pdf-service
./.venv/bin/python -m pytest tests/test_provider_health_report.py tests/test_visual_api_smoke_tool.py -v
./.venv/bin/python scripts/eval_commercial_ocr.py
```

## resume prompt

继续在 `/home/carry/project2` 的 `main` 分支推进 commercial OCR 主线。已完成 M2/M3/M4/M7/M8-pre，当前 code baseline 为 `d7b26a0`，仅剩 3 条既有 pytest 回归。先处理 `test_provider_health_report` 和 `test_visual_api_smoke_tool`，然后推进 COCR-M5 visual understanding、M8 real adapter hardening、M9 review UI / publish hard gate。真实腾讯/百度 API 默认关闭，不要写入任何 SecretId/SecretKey/API key/token；百度 Key 曾在对话中暴露，报告里继续提醒轮换。

