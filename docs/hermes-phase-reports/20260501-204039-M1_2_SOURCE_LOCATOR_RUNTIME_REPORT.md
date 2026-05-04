# M1.2 Source Locator / Paper Review Runtime Report

生成时间：2026-05-01 21:43 本地复核后
工作目录：`/Users/apple/Downloads/公考/project2`
分支：`hermes/pdf-production-pipeline`

## 1. 结论

M1.2 runtime gate 已按“source evidence 不可靠时 fail closed”的原则收紧：

- `source_unverified` / `question_not_found_in_pdf` / `ghost_candidate_possible` / 缺 `source_text_span` 时，不再允许 `manualForceAddAllowed=true`。
- paper review 候选题即使还有 `source_bbox` / `source_page_refs`，只要缺关键 `source_text_span`，也判定不可人工强制加入。
- draft 创建/更新仍通过后端 canonical candidates 重新校验，不信任前端伪造的 `manualForceAddAllowed` / `manualReviewable` / `can_add_to_paper` / `source_locator_available`。
- visual debug report 已覆盖 case 中 q1~q10，不再只输出前 7 题。

当前 all/default 验收仍返回非 0，但已判定为 expected fail：失败原因是 `main_positive_fixture` 的资料分析题仍出现 `partial_pdf_context` / `missing_previous_page_context` / material evidence 缺失；不是 source gate 放行问题。当前表现是安全失败：相关题均不能自动入卷，也不能人工强制加入。

按当前规则：不 commit、不 push。原因：all/default 仍是 expected fail，且本轮没有用户显式授权 commit/push；建议保留为本地 WIP，待用户确认是否提交 WIP checkpoint。

## 2. 关键代码行为

### backend/src/modules/pdf/pdf.service.ts

已完成：

- `source_locator_available` 不再硬编码为 false，而是基于 task file/source page refs/source bbox/source text span 等 evidence 计算。
- `manualReviewable` / `manualForceAddAllowed` 依赖后端重算结果：
  - AI passed + source evidence 完整 => 可自动入卷。
  - AI warning + source evidence 完整 => 可人工核验，可 manual force add。
  - 缺 source evidence/source locator/source text span，或存在 source_unverified/question_not_found/ghost candidate/partial context 等风险 => 不可人工核验，不可 manual force add。
- `createDraftPaper` / `updateDraftPaper` 通过 canonical candidates 校验请求题目，拒绝前端伪造可加题字段。

新增/强化点：

- `paperDraftCandidateCanBeAdded(...)` 要求 candidate 的真实 source locator 与 source evidence 完整。
- `paperCandidateManualReviewDecision(...)` 对缺 `source_text_span`、`source_unverified`、`question_not_found_in_pdf`、`ghost_candidate_possible`、`partial_pdf_context` 等风险 fail closed。

### backend/test/pdf-review-workflow.test.ts

已覆盖：

- source evidence 完整 + AI passed 可自动入卷。
- source evidence 完整 + AI warning 可人工核验/强制加入。
- 缺 source evidence 时不可人工核验/不可强制加入。
- 前端伪造 `manualForceAddAllowed=true` 不能绕过 create draft。
- 前端伪造 `manualForceAddAllowed=true` 不能绕过 update draft。
- 新增缺 `source_text_span` 时拒绝 manual force add 的 regression。

### pdf-service/debug_tools/export_visual_debug.py

已移除只输出前 7 题的过滤逻辑，visual debug report 现在输出 case 中全部题号。

### pdf-service/tests/test_pdf_review_flow_rules.py

已新增/扩展 `render_report` regression，锁定 q8/q9/q10 不会被过滤。

## 3. 已运行验证

### 3.1 backend workflow regression

命令：

```bash
cd /Users/apple/Downloads/公考/project2/backend && npx ts-node -r tsconfig-paths/register test/pdf-review-workflow.test.ts
```

结果：pass，exit code 0。

### 3.2 pdf-service unittest

命令：

```bash
cd /Users/apple/Downloads/公考/project2/pdf-service && .venv/bin/python -m unittest discover -s tests -p 'test*.py'
```

结果：pass，exit code 0。

备注：此前同一轮记录过 `Ran 85 tests ... OK`，有非阻塞 DeprecationWarning。

### 3.3 visual debug

命令：

```bash
cd /Users/apple/Downloads/公考/project2/pdf-service && .venv/bin/python debug_tools/export_visual_debug.py --case debug_tools/cases/example_1_10.yml --out debug_artifacts/example_1_10
```

结果：pass。

输出：

```text
Visual debug PASS: 0 failed assertions
Artifacts: debug_artifacts/example_1_10
```

### 3.4 diff whitespace check

命令：

```bash
cd /Users/apple/Downloads/公考/project2 && git diff --check
```

结果：pass，exit code 0。

### 3.5 fixture scripts syntax check

命令：

```bash
cd /Users/apple/Downloads/公考/project2 && node --check scripts/check-pdf-fixtures.mjs
cd /Users/apple/Downloads/公考/project2 && node --check scripts/check-paper-review-recognition.mjs
```

结果：均 pass，exit code 0。

### 3.6 fixture governance + negative regression

命令：

```bash
cd /Users/apple/Downloads/公考/project2 && node scripts/check-pdf-fixtures.mjs
cd /Users/apple/Downloads/公考/project2 && OUTPUT_DIR="$PWD/debug/hermes/20260501-204039/negative-regression-after-gate-fix" FIXTURE_ROLE=partial_pdf_context_negative_regression node scripts/check-paper-review-recognition.mjs
```

结果：pass，exit code 0。

negative regression 关键语义：

