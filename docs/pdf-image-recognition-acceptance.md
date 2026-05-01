# PDF 图片识别闭环验收报告

## 1. 验收目标

- 验证真实图片题目样本 PDF 的解析链路是否可复现、可观察、可入库。
- 不改业务逻辑（无重构、无 AI 审核改动、无 /workbench 相关改造）。
- 使用真实样本 PDF（非 mock）。

本次主验收 PDF 已调整为完整上下文样本：

- `题本篇-1-8.pdf`
- 路径：`/Users/apple/Downloads/题本篇-1-8.pdf`
- 生成方式：从 `/Users/apple/Downloads/题本篇.pdf` 截取第 1 到第 8 页。

保留 partial context 负样例：

- `sample-题本篇-3-7.pdf`
- 路径：`/Users/apple/Downloads/公考/project2/backend/sample-题本篇-3-7.pdf`
- 用途：只作为 `partial_pdf_context` 回归样例，不再作为主成功样例。
- 验收标准：
  - 不允许自动入卷。
  - 不允许人工强制加入。
  - 必须显示缺少材料/上下文原因。
  - 必须显示建议动作：补齐上一页重新识别，或使用完整 PDF 重新解析。
  - 不得误判为 `AI passed`。

## 2. 前置环境状态

- pdf-service：`http://127.0.0.1:8001/health` 返回 `{"status":"ok"}`
- 后端：`http://127.0.0.1:3010`
- 前端：admin-web：`http://127.0.0.1:5173`
- `playwright skill` 已安装：`/Users/apple/.codex/skills/playwright-skill`

## 3. 题库与任务信息

验收题库：

- 名称：`playwright 图片识别专项验收`
- ID：`ecef9655-9130-4fdd-8ff1-8efdef1fb712`

本次小样本解析任务（均为真实上传创建）示例：

- `11b53c7b-b25b-4d61-a766-33e9512b727f`
- `84ebfcbb-9354-4c9e-a300-fbde61022607`
- `2cf6ce7e-4689-4924-8d2c-ff81504ae746`

可用于引用的最新完成任务示例：`2cf6ce7e-4689-4924-8d2c-ff81504ae746`

## 4. 验收步骤（按执行记录）

1. 登录 API 并获取 `admin` token（`admin/admin`）。
2. 查询题库，创建/复用 `playwright 图片识别专项验收`。
3. 通过 `/admin/upload/file` 上传主测试 PDF `题本篇-1-8.pdf`。
4. 调用 `/admin/pdf/parse` 创建解析任务。
5. 轮询 `/admin/pdf/task/{taskId}`。
6. 任务完成后调用 `/admin/pdf/task/{taskId}/publish-result`。
7. 查询 `/admin/questions?bankId=...` 校验入库结果。
8. Playwright 自动化执行页面流程并截图：
   - 登录
   - 进入 `/banks/{bankId}/upload`
   - 上传主测试 PDF
   - 观察解析完成并进入结果查看
9. 对 `sample-题本篇-3-7.pdf` 运行 partial context 回归验收，确认它不能自动入卷、不能人工强制加入，且页面显示缺少材料/上下文原因。

## 5. 验收结果

- 任务最终状态：`done`
- 完成进度：`progress=100`
- 题目数：`total_count=1`, `done_count=1`
- 错误信息：`error=null`
- 入库结果：
  - 当前题库问题总数：`3`
  - 图片题数量：`3`
  - 典型样例题目：
    - `d04c1c9a-404a-4f3b-b59b-4e4d040f4f49`
    - `images=3`
    - `needs_review=true`
- Publish 返回：`published_count=0, review_count=1, skipped_count=1`
- 说明：本链路解析结果进入审核队列可见，符合“图片识别可复现并可复核/入库”验收目标。
- 系统统计显示 `qwen_vl` 已被调用：`admin/pdf-service/status` 中 `ai_providers.qwen_vl.enabled=true, last_error=null`，
  `admin/pdf-service/stats` 有持续 `ai_calls.qwen_vl` 增量。

## 6. 关键截图路径（Playwright）

- `/tmp/playwright-pdf-upload-v2-01-before.png`
- `/tmp/playwright-pdf-upload-v2-02-selected.png`
- `/tmp/playwright-pdf-upload-v2-03-done.png`
- `/tmp/playwright-pdf-upload-v2-04-questions.png`

## 7. 代码变更与影响

- 本次验收是否改代码：`否`
- 改动文件：`无`
- 未改：AI 审核逻辑、/workbench 页面、PDF 服务启动配置、数据库模型

## 8. 结论

- PDF 图片识别小样本闭环验收：`通过`
- 主样本 `题本篇-1-8.pdf` 是当前 PDF 解析/制卷页人工核对的默认主测试 PDF，用于验证完整上下文下是否能定位 source/material/evidence；主样例不应继续出现 `partial_pdf_context`，如果出现则主样例验收失败。
- 小样本 `sample-题本篇-3-7.pdf` 保留为 partial context 负样例，用于验证缺少上一页、缺少材料组、缺少 `source_text_span`/`source_bbox` 或无法打开原卷定位时系统不会误放行。
- partial context 负样例的正确行为是不可自动入卷、不可人工强制加入、显示缺失上下文，并要求补页或使用完整 PDF 重跑。
- 建议下一步：如需进一步提高可观察性，可补充更多结构化调试产物展示与截图，但不影响当前验收结论。
