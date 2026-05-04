# 最近工作总结

生成时间：2026-05-03 17:50（Asia/Shanghai）

## 2026-05-04 09:48 更新

- 已把 Qwen 视觉模型从 `qwen-vl-max` 切到 `qwen3-vl-plus`。
- 已更新位置：
  - 运行配置：`/home/carry/project2/pdf-service/.env`、`/home/carry/project2/.env`
  - 默认回退与相关代码：`pdf-service/ai_client.py`、`pdf-service/parser_kernel/adapter.py`、`pdf-service/vision_ai/qwen_vl_provider.py`、`backend/src/modules/*`、`admin-web/src/views/system/SystemView.vue`
  - 持久化系统配置：Postgres `system_configs` 表中 `AI_VISUAL_MODEL=qwen3-vl-plus`
- 已验证：
  - `provider_health_report.py` 显示 `qwen_vl.model_or_endpoint=qwen3-vl-plus` 且 `health=pass`
  - `volcengine_ark_vl` 仍为 `health=pass`
  - `PYTHONPATH=pdf-service pdf-service/.venv/bin/python -m unittest pdf-service/tests/test_ai_client_page_visual_fallbacks.py pdf-service/tests/test_provider_health_report.py` 通过
- 最新关键突破：
  - 真实目标页 `page 5` smoke 已成功，不再是 `fallback_failed`
  - 证据目录：`/home/carry/project2/debug/autofix/20260504-0937-real-page5-qwen3`
  - 关键结果：
    - provider=`volcengine_ark_vl`
    - model=`doubao-seed-2-0-lite-260215`
    - `elapsed_ms=153742`
    - `accepted_questions=5`
    - `questions_preview=[16,17,18,19,20]`
- 当前正在进行的全量 forced-new rerun：
  - 新 task_id：`836fec20-2628-44ed-9642-aedd57467864`
  - Verifier 输出目录：`/home/carry/project2/debug/hermes/20260502-222819-M2-longrun/phaseA-m2-forced-new-acceptance`
  - 当前状态（2026-05-04 09:48 CST）：`processing`, `progress=10`, `done_count=0`, `total_count=0`
  - 当前判断：不是本地死锁。`backend(pid=121800)` 与 `pdf-service(pid=120978)` 均存活；`pdf-service` 保持到远端 `:443` 的已建立连接，说明正在等待远端视觉推理返回。

## 恢复依据

上一个对话内容无法直接从当前消息中完整恢复；本总结基于当前工作区可见的恢复文件、状态文件和报告重建，重点参考：

- `/home/carry/project2/.agent/CHECKPOINT.md`
- `/home/carry/project2/.agent/STATUS.json`
- `/home/carry/project2/.agent/BOARD.md`
- `/home/carry/project2/.agent/reports/builder-report.md`
- `/home/carry/project2/.agent/reports/diagnosis-report.md`
- `/home/carry/project2/.agent/reports/verifier-report.md`
- `/home/carry/project2/.agent/reports/archivist-report.md`

## 当前结论

- 项目：`/home/carry/project2`
- 当前任务目标：用户希望“完成 M3 环节后再验收，开启托管模式”。
- Supervisor 的执行解释：必须先完成 M2 PASS gate；只有 M2 明确 PASS 后，才允许进入 M3。
- 最新明确状态：`M2 FAIL`。
- 当前限制：不得进入 M3/M4，不得写 M3/M4 代码，不得运行 M3/M4 验收。

## 刚刚完成的工作

1. 恢复并读取了 `.agent` 体系下的项目上下文，包括 `BOARD.md`、旧 checkpoint、worker reports 和运行状态。
2. 确认托管运行环境存在，`project2-agents` tmux session 处于 running，`.agent/STATUS.json` 显示 runtime ready。
3. 重新汇总了 M2 的关键事实：
   - Builder 已做过 B3 代码变更，并在 `pdf-service/parser_kernel/adapter.py` 中加入了 source_text_span、material_group、debug artifact 相关逻辑。
   - pdf-service 单元测试已通过：`85 passed, 1 skipped`。
   - 旧 task `50bee0c6-a85c-438d-87fc-b360a2eedf85` 仍是失败证据，不能作为 PASS 依据。
   - forced-new V2 task `7bc62665-7c46-41ec-b651-e74da9a1220e` 已 terminal/done，且 Q7 已在 page-understanding 层恢复。
