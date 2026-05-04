# E2E Test Matrix - 行测助手全链路

Generated: 2026-05-04 18:43:00 CST
Branch: ralph/xingce-e2e-git-hygiene-delivery

## Test Matrix

### 1. 题本上传 (US-011)

| # | Test Case | API/Page | Expected Result | Evidence Path | Automation |
|---|-----------|----------|-----------------|---------------|------------|
| 1.1 | 上传 20 页题本 PDF | `POST admin/pdf/parse` | task created, status=processing | `debug/e2e-upload/<taskId>/` | API + UI |
| 1.2 | 任务进度轮询 | `GET admin/pdf/task/:taskId` | progress updates, not stuck | `debug/e2e-upload/<taskId>/progress.json` | API poll |
| 1.3 | 最终状态 success | `GET admin/pdf/task/:taskId` | status=success, 20 pages parsed | `debug/e2e-upload/<taskId>/final.json` | API |
| 1.4 | 候选题数量 | `GET admin/pdf/task/:taskId/paper-candidates` | candidates >= 20 | `debug/e2e-upload/<taskId>/candidates.json` | API |
| 1.5 | UI 任务列表展示 | `/pdf/TaskListView` | task visible, status badge correct | `debug/e2e-upload/<taskId>/task-list.png` | Browser |
| 1.6 | UI 无 undefined | Browser | no `undefined`, `[object Object]`, `fixture_only` | screenshots | Browser |

### 2. 答本上传与 M5A 对撞 (US-012)

| # | Test Case | API/Page | Expected Result | Evidence Path | Automation |
|---|-----------|----------|-----------------|---------------|------------|
| 2.1 | 上传答本 PDF | `POST admin/banks/:bankId/answer-books` | task created | `debug/e2e-answer/<taskId>/` | API |
| 2.2 | 触发 M5A 匹配 | `POST admin/answer-books/:taskId/match` | match started | `debug/e2e-answer/<taskId>/match.json` | API |
| 2.3 | M5A 结果完整性 | `GET admin/pdf/task/:taskId/paper-candidates` | 每题有 matched/conflict/match_confidence/evidence/matched_answer_item_id | `debug/e2e-answer/<taskId>/m5a.json` | API |
| 2.4 | 无 BLOCKED_BY_MISSING | API response | no `BLOCKED_BY_MISSING_ANSWER_BOOK` | API response | API |
| 2.5 | 无 fixture_only | API response | no `fixture_only` in any field | API response | API |
| 2.6 | 20/20 有答本结果 | paper-candidates | all 20 questions have answer result | `debug/e2e-answer/<taskId>/coverage.json` | API |
| 2.7 | conflict 不自动覆盖 | review-state | conflict questions marked for human review | `debug/e2e-answer/<taskId>/conflict.json` | API |
| 2.8 | 已有任务验证 | task `836fec20-...` | M5A results visible | `debug/m5/836fec20-.../` | API |

### 3. M5B 历史撞库 (US-013)

| # | Test Case | API/Page | Expected Result | Evidence Path | Automation |
|---|-----------|----------|-----------------|---------------|------------|
| 3.1 | M5B 字段存在 | paper-candidates API | each question has M5B fields | `debug/e2e-m5b/<taskId>/m5b.json` | API |
| 3.2 | 候选类型覆盖 | API response | duplicate/near/sibling/similar at least one present | API response | API |
| 3.3 | 候选包含来源 | API response | candidate has history, score, source page, status | API response | API |
| 3.4 | 不同题不误判合并 | UI + API | distinct questions not auto-merged | screenshots | Browser + API |
| 3.5 | UI 展示候选 | PaperReviewView | duplicate/near/sibling/similar badges visible | screenshots | Browser |

### 4. 制卷核对页 (US-014)

| # | Test Case | API/Page | Expected Result | Evidence Path | Automation |
|---|-----------|----------|-----------------|---------------|------------|
| 4.1 | 进入制卷核对页 | `/pdf/PaperReviewView` | page loads, 20 questions visible | `debug/human-review/<taskId>/page.png` | Browser |
| 4.2 | 逐题遍历 | Browser | each question: stem, options, images, answer, analysis visible | `debug/human-review/<taskId>/q-*.png` | Browser |
| 4.3 | 题号连续 | Browser | Q1-Q20, no gaps, no duplicates | screenshots | Browser |
| 4.4 | 题干完整 | Browser | no truncation, no `undefined` | screenshots | Browser |
| 4.5 | 选项完整 | Browser | A/B/C/D all present and readable | screenshots | Browser |
| 4.6 | 图片归属 | Browser | images belong to correct question | screenshots | Browser |
| 4.7 | M5A/M5B 展示 | Browser | match status, candidates visible | screenshots | Browser |
| 4.8 | 状态徽标 | Browser | matched/conflict/pending badges | screenshots | Browser |
| 4.9 | 按钮可点击 | Browser | all action buttons responsive, no silent fail | screenshots | Browser |
| 4.10 | per-question JSON | API + Browser | `debug/human-review/<taskId>/per-question-review.json` | file | Script |

### 5. PDF 识别错误闭环 (US-015)

| # | Test Case | API/Page | Expected Result | Evidence Path | Automation |
|---|-----------|----------|-----------------|---------------|------------|
| 5.1 | 错误分类 | Manual review | 题目缺失/题干缺失/选项错误/图表裁切/图片归属/跨页/答案冲突/撞库误判/前端/发布 | `debug/manual-review/<taskId>/<qNo>/diagnosis.md` | Manual |
| 5.2 | 证据结构 | Per question | original-page.png, current-ui.png, api-response.json, page-understanding.json, semantic-groups.json, recrop-plan.json, diagnosis.md | `debug/manual-review/<taskId>/<qNo>/` | Script |
| 5.3 | 修复验证 | Code change | fix applied, regression test added | commit + test | Code |

