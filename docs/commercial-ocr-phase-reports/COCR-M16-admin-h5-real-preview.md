# COCR-M16 Admin H5 Real Preview

## 1. 阶段目标

admin 端在审核页面提供真实 H5 端一致的预览页面。

## 2. 方案选择

**方案 A：iframe 嵌入真实 h5 preview 路由**

- h5-web 已有 `/quiz-preview/:paperId` 路由
- admin 中用 iframe 嵌入该 h5 preview 页面
- iframe viewport 固定为 390x844

## 3. 修改范围

- `admin-web/src/views/pdf/PaperReviewView.vue`
  - 新增 H5 preview section（iframe + device frame + info panel）
  - 新增 `h5PreviewUrl` computed（从 paperId 或 preview_route 生成）
  - 新增 `h5PreviewKey` ref（刷新 iframe 用）
  - 新增 `openH5InNewTab` 函数
  - 新增 CSS：`.h5-preview-container`, `.h5-device-frame`, `.h5-preview-iframe`, `.h5-preview-info`

## 4. 数据流

```
admin 保存草稿 → paperId
admin Preview 发布 → previewPublishMeta.preview_route
admin H5 preview section 计算 h5PreviewUrl
  ↓
iframe src = http://127.0.0.1:5173/quiz-preview/:paperId
  ↓
h5-web QuizView (isPreviewMode=true)
  → getPreviewPaper(paperId)
  → startPreviewQuiz()
  → 渲染题目、shared material、选项、答案解析
```

## 5. H5 Preview 功能

- 390x844 移动端 viewport
- 题目列表/题号导航
- 17/18/19/20 切换
- shared material 展示
- 图表/表格/材料图展示
- options 展示
- answer/analysis 预览
- 刷新预览按钮
- 打开真实 H5 页面按钮

## 6. 测试结果

| 测试 | 结果 |
|------|------|
| admin build | PASS |
| admin E2E (2 tests) | 2 passed |
| force publish E2E (3 tests) | 3 passed |
| h5 E2E (1 test) | 1 passed |
| Total Playwright | 6/6 passed |

## 7. 证据路径

- `debug/e2e-commercial-ocr/20260505-193000/admin/`
- `debug/e2e-commercial-ocr/20260505-193000/h5/`

## 8. 风险

- iframe 跨域问题：admin-web 和 h5-web 同域（localhost），无 CORS 问题
- h5-web 需要运行才能加载 iframe
- h5-web 需要登录 token（localStorage h5_token）

## 9. 回滚方案

1. `git revert` 本轮提交
2. admin-web 恢复到原有 preview drawer

## 10. 结论

`GO`

admin H5 real preview 已集成，使用 iframe 嵌入真实 h5-web preview 路由。
全部 6 个 Playwright 测试通过。
