# COCR-M12 Overnight Final Report

## 1. 本阶段目标

完成 commercial OCR mock-first 全链路夜间托管交付：backend 接线、admin review、publish gate、h5 preview、Playwright 证据、known regression 清理、handoff 与报告归档。

## 2. 修改范围

- backend commercial OCR DTO / publish gate / config wiring
- pdf-service visual understanding mock integration
- admin-web review UI 与 publish gate 展示
- h5-web shared material 渲染与友好交互
- root Playwright E2E harness
- phase reports / PRD / progress / handoff

## 3. 架构变化

当前可运行闭环：

`PDF 上传 -> backend parse task -> pdf-service commercial OCR/mock -> OCR normalizer -> semantic assembler -> visual understanding mock -> quality gate -> admin review -> preview publish -> h5 preview`

关键约束保持：

- local parser 保留为 fallback
- M5A / M5B 原逻辑未被绕过
- review_ready=false 不可入卷
- shared material 不再被拆成孤立题

## 4. 数据结构/API 变化

业务链路现已贯通以下关键信息：

- `provider_result`
- `material_groups`
- `question_groups`
- `normalized_questions`
- `quality_gate`
- `visual_understanding`
- `provider_trace_ref`
- `fallback_used`
- `grouping_evidence`

## 5. 测试与验证

- `cd pdf-service && ./.venv/bin/python -m pytest tests/test_commercial_ocr_pipeline.py tests/test_commercial_ocr_kernel_integration.py -v`
  - `10 passed`
- `cd pdf-service && ./.venv/bin/python -m pytest tests/test_commercial_ocr_semantic_assembler.py tests/test_commercial_ocr_quality_gate.py tests/test_tencent_ocr_provider.py tests/test_commercial_ocr_visual_understanding.py -v`
  - `16 passed / 1 skipped`
- `cd pdf-service && ./.venv/bin/python -m pytest tests/ -v`
  - `144 passed / 2 skipped`
- `cd backend && pnpm build`
  - passed
- `cd backend && pnpm exec ts-node -r tsconfig-paths/register test/pdf-review-workflow.test.ts`
  - passed
- `cd admin-web && pnpm build`
  - passed
- `cd h5-web && pnpm build`
  - passed
- Playwright admin
  - `2 passed`
- Playwright h5
  - `1 passed`

## 6. Playwright 证据路径

- `debug/e2e-commercial-ocr/20260505-014457/admin/blocked-review-gate/`
- `debug/e2e-commercial-ocr/20260505-014457/admin/complete-preview-publish/`
- `debug/e2e-commercial-ocr/20260505-014457/h5/preview-paper-mobile/`

## 7. 风险与遗留问题

- 真实百度/腾讯 provider 本轮默认未调用；真实 smoke 仍需显式 env flag。
- visual understanding 仍是 mock assist layer，不是正式 VLM 生产核验。
- backend 暂无独立 `/api/health` 探针。
- 对话里曾明文暴露百度 Key，必须尽快轮换；腾讯 SecretId/SecretKey 也绝不能写入仓库。

## 8. 回滚方案

1. 按 commit 粒度依次 `git revert`：
   - backend commercial OCR wiring
   - pdf-service visual pipeline
   - admin/h5 E2E flow
   - regression cleanup
2. 运行时回退到 `PDF_PARSE_PRIMARY_PROVIDER=local_parser`。
3. 停用 Playwright commercial OCR suite。

## 9. 是否允许进入下一阶段

`GO_WITH_RISK`