### 6. 图表题与图片归属 (US-016)

| # | Test Case | API/Page | Expected Result | Evidence Path | Automation |
|---|-----------|----------|-----------------|---------------|------------|
| 6.1 | 图表题识别 | Browser + API | charts/tables not fragmented | screenshots | Browser |
| 6.2 | 图片完整性 | Browser | title, legend, axis, labels visible | screenshots | Browser |
| 6.3 | visual_parse_status | API | reasonable value (not null/error) | API response | API |
| 6.4 | visual_summary | API | descriptive summary present | API response | API |
| 6.5 | image linkage | API | images linked to correct questions | API response | API |

### 7. 发布入库 (US-017)

| # | Test Case | API/Page | Expected Result | Evidence Path | Automation |
|---|-----------|----------|-----------------|---------------|------------|
| 7.1 | 选择 matched 题发布 | `POST admin/pdf/task/:taskId/publish-result` | publish success | `debug/publish/<taskId>/publish.json` | API |
| 7.2 | conflict 不能批量发布 | API | conflict questions rejected or warned | API response | API |
| 7.3 | 发布后题库可见 | `GET admin/banks/:id` | questions appear in bank | `debug/publish/<taskId>/bank.json` | API |
| 7.4 | 发布状态回写 | admin-web UI | publish status updated | screenshots | Browser |
| 7.5 | 刷题端可见 | h5-web or API | stem, options, answer, analysis, images visible | `debug/publish/<taskId>/practice.json` | API/Browser |

### 8. 刷题端预览 (US-018)

| # | Test Case | API/Page | Expected Result | Evidence Path | Automation |
|---|-----------|----------|-----------------|---------------|------------|
| 8.1 | 找到刷题端 | h5-web startup | dev server starts | startup log | Script |
| 8.2 | 打开已发布题目 | Browser | question page loads | `debug/practice-preview/<taskId>/page.png` | Browser |
| 8.3 | 题干/选项/图片 | Browser | all elements rendered correctly | screenshots | Browser |
| 8.4 | 答案/解析逻辑 | Browser | answer shown after submit | screenshots | Browser |
| 8.5 | 移动端窄屏 | Browser (narrow) | responsive layout, no overflow | screenshots | Browser |

### 9. 异常状态测试

| # | Test Case | Trigger | Expected Result | Evidence Path | Automation |
|---|-----------|---------|-----------------|---------------|------------|
| 9.1 | Provider 超时 | Set low timeout | task continues with fallback, not stuck | logs | Config + API |
| 9.2 | Provider 429 | Rate limit hit | 429 provider skipped, fallback used | logs | Config + API |
| 9.3 | 任务卡 processing | Kill pdf-service mid-task | task recoverable via retry/cancel | `debug/task-recovery/` | API |
| 9.4 | PDF 解析失败 | Corrupt PDF | task status=failed, error message clear | API response | API |
| 9.5 | 前端 undefined | Check all pages | no `undefined` text in UI | screenshots | Browser |
| 9.6 | API 有数据 UI 不显示 | Compare API vs UI | UI matches API data | screenshots + API | Browser + API |

### 10. 任务 Cancel/Retry (US-010)

| # | Test Case | API/Page | Expected Result | Evidence Path | Automation |
|---|-----------|----------|-----------------|---------------|------------|
| 10.1 | 列出任务状态 | `GET admin/pdf/tasks` | tasks with processing/pending/failed/success listed | API response | API |
| 10.2 | Cancel 卡住任务 | `POST admin/pdf/cancel/:taskId` | task status=canceled | `debug/task-recovery/<ts>/cancel.json` | API |
| 10.3 | Retry 失败任务 | `POST admin/pdf/retry/:taskId` | task restarts, uses current provider order | `debug/task-recovery/<ts>/retry.json` | API |
| 10.4 | UI 任务状态 | TaskListView | status badges accurate | screenshots | Browser |

### 11. 回归测试 (US-019)

| # | Test Case | Command | Expected Result | Evidence Path |
|---|-----------|---------|-----------------|---------------|
| 11.1 | Backend test | `node -r ts-node/register -r tsconfig-paths/register test/pdf-review-workflow.test.ts` | PASS | `debug/regression/<ts>/` |
| 11.2 | Backend build | `npm run build` | PASS | `debug/regression/<ts>/` |
| 11.3 | Admin-web build | `npm run build` | PASS | `debug/regression/<ts>/` |
| 11.4 | PDF service test | `python -m pytest` or documented skip | PASS or documented reason | `debug/regression/<ts>/` |

### 12. 性能基线 (US-020)

| # | Test Case | Method | Expected Result | Evidence Path |
|---|-----------|--------|-----------------|---------------|
| 12.1 | 3-5 页 smoke | Upload small PDF | per-page timing recorded | `debug/performance/<ts>/` |
| 12.2 | 20 页全链路 | Upload 题本篇.pdf | total time, per-page time, provider time | `debug/performance/<ts>/` |
| 12.3 | 瓶颈分析 | Logs + timing | identify slowest provider/page | `debug/performance/<ts>/performance-baseline.md` |

## Automation Strategy

- **API tests**: curl or fetch scripts, save responses as JSON evidence
- **Browser tests**: Playwright or manual browser with screenshots
- **Build verification**: npm run build for backend + admin-web
- **Performance**: timestamps from pdf-service logs + backend logs
