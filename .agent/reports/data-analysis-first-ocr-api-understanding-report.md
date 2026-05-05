# Data Analysis First OCR API Understanding Report

## Summary

- Branch: `mimo`
- Baseline tag: `pre-data-analysis-ocr-api-first-20260505-221735`
- Implementation head before docs commit: `02b02bb`
- Scope: 仅完成资料分析 17-20 共用材料闭环，不扩全题型

## Delivered

1. `pdf-service` 增加资料分析 visual context / understanding / quality gate 数据结构和 mock 实现。
2. `backend` 将资料分析结果挂到 `question_quality.commercial_ocr`，并把 `data_analysis_quality_gate` 接入发布门禁。
3. `admin-web` 将 `/banks` 主入口切到 `/workbench`，旧 `/banks/:id/questions` 自动 redirect，workbench 显示 shared material、VLM、LLM、quality gate、bbox overlay。
4. `Playwright` 覆盖 admin workbench、旧路由 redirect、答案冲突需复核、H5 shared material 不丢。

## Verification

- `pdf-service` targeted pytest: `21 passed`
- `backend` workflow script: PASS
- `backend` build: PASS
- `admin-web` build: PASS
- `h5-web` build: PASS
- root Playwright: `9 passed`

## Evidence

- Detailed phase report: `docs/commercial-ocr-phase-reports/COCR-M20A-data-analysis-first.md`
- Playwright artifacts: `debug/e2e-commercial-ocr/2026-05-05T15-03-11-354Z/`
- Playwright traces: `test-results/`

## Risks

- Real VLM / LLM providers skipped by env; only mock contract verified
- Legacy `page_understanding` / `semantic_groups` / `recrop_plan` still present for compatibility
- Backend has no generic `pnpm test` script
