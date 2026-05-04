# M2 完成报告

一句话结论：最新全量任务 `836fec20-2628-44ed-9642-aedd57467864` 已满足 M2_PASS。

- produced / expected: 20 / 20
- fallback_failed_pages: []
- missing_question_numbers: []
- debug/live consistency: pass
- provider health: qwen3-vl-plus=pass, volcengine_ark_vl=pass, mimo_vl=fail(quota_exhausted, cooldown)
- canAddToPaper=true 的题目仅有 14、15，且均为 `ai_audit_status=passed`、`need_manual_fix=false`
- manualForceAddAllowed=true 数量已收敛为 0

证据路径：
- `/home/carry/project2/backend/debug/pdf-ai-preaudit/836fec20-2628-44ed-9642-aedd57467864/final-questions.json`
- `/home/carry/project2/backend/debug/pdf-ai-preaudit/836fec20-2628-44ed-9642-aedd57467864/fallback-recovery.json`
- `/home/carry/project2/backend/debug/pdf-ai-preaudit/836fec20-2628-44ed-9642-aedd57467864/question-number-scan.json`
- `/home/carry/project2/debug/pdf-semantic/836fec20-2628-44ed-9642-aedd57467864/playwright/playwright-recognition-audit.json`
