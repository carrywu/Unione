# Commercial OCR Phase Reports

本目录记录 `commercial OCR first + VLM/LLM semantic assembler` 主线的阶段化资产。当前所有迭代默认直接在 `main` 上推进，不再新建日常测试分支。

## 当前状态

| 阶段 | 文件 | 状态 | 结论 |
| --- | --- | --- | --- |
| M0 | `COCR-M0-baseline.md` | 已完成 | `GO_WITH_RISK` |
| M1 | `COCR-M1-merge-main-and-provider-baseline.md` | 已完成 | `GO_WITH_RISK` |
| M2 | `COCR-M2-mock-provider.md` | 已完成 | `GO` |
| M3 | `COCR-M3-ocr-normalizer.md` | 已完成 | `GO_WITH_RISK` |
| M4 | `COCR-M4-semantic-assembler.md` | 已完成 | `GO_WITH_RISK` |
| M5 | `COCR-M5-visual-understanding.md` | 规划中 | Pending |
| M6 | `COCR-M6-data-model.md` | 规划中 | Pending |
| M7 | `COCR-M7-quality-gate.md` | 已完成 | `GO_WITH_RISK` |
| M8 | `COCR-M8-tencent-ocr-adapter.md` | 已完成 | `GO_WITH_RISK` |
| M9 | `COCR-M9-review-ui.md` | 规划中 | Pending |
| M10 | `COCR-M10-eval-harness.md` | 规划中 | Pending |
| M11 | `COCR-M11-git-hygiene.md` | 规划中 | Pending |
| M12 | `COCR-M12-final-handoff.md` | 规划中 | Pending |

## 证据与归档

- 旧 `prd.json` 归档：`archive/prd-before-commercial-ocr-20260504-223958.json`
- 主 handoff：`/home/carry/project2/.agent/handoff/README.md`
- 夜间 handoff：`/home/carry/project2/.agent/handoff/commercial-ocr-overnight-20260504-2335.md`
- Agent phase 摘要：`/home/carry/project2/.agent/reports/commercial-ocr-main-handoff.md`
- Mock-only eval：`/home/carry/project2/pdf-service/debug/commercial-ocr-eval/20260504-233354/evaluation.json`

## 本轮范围

- 把 `ralph/xingce-e2e-git-hygiene-delivery` 安全合并到 `main`
- 清理 merge 历史中误跟踪的 `debug/**` runtime/raw response
- 读取本地百度 `paper_cut_edu` 示例代码并抽象 provider adapter
- 在 `pdf-service` 新增 `commercial_ocr` provider interface、fallback orchestrator、mock provider、百度 adapter、腾讯 SDK adapter、layout-only fallback
- 固化 deterministic fixture，并把 OCR normalizer、semantic assembler、quality gate 接入 commercial OCR execution summary

## 下一步

1. M5 引入 VLM visual understanding，只做图表/表头/跨页归属核验，不替代 OCR。
2. M8 后续 hardening：补真实 Tencent single-page smoke、429/backoff、更多 provider conflict 证据。
3. M9/M10 把 review UI / publish hard gate / eval harness 正式前推到业务链路。
