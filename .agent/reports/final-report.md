# 最终报告

一句话结论：最新全量任务 `836fec20-2628-44ed-9642-aedd57467864` 已真实达到 `M2_PASS`，现状是 `M3_PASS / M4_FAIL`，阻塞已从提取完整性转移到 AI 预审核字段覆盖不足与 image linkage 元数据缺失。

## 1. 最新任务与结论

- 最新 task_id：`836fec20-2628-44ed-9642-aedd57467864`
- M2：`PASS`
- M3：`PASS`
- M4：`FAIL`
- verifier：`/home/carry/project2/.agent/reports/verifier-report.json`

## 2. M2 是否完成

- verdict：`PASS`
- produced / expected：`20 / 20`
- fallback_failed_pages：`[]`
- missing_question_numbers：`[]`
- debug/live consistency：`pass`
- provider health：`qwen3-vl-plus=pass`、`volcengine_ark_vl=pass`、`mimo_vl=fail(quota_exhausted, cooldown)`
- fail-closed：`manualForceAddAllowed=true` 已收敛为 `0`；`warning/failed` 题 `canAddToPaper=true` 已收敛为 `0`
- 关键证据：
  - `/home/carry/project2/backend/debug/pdf-ai-preaudit/836fec20-2628-44ed-9642-aedd57467864/final-questions.json`
  - `/home/carry/project2/backend/debug/pdf-ai-preaudit/836fec20-2628-44ed-9642-aedd57467864/fallback-recovery.json`
  - `/home/carry/project2/backend/debug/pdf-ai-preaudit/836fec20-2628-44ed-9642-aedd57467864/question-number-scan.json`
  - `/home/carry/project2/debug/pdf-semantic/836fec20-2628-44ed-9642-aedd57467864/playwright/playwright-live-paper-candidates-api.json`

## 3. M3 是否完成

- verdict：`PASS`
- page-understanding：`8/8`
- semantic-groups：`30`
- recrop-plan：`30`
- final-questions：`20`
- final-preview questions：`20`
- 验收结论：现有 review 页面与 API 一致，未出现碎图、标题丢失、题干缺失、`undefined`、`[object Object]`、`visual parse unavailable`
- 关键证据：
  - `/home/carry/project2/backend/debug/pdf-ai-preaudit/836fec20-2628-44ed-9642-aedd57467864/page-understanding.json`
  - `/home/carry/project2/backend/debug/pdf-ai-preaudit/836fec20-2628-44ed-9642-aedd57467864/semantic-groups.json`
  - `/home/carry/project2/backend/debug/pdf-ai-preaudit/836fec20-2628-44ed-9642-aedd57467864/recrop-plan.json`
  - `/home/carry/project2/debug/pdf-semantic/836fec20-2628-44ed-9642-aedd57467864/playwright/admin-paper-review.png`

## 4. M4 是否完成

- verdict：`FAIL`
- ai_audit 字段覆盖率：`ai_audit_status 20/20`，`ai_audit_verdict 20/20`，`ai_audit_summary 10/20`
- answer_suggestion 覆盖率：`0/20`
- analysis_suggestion 覆盖率：`0/20`
- risk_flags 覆盖率：`0/20`
- visual_summary 覆盖率：`0/20`
- image linkage 完整率：`0/20`
- admin-web 展示：页面可达，截图与 trace 已落盘，但字段内容不足以通过 M4 验收
- 最小 blocker：
  - `visual_summary` 未回填
  - `answer_suggestion` / `analysis_suggestion` 未回填
  - `risk_flags` 未回填
  - `visual_assets` 未补齐 `belongs_to_question / linked_by / link_reason / visual_hash`

## 5. Checkpoint 机制