4. 重新判定 V2 仍不满足 M2 gate：
   - page-understanding question numbers: `[1,5,6,7,8,9,10,11]`
   - final-preview question numbers: `[5,6,7,8,9,10,11,1]`
   - `source_text_span`: `0/8`
   - explicit `source_bbox`: final/debug `0/8`
   - `source_page_refs`: `8/8`
   - `material_group` / shared material binding: `0/8`
   - `fallback_failed` pages: `[1,4,5,7,8]`
   - candidates 仍全部 `need_manual_fix=8/8`
5. 根据上述事实，继续保持 M2 fail-closed：
   - 不把 Q7 出现本身视作 M2 通过。
   - 不允许 source_text_span/material_group 为空时进入 M3。
   - 不允许通过 canAddToPaper 或 manual force add 绕过 gate。
6. 已通过文件协议向四个 worker 分派 B4 任务：
   - Builder：`/home/carry/project2/.agent/reports/builder-task.md`
   - Diagnostician：`/home/carry/project2/.agent/reports/diagnostician-task.md`
   - Verifier：`/home/carry/project2/.agent/reports/verifier-task.md`
   - Archivist：`/home/carry/project2/.agent/reports/archivist-task.md`
7. 已更新 worker marker，并保存新的恢复点：
   - `/home/carry/project2/.agent/CHECKPOINT.md`
   - `/home/carry/project2/.agent/STATUS.json`
   - `/home/carry/project2/.agent/reports/supervisor-runtime-last.md`

## B4 分工

### Builder

继续只做 M2 修复，不做 M3/M4：

- 修改 `backend/src/modules/pdf/pdf.service.ts`，确保 5 个新 debug JSON 能被复制到 backend debug 目录。
- 增加 provider fallback recovery chain。
- 确认 `source_text_span` 和 `material_group` 从 pdf-service 到 backend/API 的传播链。
- 更新 `/home/carry/project2/.agent/reports/builder-report.md`。

### Diagnostician

继续只做 M2 诊断：

- 确认 V2 task 是否使用了旧代码路径。
- 分析 provider fallback 根因。
- 分析 `source_text_span` / `material_group` 在哪一层丢失。
- 更新 `/home/carry/project2/.agent/reports/diagnosis-report.md`。

### Verifier

等待 Builder 完成后执行：

- 重启 pdf-service。
- 创建 V3 forced-new task。
- 运行完整 M2 验收。
- 输出 V3 before/after 对比。
- 只有全部 gate 通过，才允许写 `M2 PASS`。

### Archivist

持续维护恢复资料：

- `.agent/CHECKPOINT.md`
- `.agent/HANDOFF.md`
- `.agent/RESUME_PROMPT.md`
- `.agent/reports/final-report.md`
- longrun 目录下的交接产物。

## 当前阻塞点

- M2 最新明确 verdict 仍是 `FAIL`。
- Verifier 尚未写出明确 `M2 PASS`。
- V2 虽然恢复了 Q7，但 source/material/fallback 证据仍不达标。
- 不得进入 M3/M4。

## 下一步建议

1. 让 Builder 优先补 backend 对 5 个 debug JSON 的复制，并修通 `source_text_span` / `material_group` 的传播链。
2. 让 Diagnostician 明确 V2 的运行代码版本和字段丢失层级。
3. Builder 完成后，由 Verifier 重启服务并创建 V3 forced-new task。
4. 只用 V3 的 API/debug/Playwright 三方一致证据判断 M2 是否 PASS。
5. M2 PASS 之后，再进入 M3。

## 可恢复命令

```bash
cd /home/carry/project2
bash scripts/agent-orchestrator.sh status
sed -n '1,220p' .agent/CHECKPOINT.md
find .agent/reports -maxdepth 1 -type f -printf '%TY-%Tm-%Td %TH:%TM %p\n' | sort
```

## 安全说明

本总结只记录状态、路径和聚合指标；没有读取或写入 `.env`、API key、token、`sk-` 开头密钥或其他凭据。
