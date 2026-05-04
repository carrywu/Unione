# HANDOFF

当前 authoritative truth：`M2_PASS / M3_PASS / M4_FAIL`。提取完整性问题已经闭环，当前工作重点只能是 `M4 AI 预审核`。

## 已确认事实

- 最新全量 task：`836fec20-2628-44ed-9642-aedd57467864`
- `produced_question_count=20 / expected_question_count=20`
- `fallback_failed_pages=[]`
- `missing_question_numbers=[]`
- `debug/live consistency=pass`
- `manualForceAddAllowed=true` 数量为 `0`
- `warning/failed` 题 `canAddToPaper=true` 数量为 `0`
- `qwen3-vl-plus` 与 `volcengine_ark_vl` 均 `pass`
- `mimo_vl` 为 `429 quota_exhausted`，已视为 cooldown，不阻塞 M2

## 当前 M4 blocker

1. `visual_summary` 覆盖率 `0/20`
2. `answer_suggestion` 覆盖率 `0/20`
3. `analysis_suggestion` 覆盖率 `0/20`
4. `risk_flags` 覆盖率 `0/20`
5. `visual_assets` 缺少 `belongs_to_question / linked_by / link_reason / visual_hash`

## 这轮新增的重要产物

- `/home/carry/project2/.agent/reports/verifier-report.json`
- `/home/carry/project2/.agent/reports/final-report.md`
- `/home/carry/project2/.agent/reports/checkpoint-recovery-report.md`
- `/home/carry/project2/.agent/reports/provider-fallback-report.md`
- `/home/carry/project2/debug/pdf-semantic/836fec20-2628-44ed-9642-aedd57467864/playwright/`

## 不要做的事

- 不要回退多 agent 架构
- 不要再把 page 5 当成当前 blocker
- 不要伪造 `M4_PASS`
- 不要写 questionId / bankId / page 5 特判来补字段

## 建议续跑顺序

1. 从 live candidate 生成路径补齐 `visual_summary / answer_suggestion / analysis_suggestion / risk_flags`
2. 将 `visual_assets` 补成完整 linkage 结构
3. 重跑 `scripts/verifier_m2_playwright_audit.mjs`
4. 只有当 live API 与 admin-web 同时显示完整 AI 预审核字段后，才可把 `m4_verdict` 改为 `M4_PASS`
