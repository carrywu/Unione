# Provider Fallback 报告

一句话结论：视觉 provider 已切换为 `qwen_vl -> volcengine_ark_vl -> mimo_vl` 的健康排序，qwen 使用 soft-timeout hedged 到 Ark，mimo 在 429 时进入 cooldown。

当前实现：
- primary: `qwen_vl / qwen3-vl-plus`
- backup: `volcengine_ark_vl / doubao-seed-2-0-lite-260215`
- cooldown: `mimo_vl` 命中 `quota_exhausted` 后 60 分钟
- qwen 连续 timeout 3 次后 cooldown 10 分钟
- Ark 命中 `auth_error` / `model_not_open` 后禁用到配置变化
- provider cache: 以 `provider + model + page_b64 + prompt` 为 key，命中后不再重复计费调用

回归测试：
- `python -m unittest tests.test_ai_client_page_visual_fallbacks`
- `python -m unittest tests.test_provider_health_report`
