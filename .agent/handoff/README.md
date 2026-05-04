# Commercial OCR Overnight Handoff

当前默认恢复入口：

- 最新 overnight handoff：`/home/carry/project2/.agent/handoff/commercial-ocr-overnight-20260504-2335.md`
- Phase README：`/home/carry/project2/docs/commercial-ocr-phase-reports/README.md`
- 当前主线分支：`main`
- 当前 code baseline commit：`d7b26a0`

## 本轮落地范围

- COCR-M2 mock fixture / mock provider / fallback tests
- COCR-M3 OCR normalizer
- COCR-M4 17-20 shared-material semantic assembler
- COCR-M7 parse quality gate
- COCR-M8-pre Tencent OCR SDK adapter + real smoke gating
- 额外修复：vision soft-timeout hedge 胜者覆盖问题

## 仍未完成

- COCR-M5 visual understanding
- COCR-M9 review UI / publish hard gate
- 既有回归：`test_provider_health_report` 两条、`test_visual_api_smoke_tool` 一条

## 恢复建议

1. `git checkout main && git pull --ff-only origin main`
2. 先看 overnight handoff，再看对应 phase report。
3. 优先处理 M5 / M8 hardening / M9 或既有 3 条回归。

