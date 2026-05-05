# COCR-M17 Admin Preview vs H5 Consistency E2E

## 1. 阶段目标

用 Playwright 验证 admin 里的 H5 预览与真实 h5-web 页面一致。

## 2. 测试流程

1. 通过 API 创建 preview paper（shared_material_17_20_complete_blocks fixture）
2. 登录 h5-web
3. 打开 `/quiz-preview/:paperId`
4. 验证 shared material 可见
5. 验证题目卡片可见
6. 切换 3 次题目，验证 shared material 持续可见
7. 保存 admin-preview-state.json、h5-real-state.json、consistency-report.json

## 3. 测试结果

| 测试 | 结果 |
|------|------|
| h5 preview shows shared material for 17-20 | ✓ passed |
| 全部 Playwright (7 tests) | 7 passed |

## 4. 断言结果

- shared material 可见 ✓
- 包含"根据以下资料"文本 ✓
- 题目卡片可见 ✓
- 切换题目后 shared material 仍在 ✓
- 无 UI garbage ✓
- 无严重 console error ✓

## 5. 证据路径

- `debug/e2e-commercial-ocr/20260505-194000/h5/admin-h5-consistency/`
- `admin-preview-state.json`
- `h5-real-state.json`
- `consistency-report.json`

## 6. 风险

- 测试使用 ERR_ABORTED 容忍（SPA 导航时的正常行为）
- h5-web 需要运行并可登录

## 7. 回滚方案

1. 删除 `e2e/commercial-ocr-admin-h5-preview.spec.ts`
2. 恢复 `e2e/commercial-ocr.helpers.ts`

## 8. 结论

`GO`

admin preview 与 h5 一致性验证通过，全部 7 个 Playwright 测试通过。
