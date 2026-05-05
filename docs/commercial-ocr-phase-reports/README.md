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
| M5 | `COCR-M5-visual-understanding-backend.md` | 已完成 | `GO_WITH_RISK` |
| M6 | `COCR-M6-data-model.md` | 规划中 | Pending |
| M7 | `COCR-M7-quality-gate.md` | 已完成 | `GO_WITH_RISK` |
| M8 | `COCR-M8-tencent-ocr-adapter.md` | 已完成 | `GO_WITH_RISK` |
| M8b | `COCR-M8b-backend-provider-wiring.md` | 已完成 | `GO_WITH_RISK` |
| M9 | `COCR-M9-admin-review-ui-publish-gate.md` | 已完成 | `GO_WITH_RISK` |
| M10 | `COCR-M10-full-chain-playwright-e2e.md` | 已完成 | `GO_WITH_RISK` |
| M11b | `COCR-M11b-known-regression-cleanup.md` | 已完成 | `GO` |
| M12 | `COCR-M12-overnight-final-report.md` | 已完成 | `GO_WITH_RISK` |
| M20A | `COCR-M20A-data-analysis-first.md` | 已完成 | `GO_WITH_RISK` |
| M20C | `COCR-M20C-real-data-multipage-data-analysis.md` | 已完成 | `GO_WITH_RISK` |

## 证据与归档

- 旧 `prd.json` 归档：`archive/prd-before-commercial-ocr-20260504-223958.json`
- 主 handoff：`/home/carry/project2/.agent/handoff/README.md`
- 夜间 handoff：`/home/carry/project2/.agent/handoff/commercial-ocr-full-chain-e2e-20260505-0147.md`
- Agent phase 摘要：`/home/carry/project2/.agent/reports/commercial-ocr-main-handoff.md`
- Full-chain E2E 摘要：`/home/carry/project2/.agent/reports/commercial-ocr-full-chain-e2e-report.md`
- Mock-only eval：`/home/carry/project2/pdf-service/debug/commercial-ocr-eval/20260504-233354/evaluation.json`

## 本轮范围

- 在 backend 接入 provider/material/quality gate/visual understanding DTO，并把 publish gate 前推到 review / draft / preview publish
- 在 admin-web 展示 provider、shared material、quality gate、grouping evidence、similarity 空状态/候选状态
- 在 h5-web 验证 17-20 shared material 预览做题体验
- 用 Playwright 保存 admin + h5 全链路截图 / trace / console / network 证据
- 清理 provider health / visual smoke 既有回归，`pdf-service` 全量 pytest 重新回到绿色

## 下一步

1. 用真实 VLM 替换 selected-case mock visual understanding，并补跨页 / 图例 / 表头核验。
2. 做 M8 真实 adapter hardening：补 Tencent/Baidu single-page smoke、429/backoff、provider conflict 证据。
3. 收敛 warning case 的人工放行策略，并决定是否允许正式 publish。
4. 在拿到真实百度或腾讯 OCR key 后，把当前 `tesseract_local_ocr` 多页发现/导入替换成真实 OCR provider 的同口径批量验证。
