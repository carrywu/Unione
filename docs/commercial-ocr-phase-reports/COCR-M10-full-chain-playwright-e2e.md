# COCR-M10 Full-Chain Playwright E2E

## 1. 本阶段目标

以 mock commercial OCR 为默认输入，跑通 `backend -> pdf-service -> admin -> publish-preview -> h5` 的真人式全链路，并保存截图、trace、console、network 证据。

## 2. 修改范围

- 新增 `playwright.config.ts`
- 新增 `e2e/commercial-ocr.helpers.ts`
- 新增 `e2e/commercial-ocr-admin.spec.ts`
- 新增 `e2e/commercial-ocr-h5.spec.ts`
- 更新 admin / h5 页面 testids

## 3. 架构变化

- Playwright 先通过 admin API 配置 mock fixture，再走页面上传和审核。
- admin case 分成 blocked fixture 与 publishable fixture 两条主路径。
- h5 case 通过 preview publish 结果进入 `/quiz-preview/:paperId`，以移动端 viewport 验证 shared material 题组体验。

## 4. 数据结构/API 变化

E2E 变量：

- `E2E_BACKEND_URL`
- `E2E_PDF_SERVICE_URL`
- `E2E_ADMIN_URL`
- `E2E_H5_URL`
- `E2E_USE_MOCK_OCR`
- `E2E_ARTIFACT_DIR`

产物结构：

- `screenshots/*.png`
- `traces/*.zip`
- `console.json`
- `network.json`
- `final-admin-review-state.json`
- `final-h5-state.json`

## 5. 测试与验证

- admin：
  - `E2E_ARTIFACT_DIR=debug/e2e-commercial-ocr/20260505-014457 pnpm exec playwright test e2e/commercial-ocr-admin.spec.ts`
  - `2 passed`
- h5：
  - `E2E_ARTIFACT_DIR=debug/e2e-commercial-ocr/20260505-014457 pnpm exec playwright test e2e/commercial-ocr-h5.spec.ts`
  - `1 passed`

验收结果：

- blocked fixture：草稿创建被拒绝，UI 显示 quality gate 阻断
- publishable fixture：17-20 共享材料保持一致，admin preview publish 成功
- h5：17/18/19/20 均能看到 shared material，连续答题后进入 result 页

## 6. Playwright 证据路径

- `debug/e2e-commercial-ocr/20260505-014457/admin/blocked-review-gate/`
- `debug/e2e-commercial-ocr/20260505-014457/admin/complete-preview-publish/`
- `debug/e2e-commercial-ocr/20260505-014457/h5/preview-paper-mobile/`

## 7. 风险与遗留问题

- 本轮默认使用 mock commercial OCR，不代表真实百度/腾讯 provider 的 UI 时延与稳定性。
- 测试依赖本地 seed 账号：
  - `admin/admin`
  - `13800138000/123456`
- backend 暂无单独 `/api/health`，E2E 通过业务 API 验证服务可用性。

## 8. 回滚方案

1. 删除 `e2e/commercial-ocr-*.spec.ts` 与 helper。
2. 保留页面 testids，不再运行该套全链路用例。
3. 如需禁用，CI/本地不执行 Playwright commercial OCR suite。

## 9. 是否允许进入下一阶段

`GO_WITH_RISK`
