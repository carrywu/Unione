# HANDOFF

> 当前主线 handoff 已切换到 `/home/carry/project2/.agent/handoff/README.md`，本文件保留为上一阶段 M5/M6 交付记录。

当前 authoritative truth：`M2_PASS / M3_PASS / M4_PASS / M5A_PASS / M5B_PASS / M6_PASS`。

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

- `M5A_PASS`
  - 真实题本已锁定：`/home/carry/题本/题本篇.pdf`
  - 真实答本已锁定：`/home/carry/答本/解析篇.pdf`
  - 20/20 题已生成真实答本对撞结果、冲突原因、证据与最终建议
  - API / admin-web 已直接读取 `debug/m5/.../m5a-answer-match-report.json`
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
- `/home/carry/project2/debug/m5/836fec20-2628-44ed-9642-aedd57467864/m5a-answer-match-report.json`
- `/home/carry/project2/debug/m5/836fec20-2628-44ed-9642-aedd57467864/answer-question-alignment.json`
- `/home/carry/project2/.agent/reports/m5a-answer-book-alignment-report.md`
- `/home/carry/project2/debug/m6/836fec20-2628-44ed-9642-aedd57467864/admin-review-playwright.json`
- `/home/carry/project2/debug/m6/836fec20-2628-44ed-9642-aedd57467864/publish-smoke.json`
- `/home/carry/project2/debug/h5-regression/836fec20-2628-44ed-9642-aedd57467864/playwright-h5-consistency.json`

## 不要做的事

- 不要回退多 agent 架构
- 不要重写 M2/M3/M4 主逻辑
- 不要把冲突题自动写回正式题库；只能作为建议并进入人工复核
- 不要伪造 similarity candidate
- 不要把 preview 发布当成真实生产发布
- 不要 force push 或改写历史

## 建议续跑顺序

1. 推送当前 `M5A` 代码、debug 产物与 report/handoff 更新
2. 如需继续推进，下一阶段只剩 `M7`，需要用户另行授权进入合规/审计加固阶段
