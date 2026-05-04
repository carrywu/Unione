# COCR-M0 Baseline

## 1. 本阶段目标

在不丢失现有 parser、M5A、M5B、review、publish 逻辑的前提下，把测试/验证分支安全并回 `main`，并记录商业 OCR 改造前的主链路基线。

## 2. 修改范围

- 合并前分支：`ralph/xingce-e2e-git-hygiene-delivery`
- 合并提交：`d411a90` (`merge: integrate validation branch into main`)
- 合并后卫生修复提交：`2fbf506` (`chore: stop tracking debug runtime artifacts`)
- 当前 baseline 主分支头：`2fbf506`
- 工作区治理：补强根 `.gitignore`，阻止 `.mcp.json`、`.ralph/`、`backend/uploads/`、`debug/**` runtime/raw response 再次入库

## 3. 架构变化

本阶段不引入商业 OCR 主链，只确认现状：

- PDF 入口仍由 `pdf-service/pipeline.py` 负责调度。
- 非 scanned question book 优先走 `MarkdownQuestionStrategy` / 既有策略。
- scanned question book 走 `parser_kernel` + 视觉页理解 fallback。
- M5A 真实答本对齐、M5B 相似题检测、admin review、publish 流程均保持现状。

现有 PDF 解析主链路：

1. `pipeline.parse_pdf`
2. `routing_decision` 判定 PDF 类型
3. `parse_extractor_with_kernel`
4. `normalize_pages -> annotate_semantics -> build_groups`
5. `validate_and_clean`
6. AI solver / review / publish 后续链

## 4. 数据结构

现有核心结构：

- `Question`
- `Material`
- `ParseStats`

本阶段只记录未来要接入的新增契约，不在 baseline 中启用：

- `MaterialGroup`
- `NormalizedQuestion`
- `ParseQualityGateResult`

## 5. 测试与验证

按要求执行的命令：

- `cd backend && pnpm test`
  - 结果：失败
  - 原因：`backend/package.json` 没有定义 `test` script
- `cd admin-web && pnpm build`
  - 结果：通过
- `cd pdf-service && python3 -m pytest tests/ -v`
  - 结果：失败
  - 原因：系统 `python3` 环境缺少 `fastapi`、`httpx`、`openai`、`fitz`、`pydantic` 等依赖，collection 阶段中断

补充验证：

- `cd backend && pnpm build`
  - 在 M1 阶段补跑
- `cd pdf-service && ./.venv/bin/python -m pytest ...`
  - 在 M1 阶段用于验证新增 commercial OCR 测试

## 6. 证据路径

- 旧 PRD 归档：`/home/carry/project2/docs/commercial-ocr-phase-reports/archive/prd-before-commercial-ocr-20260504-223958.json`
- 既有 M5A 报告：`/home/carry/project2/.agent/reports/m5a-answer-book-alignment-report.md`
- 既有 M5B 报告：`/home/carry/project2/.agent/reports/m5b-similarity-dedupe-report.md`
- 既有 provider fallback 报告：`/home/carry/project2/.agent/reports/provider-fallback-report.md`

## 7. 风险与遗留问题

- `provider timeout`：现有视觉 provider 仍存在超时成本
- `model selection`：既有视觉模型选择与 fallback 路径仍需继续梳理
- `API key loading`：多 provider env/runtime config 口径尚未统一
- `browser verification`：本轮未新增浏览器验收
- `backend pnpm test`：缺少脚本，无法作为稳定回归入口
- `python3 -m pytest`：系统 Python 缺依赖，不能直接代表项目 venv 状态

M5A 状态：

- 现有结论：`PASS`
- 说明：真实答本对齐链已存在，但尚未接入商业 OCR first 输入

M5B 状态：

- 现有结论：`PASS`
- 说明：相似题检测链已存在，但尚未接入商业 OCR provider trace

## 8. 回滚方案

1. `git revert 2fbf506`
2. `git revert -m 1 d411a90`
3. 如仅需停用商业 OCR 后续改动，保持 `main`，把 `COMMERCIAL_OCR_ENABLED=false`

## 9. 是否允许进入下一阶段

`GO_WITH_RISK`

允许进入 M1，但必须显式记录：

- backend 缺少 `pnpm test`
- 系统 Python 缺少 pdf-service 测试依赖
- provider timeout / model selection / API key loading / browser verification 仍是已知问题
