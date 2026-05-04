# COCR-M8b Backend Provider Wiring

## 1. 本阶段目标

把 commercial OCR pipeline 从 `pdf-service` 单元测试层推进到 backend 真实业务链路，让 provider、material group、quality gate、visual understanding 和 fallback 信息进入 review / publish DTO。

## 2. 修改范围

- 更新 `backend/src/modules/pdf/pdf.service.ts`
- 更新 `backend/src/modules/question/question.service.ts`
- 更新 `backend/src/modules/system/system.service.ts`
- 更新 `backend/test/pdf-review-workflow.test.ts`
- 更新 `backend/.env.example`

## 3. 架构变化

- backend 现在允许读取并透传：
  - `COMMERCIAL_OCR_ENABLED`
  - `PDF_PARSE_PRIMARY_PROVIDER`
  - `PDF_PARSE_FALLBACK_PROVIDERS`
  - `OCR_PROVIDER_TRACE_ENABLED`
  - `COMMERCIAL_OCR_REAL_SMOKE`
  - mock fixture override 变量
- `paper-candidates`、review debug payload、preview paper payload 优先消费 `commercial_ocr` 输出，而不是只看旧 local parser 结果。
- 当 provider 不是 `local_parser` 时，backend 会优先组装 commercial OCR preview，并保留 local parser fallback 路径。

## 4. 数据结构/API 变化

新增或稳定透传以下 DTO 字段：

- `provider_name`
- `provider_version`
- `provider_latency_ms`
- `provider_status`
- `provider_error`
- `fallback_used`
- `raw_response_ref`
- `material_groups`
- `question_groups`
- `quality_gate`
- `visual_understanding`
- `grouping_evidence`
- `grouping_confidence`
- `shared_assets`
- `provider_trace_ref`

backend publish / add-to-draft gate 现已阻止：

- `review_ready=false`
- `extracted_but_incomplete=true`
- `answer=null`
- `analysis=unknown`
- layout-only candidate
- incomplete shared-material group

## 5. 测试与验证

- `cd backend && pnpm build`
  - 通过
- `cd backend && pnpm exec ts-node -r tsconfig-paths/register test/pdf-review-workflow.test.ts`
  - 通过，exit code `0`
- Playwright admin API + UI 闭环：
  - blocked fixture draft 创建被 `400` 拒绝
  - complete fixture draft + preview publish 成功

## 6. Playwright 证据路径

- admin blocked case: `debug/e2e-commercial-ocr/20260505-014457/admin/blocked-review-gate/`
- admin publishable case: `debug/e2e-commercial-ocr/20260505-014457/admin/complete-preview-publish/`

## 7. 风险与遗留问题

- backend 当前没有单独 `/api/health` 健康探针；本轮使用登录与业务 API 作为实际健康验证。
- 真实 commercial provider 仍默认关闭，仅 mock provider 进入全链路。
- preview publish 已打通，正式生产 publish 策略仍需 M9/M12 继续收敛。

## 8. 回滚方案

1. `git revert` backend commercial OCR wiring 提交。
2. 运行时关闭 `COMMERCIAL_OCR_ENABLED` 或将主 provider 切回 `local_parser`。
3. admin review 将回退到既有 local parser 预览路径。

## 9. 是否允许进入下一阶段

`GO_WITH_RISK`