- `canAutoCompose=false`
- candidate 可加题数量为 0
- q8/q9/q10 保持 `partial_pdf_context` / `missing_previous_page_context`
- `manualReviewable=false`
- `manualForceAddAllowed=false`
- UI 展示无法人工核验原因，并建议补齐上一页或使用完整 PDF 重新解析

### 3.7 all/default recognition suite

命令：

```bash
cd /Users/apple/Downloads/公考/project2 && OUTPUT_DIR="$PWD/debug/hermes/20260501-204039/all-default-after-gate-fix" node scripts/check-paper-review-recognition.mjs
```

结果：exit code 1。

`full-matrix-report.json`：

```json
{
  "fixtureGovernance": "pass",
  "mainPositiveRecognition": "fail",
  "negativeRegression": "pass",
  "uiRuleHardening": "pass",
  "overall": "fail",
  "exitCodeShouldBeNonZero": true
}
```

main-positive stderr：

```text
Recognition audit failed: main_positive_fixture 第 8 题仍出现 partial/missing previous page context
```

all/default 产物：

- `/Users/apple/Downloads/公考/project2/debug/hermes/20260501-204039/all-default-after-gate-fix/full-matrix-report.json`
- `/Users/apple/Downloads/公考/project2/debug/hermes/20260501-204039/all-default-after-gate-fix/main-positive/recognition-audit.json`
- `/Users/apple/Downloads/公考/project2/debug/hermes/20260501-204039/all-default-after-gate-fix/negative-regression/recognition-audit.json`

## 4. all/default expected fail 判定

判定：expected fail。

原因：

1. suite 的非 0 只来自 `main_positive_fixture`。
2. `fixtureGovernance=pass`、`negativeRegression=pass`、`uiRuleHardening=pass`。
3. main-positive 的失败原因是第 8 题仍带 `partial_pdf_context` / `missing_previous_page_context`，属于材料/跨页上下文 evidence 尚未补齐的问题。
4. 失败不是 gate 漏放：q1/q8/q9/q10 的 `manualReviewable` 和 `manualForceAddAllowed` 均为 false，`can_add_to_paper` 均为 false。
5. q1 的 `source_unverified` / `question_not_found_in_pdf` / `ghost_candidate_possible` 已被正确拦截：
   - `uiStatus=AI warning`
   - `manualReviewable=false`
   - `manualForceAddAllowed=false`
   - `can_add_to_paper=false`
   - UI 展示“无法人工核验：缺少原卷定位/source_text_span/source_bbox，不能确认题目来源”
6. q8/q9/q10 的资料分析上下文风险也 fail closed：
   - `manualReviewable=false`
   - `manualForceAddAllowed=false`
   - `can_add_to_paper=false`
   - UI 展示“资料分析题缺少材料组或图表证据，当前 PDF 片段无法核验”
   - recommended action 是补齐上一页或使用完整 PDF 重新解析

因此，all/default 当前不是生产通过状态，但 M1.2 的 runtime gate 目标已达到“高风险状态不自动入卷、不允许人工强制加入”。后续要让 all/default 变绿，需要进入材料/跨页 source evidence 补齐工作，而不是放宽 gate。

## 5. 当前服务状态

本轮复核时监听状态：

- backend：node 监听 `*:3010`
- admin-web：node 监听 `127.0.0.1:5173`
- pdf-service：Python 监听 `127.0.0.1:8001`，health 返回 `{"status":"ok"}`

## 6. 当前 git 状态

最近状态：

```text
 M backend/src/modules/pdf/pdf.service.ts
 M backend/test/pdf-review-workflow.test.ts
 M pdf-service/debug_tools/export_visual_debug.py
 M pdf-service/tests/test_pdf_review_flow_rules.py
?? deep-research-report.md
```

diff stat：

```text
backend/src/modules/pdf/pdf.service.ts          | 158 +++++++++++++--
backend/test/pdf-review-workflow.test.ts        | 248 +++++++++++++++++++++++-
pdf-service/debug_tools/export_visual_debug.py  |   2 -
pdf-service/tests/test_pdf_review_flow_rules.py |  32 ++-
4 files changed, 412 insertions(+), 28 deletions(-)
```

`deep-research-report.md` 是既有未跟踪文件，本轮未读取、未修改、未删除。

## 7. 风险与后续

剩余风险：

1. all/default 仍为非 0：main-positive fixture 的资料分析题仍被判 `partial_pdf_context` / `missing_previous_page_context`。
2. paper review 页面仍报告 `paperReviewHasOriginalPdfLocator=false`；当前 gate 因此正确 fail closed，但原卷 locator UI/材料 evidence 仍需后续修复。
3. q1 stored question 与 paper-review candidate 的 AI 状态来源仍不完全一致：stored question 可显示 passed，而 paper-review candidate 已按 source evidence 降为 warning；需要后续统一状态来源。
4. patch 工具 lint 曾暴露 TypeScript decorator/tsconfig 环境类 TS1240 问题，判断非本轮业务修改直接引入。
5. pdf-service unittest 有非阻塞 DeprecationWarning。

建议下一步：

- 不放宽 gate。
- 若要 all/default 变绿，应补齐 source_text_span / original PDF locator / 资料分析 material group / 跨页 evidence。
- 本轮只作为 M1.2 runtime gate WIP checkpoint；是否 commit/push 由用户决定。

## 8. commit/push 决策

本轮未 commit，未 push。

决策：暂不自动 commit/push。

理由：

- all/default suite 仍非 0，虽然语义上是 expected fail，但还不是完整 green acceptance。
- 用户此前约定不自动 commit/push。
- 当前修改适合作为 WIP checkpoint；如用户明确要求，可以再提交一个 WIP commit，并在 commit message/report 中标明 all/default expected fail。