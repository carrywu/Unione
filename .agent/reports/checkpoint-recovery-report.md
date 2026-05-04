# Checkpoint Recovery 报告

一句话结论：已补齐轻量 checkpoint 机制，断电后可复用已完成页 cache，仅重跑当前失败/陈旧页。

实现摘要：
- backend 在调用 `pdf-service /parse-by-url` 时透传固定 `debug_dir`，将同一 task 绑定到稳定的 kernel-run 目录。
- parser kernel 新增 `debug/checkpoint-manifest.json`，记录 page status / stage / artifact sha256 / image sha256 / prompt_version。
- 所有新落盘 JSON 采用 `tmp -> fsync -> rename` 原子写。
- 成功页写入 `visual_page_cache/page_<n>.json`，恢复时先校验 sha256，再决定跳过或重跑。
- 恢复动作写入 `debug/recovery/<timestamp>/checkpoint-recovery.json`。

回归测试：
- 半截 JSON 不得被当作成功：`test_half_written_checkpoint_cache_is_not_treated_as_success`
- page 7 中断后只重跑 page 7：`test_completed_pages_are_reused_from_checkpoint_without_retry_flag`
- stale running 页可恢复：`test_stale_running_checkpoint_page_reruns_and_writes_recovery_report`
