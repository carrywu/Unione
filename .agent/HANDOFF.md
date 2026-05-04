# HANDOFF

当前 authoritative truth：`M2_PASS / M3_PASS / M4_PASS / M6_PASS`。

- 最新全量 task：`836fec20-2628-44ed-9642-aedd57467864`
- 当前分支：`main`
- remote：`origin -> git@github.com:carrywu/Unione.git`
- 最近已推送代码提交：
  - `e7c3052 feat(admin): add review closure workflow`
  - `438502e test(h5): add mobile question consistency audit`
  - `6429fee test(pdf): add publish smoke workflow`

## 已确认事实

- `produced_question_count=20 / expected_question_count=20`
- `fallback_failed_pages=[]`
- `missing_question_numbers=[]`
- `debug_live_consistency=pass`
- `M4` 字段覆盖率仍为 `20/20`
- admin-web 审核页已完成动作闭环并落审计事件
- H5 预览一致性已完成 `20/20` 截图和 compare summary
- preview 发布链路为 `dry-run / preview-only`，`production_published=false`

## M5/M6 口径

- `M5A_IN_PROGRESS`
  - 下一步直接读取 `/home/carry/答本` 做真实答本/解析本对撞
  - seeded fixture 只能作为兜底 UI 验证，不能再作为 authoritative 结果
- `M5B_PASS`
  - backend 已接入真实历史题库 similarity / duplicate 候选生成
  - admin-web 已展示真实候选明细、分数、来源与人工决策区
- `M6_PASS`
  - `M6A_PASS`
  - `M6B_PASS`
  - `M6C_PASS`

## 关键证据

- `/home/carry/project2/backend/debug/m6/836fec20-2628-44ed-9642-aedd57467864/review-state.json`
- `/home/carry/project2/backend/debug/m6/836fec20-2628-44ed-9642-aedd57467864/preview-submit-log.json`
- `/home/carry/project2/backend/debug/m6-preview-papers/h5-audit-836fec20-2628-44ed-9642-aedd57467864.json`
- `/home/carry/project2/debug/m6/836fec20-2628-44ed-9642-aedd57467864/admin-review-playwright.json`
- `/home/carry/project2/debug/m6/836fec20-2628-44ed-9642-aedd57467864/publish-smoke.json`
- `/home/carry/project2/debug/h5-regression/836fec20-2628-44ed-9642-aedd57467864/playwright-h5-consistency.json`

## 不要做的事

- 不要回退多 agent 架构
- 不要重写 M2/M3/M4 主逻辑
- 不要把 seeded fixture 当成正式答本结果
- 不要伪造 similarity candidate
- 不要把 preview 发布当成真实生产发布
- 不要 force push 或改写历史

## 建议续跑顺序

1. 推送当前 `M5B` 代码与 report/handoff 更新
2. 读取 `/home/carry/题本` 与 `/home/carry/答本`，完成真实 `M5A` 对撞
3. `M7` 仍未启动，需要用户另行授权进入合规/审计加固阶段