- 落库/manifest 方式：本轮未做 DB migration，当前以稳定 `debug_dir + checkpoint-manifest.json + visual_page_cache + recovery report` 作为权威恢复索引；业务状态仍以 DB task 状态与 artifact 为准
- 原子写实现：所有新增 JSON 走 `tmp -> fsync -> rename`
- 恢复逻辑：已完成页先校验 sha256 命中 cache，半截 JSON 与 stale running 页会被识别并只重跑当前页/当前阶段
- 断电恢复测试：
  - 半截 JSON 不得当作成功：`pass`
  - 已完成页不重跑：`pass`
  - provider 中断页仅重跑当前页：`pass`
  - stale running 页可恢复：`pass`
  - 证据：`/home/carry/project2/.agent/reports/checkpoint-recovery-report.md`

## 6. Provider Fallback

- 当前运行时主备排序：`qwen3-vl-plus -> volcengine_ark_vl -> mimo_vl(cooldown)`
- `qwen3-vl-plus`：`pass`
- `volcengine_ark_vl`：`pass`，通过 `responses` API 使用 `doubao-seed-2-0-lite-260215`
- `mimo_vl`：`429 quota_exhausted`，已进入 cooldown，不再参与普通页处理
- hedged request：`已实现`
- cache：`已实现`，命中后跳过重复 provider 调用
- 证据：`/home/carry/project2/.agent/reports/provider-fallback-report.md`

## 7. 修改文件清单

- `backend/src/modules/pdf/pdf.service.ts`
- `backend/test/pdf-review-workflow.test.ts`
- `pdf-service/ai_client.py`
- `pdf-service/debug_writer.py`
- `pdf-service/main.py`
- `pdf-service/models.py`
- `pdf-service/parser_kernel/adapter.py`
- `pdf-service/pipeline.py`
- `pdf-service/tools/provider_health_report.py`
- `pdf-service/tests/test_ai_client_page_visual_fallbacks.py`
- `pdf-service/tests/test_provider_health_report.py`
- `pdf-service/tests/test_scanned_question_book_kernel.py`
- `scripts/m2_failclosed_smoke.sh`
- `scripts/m2_verifier_report.py`
- `scripts/verifier_m2_playwright_audit.mjs`
- `tests/test_m2_verifier_report.py`

## 8. 新增测试清单

- `backend/test/pdf-review-workflow.test.ts`
- `pdf-service/tests/test_ai_client_page_visual_fallbacks.py`
- `pdf-service/tests/test_provider_health_report.py`
- `pdf-service/tests/test_scanned_question_book_kernel.py`
- `tests/test_m2_verifier_report.py`

## 9. Playwright 与 debug 证据路径

- Playwright：
  - `/home/carry/project2/debug/pdf-semantic/836fec20-2628-44ed-9642-aedd57467864/playwright/playwright-recognition-audit.json`
  - `/home/carry/project2/debug/pdf-semantic/836fec20-2628-44ed-9642-aedd57467864/playwright/admin-paper-review.png`
  - `/home/carry/project2/debug/pdf-semantic/836fec20-2628-44ed-9642-aedd57467864/playwright/playwright-trace.zip`
- Debug：
  - `/home/carry/project2/backend/debug/pdf-ai-preaudit/836fec20-2628-44ed-9642-aedd57467864`
  - `/home/carry/project2/debug/autofix/20260504-101859-m2-to-m4-managed-mode`

## 10. 剩余最小 blocker

- 当前只剩 `M4` 阶段 blocker，不再是 `M2`
- 最小下一步：在 live candidate / admin review 结果中补齐 `visual_summary`、答案建议、解析建议、risk flags 与完整 image linkage 字段，然后重新跑 admin-web Playwright 验收

## 11. 早上直接执行的 3 条命令

- `cat /home/carry/project2/.agent/reports/final-report.md`
- `jq '{task_id, m2_verdict, m3_verdict, m4_verdict, failed_checks}' /home/carry/project2/.agent/reports/verifier-report.json`
- `find /home/carry/project2/debug -type f -mmin -720 | sort | tail -80`
