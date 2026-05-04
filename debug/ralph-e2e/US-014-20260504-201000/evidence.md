# US-014: 制卷核对页真人式审核体验

## API Data Verification (代替浏览器验证)

### 数据完整性
| 检查项 | 结果 |
|--------|------|
| 总题数 | 20 |
| 题号连续 (1-20) | ✅ |
| 每题有题干 (stem) | ✅ 20/20 |
| 每题有选项 (options A-D) | ✅ 20/20 |
| 每题有答案 (answer_suggestion 或 M5A final_answer_suggestion) | ✅ 20/20 |
| 每题有解析 (analysis_suggestion 或 M5A final_analysis_suggestion) | ✅ 20/20 |
| 每题有图片 (visual_assets) | ✅ 20/20 (共 62 张) |
| 每题有 M5A 数据 | ✅ 20/20 |
| 每题有 M5B 数据 | ✅ 20/20 |
| 每题有 candidate_id (审核操作) | ✅ 20/20 |
| API 无 undefined 值 | ✅ |
| API 无 [object Object] 值 | ✅ |

### UI 代码检查 (PaperReviewView.vue)
- `textOr()` helper 处理 null/undefined → 返回 fallback
- `MathText` 组件有 `fallback` prop
- 选项使用 `selectedCandidate.options?.[label]` + optional chaining
- M5A/M5B 字段全部有 fallback 处理
- `fixture_only` 仅用作 `v-if` 布尔判断，不直接渲染
- TaskListView 状态标签处理未知状态 → 显示原始字符串

### 审核按钮可用性
- 每题有 `candidate_id` → 可调用 `POST /admin/pdf/task/:taskId/review-action`
- 审核状态可通过 `GET /admin/pdf/task/:taskId/review-state` 获取

### 待浏览器验证
- 页面实际渲染效果
- 逐题截图
- 按钮点击响应
- 移动端窄屏适配

## Quality Checks
- backend test: PASS (EXIT 0)
- backend build: PASS
- admin-web build: PASS
