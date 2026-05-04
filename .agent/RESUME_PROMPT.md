# RESUME PROMPT

继续处理 `/home/carry/project2` 的 “M4 AI 预审核收口”。

当前事实：

- `M2_PASS`
- `M3_PASS`
- `M4_FAIL`
- 最新 task：`836fec20-2628-44ed-9642-aedd57467864`
- 最新 verifier：`/home/carry/project2/.agent/reports/verifier-report.json`
- 最新最终报告：`/home/carry/project2/.agent/reports/final-report.md`

这轮已经完成：

- 修复了 fail-closed gate，warning/need_manual_fix 题不再被 `manualForceAddAllowed=true` 误放行
- 实现了 `qwen3-vl-plus -> Ark -> mimo cooldown` 的 provider fallback、hedged request、provider cache
- 补了 checkpoint manifest / atomic write / recovery report，并通过恢复相关测试
- 跑通了 admin-web Playwright，确认 review 页面与 live API 一致

当前阻塞：

1. `visual_summary` 仍是 `0/20`
2. `answer_suggestion` 仍是 `0/20`
3. `analysis_suggestion` 仍是 `0/20`
4. `risk_flags` 仍是 `0/20`
5. `visual_assets` 尚未补齐 `belongs_to_question / linked_by / link_reason / visual_hash`

下一步必须：

1. 从 live candidate 生成链路补齐以上 M4 字段
2. 重跑 `scripts/verifier_m2_playwright_audit.mjs`
3. 更新 `.agent/reports/verifier-report.json` 与 `.agent/reports/final-report.md`
4. 只有当 live API 与 admin-web 都展示完整 AI 预审核信息后，才能把 `m4_verdict` 改成 `M4_PASS`
