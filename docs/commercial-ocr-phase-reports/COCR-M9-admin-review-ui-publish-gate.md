# COCR-M9 Admin Review UI + Publish Gate

## 1. 本阶段目标

让 admin-web 真正展示 commercial OCR / semantic assembler / quality gate 结果，并把 publish gate 前推到人工审核与入卷动作。

## 2. 修改范围

- 更新 `admin-web/src/api/pdf.ts`
- 更新 `admin-web/src/views/pdf/PaperReviewView.vue`
- 更新 `admin-web/src/views/LoginView.vue`
- 更新 `admin-web/src/views/banks/BankUploadView.vue`
- 配合 backend gate 更新 `backend/src/modules/pdf/pdf.service.ts`

## 3. 架构变化

- `PaperReviewView` 现在展示：
  - provider
  - fallback status
  - provider trace ref
  - material group / question range
  - grouping evidence / grouping confidence
  - quality gate / blocking reasons
  - visual understanding summary
  - warnings / missing fields
  - similarity panel 空状态或候选状态
- `加入试卷` 按钮会被 quality gate 直接禁用。
- blocked candidate 即使绕过 UI，也会被 backend `POST /admin/pdf/papers/draft` 拒绝。

## 4. 数据结构/API 变化

admin candidate DTO 重点字段：

- `quality_gate`
- `needs_human_review`
- `material_id`
- `shared_stem`
- `semantic_group`
- `visual_understanding`
- `provider_trace_ref`
- `similarity`

新增稳定的 UI 选择器：

- `paper-review-overview`
- `quality-gate-badge`
- `shared-material-panel`
- `similarity-panel`
- `selected-question-stem`
- `start-upload-parse`
- `enter-review-edit`

## 5. 测试与验证

- `cd admin-web && pnpm build`
  - 通过
- Playwright admin：
  - `pnpm exec playwright test e2e/commercial-ocr-admin.spec.ts`
  - `2 passed`

覆盖：

- blocked fixture 显示 `review_ready=false`
- 17/18/19/20 共享材料可切换查看
- `local_stem` 不重复 `shared_stem`
- blocked candidate 不允许入卷
- complete fixture 可保存草稿并生成 preview publish

## 6. Playwright 证据路径

- `debug/e2e-commercial-ocr/20260505-014457/admin/blocked-review-gate/`
- `debug/e2e-commercial-ocr/20260505-014457/admin/complete-preview-publish/`

## 7. 风险与遗留问题

- 当前演示的是 preview publish，不是最终生产发布审批流。
- 相似题区域已稳定显示空状态和候选状态，但 M5B 更复杂排序/去重策略仍沿用既有逻辑。
- 人工强制放行 warning case 的策略尚未专门产品化。

## 8. 回滚方案

1. `git revert` admin review UI 与 backend gate 提交。
2. 保留 backend DTO，不在 UI 使用 commercial OCR 衍生字段。
3. 继续使用旧 review 页面最小信息展示。

## 9. 是否允许进入下一阶段

`GO_WITH_RISK`
