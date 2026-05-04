# M6C Preview/Dry-Run 发布 Smoke 报告

- task_id：`836fec20-2628-44ed-9642-aedd57467864`
- verdict：`M6C_PASS`
- preview_paper_id：`d2769db3-e51d-401f-b838-14df22caedf1`

## 结论

审核确认后的 preview-only 发布链路可用，H5 可打开预览题本并正常查看答案与解析，未污染真实生产数据。

## 验证结果

- `previewRouteReachable=true`
- `answerVisible=true`
- `analysisVisible=true`
- `production_published=false`
- `dry_run=true`

## 安全性

- 发布模式：`preview-only / dry-run`
- 不写入正式题库
- 不影响真实生产用户

## 审计

- preview 发布事件已写入：
  - `/home/carry/project2/backend/debug/m6/836fec20-2628-44ed-9642-aedd57467864/review-state.json`
- H5 预览提交日志已写入：
  - `/home/carry/project2/backend/debug/m6/836fec20-2628-44ed-9642-aedd57467864/preview-submit-log.json`

## 证据

- `/home/carry/project2/debug/m6/836fec20-2628-44ed-9642-aedd57467864/publish-smoke.json`
- `/home/carry/project2/debug/m6/836fec20-2628-44ed-9642-aedd57467864/screenshots/publish-preview-h5.png`
