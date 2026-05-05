# Data Analysis First OCR API Understanding Report

## Summary

- Branch: `mimo`
- Baseline tag: `pre-data-analysis-ocr-api-first-20260505-221735`
- Scope: 先完成资料分析 17-20 共用材料闭环，再补最小真实 provider smoke，不扩全题型

## Delivered

1. `pdf-service` 增加资料分析 visual context / understanding / quality gate 数据结构和 mock 实现。
2. `backend` 将资料分析结果挂到 `question_quality.commercial_ocr`，并把 `data_analysis_quality_gate` 接入发布门禁。
3. `admin-web` 将 `/banks` 主入口切到 `/workbench`，旧 `/banks/:id/questions` 自动 redirect，workbench 显示 shared material、VLM、LLM、quality gate、bbox overlay。
4. `Playwright` 覆盖 admin workbench、旧路由 redirect、答案冲突需复核、H5 shared material 不丢。
5. post-closure 真实 smoke 已补跑：
   - `qwen_vl` 单 provider 在真实第 5 页资料分析表格页超时失败
   - `volcengine_ark_vl` 单 provider 成功解析 shared material + 16-20 题，并识别材料不完整
   - `qwen_vl -> Ark` 真实顺序成功 hedge
   - `qwen-plus` 对真实第 17 题给出低置信拒答，符合 quality gate 预期
6. `pdf-service/ai_client.py` 补了一个调度修复：当 `qwen_vl` 为主 provider 且 `Ark` 在可用列表中时，soft-timeout hedge 优先打到 `Ark`，不再被 `.env` 中的 `mimo_vl` 顺序卡住。

## Verification

- `pdf-service` targeted pytest: `21 passed`
- `pdf-service` provider fallback tests: `19 passed`
- `pdf-service` pipeline + fallback regression slice: `27 passed`
- `backend` workflow script: PASS
- `backend` build: PASS
- `admin-web` build: PASS
- `h5-web` build: PASS
- root Playwright: `9 passed`
- real provider health: `qwen_vl pass`, `volcengine_ark_vl pass`, `mimo_vl 429 fail`
- real visual smoke:
  - `qwen-only`: fail (`vision_page_timeout`)
  - `ark-only`: pass
  - `qwen->ark`: pass
  - current env order `qwen,mimo,ark` after hedge fix: pass
- real text smoke:
  - `qwen-plus` on real q17 payload: `can_understand_material=false`, `can_solve_question=false`, `comprehension_confidence=0.25`

## Evidence

- Detailed phase report: `docs/commercial-ocr-phase-reports/COCR-M20A-data-analysis-first.md`
- Playwright artifacts: `debug/e2e-commercial-ocr/2026-05-05T15-03-11-354Z/`
- Playwright traces: `test-results/`
- Real visual smoke: `debug/real-provider-smoke/20260505-real-smoke/`
- Real text smoke: `.agent/reports/data-analysis-q17-qwen-text-smoke.md`

## Risks

- 产品默认链路仍是 mock，真实 provider 只做 smoke，尚未切入发布主链
- Ark 当前可用，但 `ep-20260504082005-gvl4b` endpoint 本身对 responses API 返回 `403 AccessDenied`，实际成功依赖模型名 fallback `doubao-seed-2-0-lite-260215`
- `mimo_vl` 当前 real smoke 为 `429 quota exhausted`
- Legacy `page_understanding` / `semantic_groups` / `recrop_plan` still present for compatibility
- Backend has no generic `pnpm test` script
