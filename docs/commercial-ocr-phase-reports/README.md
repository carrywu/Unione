# Commercial OCR Phase Reports

本目录记录 `commercial OCR first + VLM/LLM semantic assembler` 主线的阶段化资产。当前所有迭代默认直接在 `main` 上推进，不再新建日常测试分支。

## 当前状态

| 阶段 | 文件 | 状态 | 结论 |
| --- | --- | --- | --- |
| M0 | `COCR-M0-baseline.md` | 已完成 | `GO_WITH_RISK` |
| M1 | `COCR-M1-merge-main-and-provider-baseline.md` | 已完成 | `GO_WITH_RISK` |
| M2 | `COCR-M2-mock-provider.md` | 规划中 | Pending |
| M3 | `COCR-M3-ocr-normalizer.md` | 规划中 | Pending |
| M4 | `COCR-M4-semantic-assembler.md` | 规划中 | Pending |
| M5 | `COCR-M5-visual-understanding.md` | 规划中 | Pending |
| M6 | `COCR-M6-data-model.md` | 规划中 | Pending |
| M7 | `COCR-M7-quality-gate.md` | 规划中 | Pending |
| M8 | `COCR-M8-real-paper-cut-adapter.md` | 规划中 | Pending |
| M9 | `COCR-M9-review-ui.md` | 规划中 | Pending |
| M10 | `COCR-M10-eval-harness.md` | 规划中 | Pending |
| M11 | `COCR-M11-git-hygiene.md` | 规划中 | Pending |
| M12 | `COCR-M12-final-handoff.md` | 规划中 | Pending |

## 证据与归档

- 旧 `prd.json` 归档：`archive/prd-before-commercial-ocr-20260504-223958.json`
- 主 handoff：`/home/carry/project2/.agent/handoff/README.md`
- Agent phase 摘要：`/home/carry/project2/.agent/reports/commercial-ocr-main-handoff.md`

## 本轮范围

- 把 `ralph/xingce-e2e-git-hygiene-delivery` 安全合并到 `main`
- 清理 merge 历史中误跟踪的 `debug/**` runtime/raw response
- 读取本地百度 `paper_cut_edu` 示例代码并抽象 provider adapter
- 在 `pdf-service` 新增 `commercial_ocr` provider interface、fallback orchestrator、mock provider、百度 adapter、腾讯 stub
- 预留 `MaterialGroup` / `NormalizedQuestion` / `ParseQualityGateResult` 数据契约

## 下一步

1. M2 把 mock provider 输出升级为更接近真实 OCR block fixture。
2. M3/M4 建立 OCR normalizer 与 semantic assembler，把 `17-20` 共用材料题编组成稳定结构。
3. M7 把 parse quality gate 接进 publish 前门禁，禁止只靠 `question_count` 判成功。
