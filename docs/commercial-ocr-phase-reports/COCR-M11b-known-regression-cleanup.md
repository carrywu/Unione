# COCR-M11b Known Regression Cleanup

## 1. 本阶段目标

清掉上轮遗留的 3 条既有回归，让 `pdf-service` 全量 pytest 回到全绿。

## 2. 修改范围

- 更新 `pdf-service/ai_client.py`
- 更新 `pdf-service/tools/visual_api_smoke.py`

## 3. 架构变化

- Ark provider config 现在会在 endpoint id 之外保留默认 model name 候选，provider health smoke 可以验证 endpoint fallback。
- visual smoke retry-only 模式会把“未重试但有效缓存仍被复用”的页面显式记为 retained cache hits，summary / review manifest 与真实行为保持一致。
- qwen soft-timeout hedge 结果不会再被晚到的 primary result 覆盖。

## 4. 数据结构/API 变化

影响字段：

- `candidate_models_tested`
- `successful_model`
- `successful_model_type`
- `cache_hits`
- `cache_misses`
- `retried_pages`

## 5. 测试与验证

- `cd pdf-service && ./.venv/bin/python -m pytest tests/test_provider_health_report.py tests/test_visual_api_smoke_tool.py::VisualApiSmokeToolTest::test_retry_failed_pages_only_bypasses_failed_cache_and_merges_manifest -q`
  - `4 passed`
- `cd pdf-service && ./.venv/bin/python -m pytest tests/ -v`
  - `144 passed / 2 skipped`

已修复回归：

- `test_ark_provider_smoke_classifies_auth_error`
- `test_ark_provider_smoke_falls_back_from_endpoint_id_to_default_model`
- `test_retry_failed_pages_only_bypasses_failed_cache_and_merges_manifest`

## 6. 证据路径

- [ai_client.py](/home/carry/project2/pdf-service/ai_client.py)
- [visual_api_smoke.py](/home/carry/project2/pdf-service/tools/visual_api_smoke.py)
- [test_provider_health_report.py](/home/carry/project2/pdf-service/tests/test_provider_health_report.py)
- [test_visual_api_smoke_tool.py](/home/carry/project2/pdf-service/tests/test_visual_api_smoke_tool.py)

## 7. 风险与遗留问题

- 仍有大量 warning 输出：
  - Pillow `getdata` deprecation
  - Pydantic `.dict()` deprecation
- 这两类 warning 不阻断本轮交付，但应在后续常规维护中清理。

## 8. 回滚方案

1. `git revert` 本阶段 regression cleanup 提交。
2. 允许重新出现已知旧失败，但不得影响主链商业 OCR 结果正确性。

## 9. 是否允许进入下一阶段

`GO`
