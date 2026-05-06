# COCR-M15～M19 第六步长链路托管提示词

> 用途：发给当前 `mimo` 分支上的托管式 Agent / MiMo 开发 Agent。  
> 总目标：从 COCR-M14 已完成的全链路 E2E 基线继续推进，不止做到第 5 步，而是推进到**第 6 步：全量回归、报告、合并 main 准备、可交付验收**。  
> 默认策略：`mock_commercial_ocr + mock MiMo reviewer`，不默认调用真实百度、腾讯、MiMo API。

---

## 0. 角色与当前基线

你是当前 `mimo` 分支上的全权托管式工程 Agent。用户不想一直盯 CLI，也不想每一步都确认。你必须基于当前 COCR-M14 成果，自主推进 COCR-M15～COCR-M19 长链路任务，直到完成**第 6 步：全量回归、交付报告、handoff、push 当前分支、合并 main 准备**。

项目根路径：

```bash
/home/carry/project2
```

当前分支：

```bash
mimo
```

当前基线：

- 最新已知 commit：`90099ea`
- 已 push：`origin/mimo`
- COCR-M14 已完成
- PostgreSQL 16 Docker：healthy，port `5432`
- Redis 7 Docker：healthy，port `6379`
- backend `3010`：`status=ok`，`db=connected`，`redis=connected`，`pdf-service=online`
- pdf-service `8001`：ok
- admin-web `5174`：200
- h5-web `5173`：200
- Playwright E2E：
  - Admin `2/2 passed`
  - H5 `1/1 passed`
  - Total `3/3 passed`
- MiMo reviewer：
  - text review `mimo-v2.5-pro`：skipped by env / mock
  - visual review `mimo-v2.5`：skipped by env / mock
  - 模型分工正确：`mimo-v2.5-pro` 未传图片
- 回归：
  - pdf-service：`151 passed / 2 skipped / 1 flaky`
  - backend build：PASS
  - backend test：PASS
  - admin-web build：PASS
  - h5-web build：PASS
- 已有环境脚本：
  - `docker-compose.e2e.yml`
  - `scripts/e2e/start-commercial-ocr-stack.sh`
  - `scripts/e2e/stop-commercial-ocr-stack.sh`
- 已有 COCR-M14 报告和 handoff

重要模型分工，必须严格遵守：

- `mimo-v2.5` 有视觉能力，用于截图、图片、页面视觉评审。
- `mimo-v2.5-pro` 不按视觉模型使用，只用于文本/JSON/API payload 推理评审。
- 不要给 `mimo-v2.5-pro` 传图片。
- 默认继续使用 mock MiMo reviewer。
- 只有 `MIMO_ENABLED=true`、`MIMO_REAL_SMOKE=true`、`MIMO_API_KEY` 存在时，才允许真实 MiMo 最小 smoke。
- 真实 MiMo smoke 最多评审 1～2 张关键截图 + 1 个 JSON payload，避免额度消耗。
- 真实 MiMo 失败、429、timeout、auth error 时，自动降级 mock/skipped，不阻塞 E2E 主流程。

安全要求：

- 不提交 `.env`。
- 不提交 API key / token / secret。
- 不提交百度/腾讯/MiMo key。
- 不提交 raw provider response。
- 不提交 debug/e2e 截图、trace、视频大文件。
- 不提交题本/答本/raw 上传文件。
- 百度 Key 曾明文暴露，报告中继续提醒轮换。
- 真实外部 API 默认跳过。

---

## 1. 总目标：从第 1 步推进到第 6 步

本轮不是只做一个小功能，而是继续托管推进到**第 6 步：全量回归、交付报告、合并 main 准备**。

六步目标如下：

### 第 1 步：环境编排复验

确认并复用 COCR-M14 已经跑通的环境：

- PostgreSQL 16
- Redis 7
- backend
- pdf-service
- admin-web
- h5-web

验收：

- MySQL/PostgreSQL 可连接，按项目当前实际使用为准。COCR-M14 当前为 PostgreSQL 16。
- Redis 可连接。
- backend `/api/health` 成功。
- pdf-service `/health` 成功。
- admin-web 可打开。
- h5-web 可打开。
- 启动/停止脚本可复用。

### 第 2 步：后端链路接入复验

确认：

- mock commercial OCR 结果能进入 backend review DTO。
- `material_groups`、`quality_gate`、`provider_result` 能透传。
- publish gate 对不完整题有效。
- 17-20 shared material 保留。
- M5A / M5B 不被绕过。

### 第 3 步：admin-web 真人审核 E2E

Playwright 像真人一样测试 admin：

- 进入 admin。
- 触发 mock parse task 或上传测试 PDF。
- 查看 provider 信息。
- 查看 17-20 共用材料。
- 查看 quality gate。
- 验证 publish gate。
- 验证 force publish。
- 验证相似题区域。

### 第 4 步：h5-web 移动端 E2E

Playwright 模拟手机端：

- 进入发布后的题目/试卷。
- 17-20 shared material 不丢。
- 做题、提交、查看答案解析。
- 移动端无明显遮挡/横向溢出。

### 第 5 步：MiMo 视觉/文本评审闭环

- Playwright 产出截图和 JSON。
- `mimo-v2.5` 评审截图。
- `mimo-v2.5-pro` 评审 JSON/API payload。
- 输出 visual review JSON 和 text review JSON。
- 发现 blocking issue 时自动修复并回归；修不了就写 BLOCKED 报告和 handoff。

### 第 6 步：全量回归、报告、合并 main 准备

这是本轮最终目标：

- 跑全量回归。
- 确认 backend/admin/h5/pdf-service 全部可交付。
- 整理报告、progress、prd、handoff。
- push `origin/mimo`。
- 生成合并回 main 的明确方案。
- 不自动合并 main，除非用户明确要求。

---

## 2. 本轮阶段命名

请按以下阶段推进：

- **COCR-M15**：force publish + MiMo real-smoke/mocked review hardening
- **COCR-M16**：admin H5-real-preview integration
- **COCR-M17**：admin-preview 与 h5-web 一致性 Playwright E2E
- **COCR-M18**：全量回归、稳定性与合并 main 准备
- **COCR-M19**：第六步最终交付报告与 handoff

报告路径：

```text
docs/commercial-ocr-phase-reports/COCR-M15-force-publish-mimo-review-hardening.md
docs/commercial-ocr-phase-reports/COCR-M16-admin-h5-real-preview.md
docs/commercial-ocr-phase-reports/COCR-M17-admin-preview-h5-consistency-e2e.md
docs/commercial-ocr-phase-reports/COCR-M18-full-regression-merge-readiness.md
docs/commercial-ocr-phase-reports/COCR-M19-step6-final-delivery.md
```

最终汇总报告：

```text
.agent/reports/mimo-commercial-ocr-step6-final-report.md
.agent/handoff/mimo-step6-final-handoff-<timestamp>.md
```

每份报告必须包含：

1. 阶段目标
2. 修改范围
3. 架构/API/数据结构变化
4. 测试与验证命令
5. Playwright/MiMo 证据路径
6. 风险与遗留问题
7. 回滚方案
8. 结论：`GO` / `GO_WITH_RISK` / `BLOCKED`

---

## 3. 托管执行原则

你必须自主推进，不要中途问用户“是否继续”。

允许你自行：

- 安装依赖
- 启动/停止 PostgreSQL/Redis/backend/pdf-service/admin/h5
- 使用现有 `docker-compose.e2e.yml`
- 修复启动脚本
- 处理端口冲突
- 补 seed/mock 数据
- 补 Playwright spec
- 补 admin H5 preview 路由/组件
- 补 h5-web 可复用 preview renderer
- 补 backend preview API
- 补 publish/preview DTO
- 补 force publish 审计字段
- 补 MiMo evidence reviewer 脚本
- 补测试
- 更新 `.env.example`
- 更新 `.gitignore`
- 分阶段 commit
- push `origin/mimo`

遇到阻塞：

1. 先自己修复。
2. 修复不了就用 mock / fixture / synthetic data 降级。
3. 仍无法推进就写 BLOCKED 报告。
4. BLOCKED 报告必须包含：
   - 当前完成到哪个阶段
   - 失败命令
   - 错误摘要
   - 证据路径
   - 手动恢复命令
   - 下一轮 resume prompt

不要空等，不要卡住不产出。

---

## 4. 开始前检查

先执行：

```bash
pwd
git branch --show-current
git status --short
git log --oneline -12
```

确认当前在 `mimo` 分支。不要直接切 main 开发。

读取：

```text
prd.json
progress.txt
ralph.yaml

.agent/handoff/mimo-full-chain-e2e-*.md
.agent/handoff/mimo-reviewer-*.md
.agent/reports/commercial-ocr-main-handoff.md

docs/commercial-ocr-phase-reports/COCR-M13-*.md
docs/commercial-ocr-phase-reports/COCR-M14-*.md
docs/commercial-ocr-phase-reports/COCR-M0-baseline.md
docs/commercial-ocr-phase-reports/COCR-M1-merge-main-and-provider-baseline.md
docs/commercial-ocr-phase-reports/COCR-M2-mock-provider.md
docs/commercial-ocr-phase-reports/COCR-M3-ocr-normalizer.md
docs/commercial-ocr-phase-reports/COCR-M4-semantic-assembler.md
docs/commercial-ocr-phase-reports/COCR-M7-quality-gate.md
docs/commercial-ocr-phase-reports/COCR-M8-tencent-ocr-adapter.md
```

重点理解：

```text
pdf-service/commercial_ocr/**
pdf-service/commercial_ocr/mimo_reviewer.py
pdf-service/pipeline.py
pdf-service/models.py
pdf-service/main.py
pdf-service/monitor.py
pdf-service/tests/test_mimo_reviewer.py
pdf-service/tests/fixtures/commercial_ocr/**

backend/src/modules/system/health.controller.ts
backend/src/modules/pdf/**
backend/src/modules/question/**
backend/src/modules/review/**
backend/src/modules/publish/**
backend/src/**/*.ts

admin-web/src/**
h5-web/src/**
```

重点搜索：

```text
preview
publish
paper
question bank
review
H5
mobile
material
sharedStem
material_id
quality_gate
forcePublish
iframe
renderer
question renderer
paper preview
```

不要凭空重写已有架构，优先复用现有模块。

---

## 5. 环境启动与复验

使用已有环境：

```text
docker-compose.e2e.yml
scripts/e2e/start-commercial-ocr-stack.sh
scripts/e2e/stop-commercial-ocr-stack.sh
```

启动并验证：

- PostgreSQL 16
- Redis 7
- backend
- pdf-service
- admin-web
- h5-web

health：

```text
backend: http://127.0.0.1:3010/api/health
pdf-service: http://127.0.0.1:8001/health
admin-web: http://127.0.0.1:5174
h5-web: http://127.0.0.1:5173
```

端口以实际配置为准。

环境默认：

```bash
COMMERCIAL_OCR_ENABLED=true
PDF_PARSE_PRIMARY_PROVIDER=mock_commercial_ocr
PDF_PARSE_FALLBACK_PROVIDERS=local_parser,mock_commercial_ocr
MIMO_ENABLED=false
MIMO_TEXT_MODEL=mimo-v2.5-pro
MIMO_VISION_MODEL=mimo-v2.5
MIMO_REAL_SMOKE=false
```

真实 MiMo smoke 只在显式 env 开启时执行：

```bash
MIMO_ENABLED=true
MIMO_REAL_SMOKE=true
MIMO_API_KEY=...
```

---

## 6. COCR-M15：force publish + MiMo reviewer hardening

目标：补齐 force publish E2E 和 MiMo reviewer 自动化证据闭环。

### 6.1 force publish 策略复验

当前策略基线：

硬阻止：

- `answer=null`
- `layout-only`
- `incomplete material`

软放行：

- `needs_review`
- `warnings`
- `fallback_used`
- `analysis=unknown`

需要验证：

- `answer=null` 不能 force publish。
- `layout-only` 不能 force publish。
- `incomplete material` 不能 force publish。
- `analysis=unknown` 可以 force publish，但必须显示警告和审计记录。
- `fallback_used` 可以 force publish，但必须显示警告和审计记录。
- `needs_review` 可以 force publish，但必须显示人工确认记录。
- force publish 后 h5 端不能裸显 `unknown/null`。
- force publish 后 backend 必须保留 warning / review action / audit event。

### 6.2 backend API / DTO

如必要，补齐：

- `force_publish_reason`
- `force_publish_operator`
- `force_publish_at`
- `force_publish_warnings`
- `publish_blocking_reasons`
- `publish_soft_warnings`
- `audit_event_id`

不要破坏已有 publish API。如果已有字段，优先复用。

### 6.3 Playwright admin force publish 测试

新增或更新：

```text
admin-web/e2e/commercial-ocr-admin.spec.ts
```

或新增：

```text
admin-web/e2e/commercial-ocr-force-publish.spec.ts
```

覆盖：

- hard-block fixture：publish 按钮禁用或 API 拒绝。
- soft-warning fixture：点击 force publish，填写 reason，确认发布。
- publish 后 admin 显示 force-published / warning 状态。
- h5 可打开该题，友好展示暂无解析或需复核标记。
- 页面不出现 `null/unknown` 裸显。

### 6.4 MiMo reviewer 自动证据

新增或完善脚本：

- 从 Playwright evidence 目录读取截图/JSON。
- 生成 mock visual review JSON。
- 生成 mock text review JSON。
- 如果 env 开启真实 MiMo，只做最小 smoke。
- visual 图片只发给 `mimo-v2.5`。
- JSON/text 只发给 `mimo-v2.5-pro`。

建议脚本：

```text
scripts/e2e/run-mimo-review-on-evidence.sh
```

或：

```text
pdf-service/scripts/review_e2e_evidence_with_mimo.py
```

输出：

```text
debug/e2e-commercial-ocr/mimo-review/<timestamp>/visual-review.json
debug/e2e-commercial-ocr/mimo-review/<timestamp>/text-review.json
debug/e2e-commercial-ocr/mimo-review/<timestamp>/mimo-review-evidence.json
```

`debug` 不提交 Git。

### 6.5 COCR-M15 报告

写入：

```text
docs/commercial-ocr-phase-reports/COCR-M15-force-publish-mimo-review-hardening.md
```

必须写：

- force publish 硬阻止/软放行测试结果
- MiMo reviewer 是否真实调用/跳过
- visual/text reviewer JSON 路径
- API/DTO 变化
- 审计字段
- 风险
- `GO / GO_WITH_RISK / BLOCKED`

---

## 7. COCR-M16：admin 编辑题库里的真实 H5 预览页面

这是本轮最重要的功能。

目标：admin 端在“编辑题库 / 审核题目 / 编辑试卷 / 发布预览”场景中，提供一个真实 H5 端一致的预览页面。

不要做成纯 admin 自己写的假卡片。要尽量复用 h5-web 的真实题目渲染逻辑、样式和数据结构。

你需要先搜索现有 admin 中的编辑题库/审核/预览页面：

```text
admin-web/src/views/**
admin-web/src/components/**
admin-web/src/router/**
admin-web/src/api/**
```

同时搜索 h5-web 的真实题目页面：

```text
h5-web/src/views/**
h5-web/src/components/**
h5-web/src/router/**
h5-web/src/api/**
```

### 7.1 方案选择

优先方案按顺序选择。

#### 方案 A：iframe 真实 h5 preview 路由

- 在 h5-web 新增 preview 路由，例如：
  - `/preview/paper/:paperId`
  - `/preview/task/:taskId`
  - `/preview/admin-paper/:previewToken`
- admin 中用 iframe 嵌入该 h5 preview 页面。
- iframe viewport 固定为 `390x844` 或可切换设备尺寸。
- h5 preview 使用真实 h5 题目组件和样式。
- 数据来自 backend preview API 或 preview payload。
- 优点：最接近真实 H5 端。

#### 方案 B：共享 renderer 包/组件

- 抽出 question renderer 到共享模块。
- admin 和 h5 共用同一 renderer。
- 如果当前架构不方便，不要大重构，可作为后续建议。

#### 方案 C：admin 内嵌 h5-web build route

如果 h5 路由已支持 preview query，可直接嵌入真实 h5 URL：

```text
http://127.0.0.1:5173/xxx?preview=1&paperId=...
```

需要保证 preview token / CORS / dev 环境可用。

本轮优先采用最小可交付方案：方案 A 或 C。

### 7.2 H5 preview 必须支持

- `390x844` mobile viewport
- 题目列表或题号导航
- 第 17/18/19/20 切换
- shared material 展示
- 图表/表格/材料图展示
- options 展示
- answer/analysis 预览
- `unknown/null` 友好占位
- force published warning 展示
- quality gate warning 展示，可简化为提示条
- 刷新/重新加载当前 preview payload

### 7.3 admin preview UI 必须支持

- 在审核/编辑页面打开 H5 预览
- 显示“真实 H5 预览”标题
- 显示当前 preview 来源：
  - `taskId / paperId / bankId / previewToken`
- 显示设备尺寸
- 提供刷新预览按钮
- 提供打开真实 h5 页面按钮
- 预览加载失败时显示明确错误，而不是空白
- 不出现 `undefined / [object Object] / null` 裸显

### 7.4 backend preview API 建议

如果已有 publish preview API，优先复用。

如没有，新增最小 preview endpoint，例如：

```text
GET /api/pdf/tasks/:taskId/h5-preview
GET /api/papers/:paperId/h5-preview
POST /api/publish/preview
```

返回结构必须与 h5-web 消费结构一致，至少包括：

- `paper_id / preview_id`
- `title`
- `questions`
- `material_groups`
- `assets`
- `quality_gate_summary`
- `publish_warnings`
- `force_publish_status`
- `m5a_summary`
- `m5b_summary`

必须保证 17-20：

- shared material 在 preview payload 中只有一份或明确引用
- child questions 引用 same `material_id`
- h5 端切题不丢 material
- `local_stem` 不重复 `shared_stem`

### 7.5 COCR-M16 报告

写入：

```text
docs/commercial-ocr-phase-reports/COCR-M16-admin-h5-real-preview.md
```

必须写：

- 选择了 iframe 还是共享 renderer
- 新增路由/API
- 数据流
- 17-20 预览结果
- force publish warning 展示
- 回滚方案
- 风险
- `GO / GO_WITH_RISK / BLOCKED`

---

## 8. COCR-M17：admin preview 与真实 h5 一致性 E2E

目标：用 Playwright 验证 admin 里的 H5 预览与真实 h5-web 页面一致。

新增或更新测试：

```text
admin-web/e2e/commercial-ocr-admin-h5-preview.spec.ts
h5-web/e2e/commercial-ocr-h5.spec.ts
```

或统一根目录 e2e，按项目结构选择。

E2E 流程：

1. 启动全栈。
2. seed 或创建一份完整 preview paper：
   - 17-20 shared material
   - 图表/表格
   - 完整 answer/analysis
   - 一个 soft warning / force publish case
3. 打开 admin 编辑/审核页面。
4. 打开右侧或 tab 的 H5 预览。
5. 断言：
   - iframe 或 preview 容器可见
   - `390x844` viewport
   - 第 17 题可见
   - shared material 可见
   - 图表/表格可见
   - 选项可见
   - 切换到 18/19/20 后 shared material 仍可见
   - `local_stem` 不重复 `shared_stem`
   - answer/analysis 友好显示
   - force publish warning 可见
6. 点击“打开真实 H5 页面”。
7. 在真实 h5 页面做同样断言。
8. 对比 admin preview 与真实 h5：
   - 题号一致
   - shared material 文本一致
   - child question stem 一致
   - options 数量一致
   - answer/analysis 状态一致
   - warning 状态一致
9. 截图并保存 trace。

Playwright 证据路径：

```text
debug/e2e-commercial-ocr/admin-h5-preview/<timestamp>/
```

包含：

```text
admin-preview-17.png
admin-preview-18.png
admin-preview-20.png
h5-real-17.png
h5-real-18.png
h5-real-20.png
admin-preview-state.json
h5-real-state.json
consistency-report.json
trace.zip
```

`debug` 不提交 Git。

COCR-M17 报告：

```text
docs/commercial-ocr-phase-reports/COCR-M17-admin-preview-h5-consistency-e2e.md
```

必须写：

- Playwright 命令
- 断言结果
- 一致性对比结果
- 截图/trace 路径
- MiMo reviewer 是否参与评审
- `GO / GO_WITH_RISK / BLOCKED`

---

## 9. COCR-M18：全量回归、稳定性与合并 main 准备

目标：完成第 6 步的工程验收基础，当前 `mimo` 分支暂不直接合并 main，但要准备好合并方案。

### 9.1 回归命令

环境：

```bash
./scripts/e2e/start-commercial-ocr-stack.sh
curl http://127.0.0.1:3010/api/health
curl http://127.0.0.1:8001/health
```

pdf-service：

```bash
cd pdf-service && ./.venv/bin/python -m pytest tests/test_mimo_reviewer.py -v
cd pdf-service && ./.venv/bin/python -m pytest tests/ -v
```

backend：

```bash
cd backend && pnpm test
cd backend && pnpm build
```

admin-web：

```bash
cd admin-web && pnpm build
cd admin-web && pnpm exec playwright test e2e/commercial-ocr-admin.spec.ts --trace=on
cd admin-web && pnpm exec playwright test e2e/commercial-ocr-admin-h5-preview.spec.ts --trace=on
```

h5-web：

```bash
cd h5-web && pnpm build
cd h5-web && pnpm exec playwright test e2e/commercial-ocr-h5.spec.ts --trace=on
```

MiMo evidence review：

```bash
./scripts/e2e/run-mimo-review-on-evidence.sh
```

或：

```bash
cd pdf-service && ./.venv/bin/python scripts/review_e2e_evidence_with_mimo.py --mock
```

停止环境：

```bash
./scripts/e2e/stop-commercial-ocr-stack.sh
```

如果某个命令失败：

- 先修复。
- 修不了就记录 FAIL 和原因。
- 如果是 env/skipped，要明确写 SKIPPED。
- 不要伪造 PASS。

### 9.2 git hygiene

不要提交：

- `.env`
- API key/token/secret
- debug/e2e screenshots/traces/videos
- provider raw response
- uploads
- 题本/答本
- `rest2.0ocrv1paper_cut_edu.js`

可以提交：

- 源码
- tests
- Playwright spec
- synthetic fixture/mock fixture
- `docker-compose.e2e.yml`
- `scripts/e2e/*`
- docs
- `prd.json`
- `progress.txt`
- `.env.example`

### 9.3 merge readiness 报告

写入：

```text
docs/commercial-ocr-phase-reports/COCR-M18-full-regression-merge-readiness.md
```

必须包含：

- 当前分支
- 当前 commit
- 与 main 的差异摘要
- 测试结果
- 未完成项
- 是否建议合并 main
- 合并步骤
- 回滚方案
- 风险清单

### 9.4 合并建议

只写方案，不自动合并 main，除非用户明确要求。

建议步骤：

```bash
git checkout main
git pull --ff-only origin main
git merge --no-ff mimo
# 运行测试
git push origin main
```

---

## 10. COCR-M19：第六步最终交付报告与 handoff

目标：形成本轮完整交付闭环。

新增最终汇总报告：

```text
.agent/reports/mimo-commercial-ocr-step6-final-report.md
```

新增 handoff：

```text
.agent/handoff/mimo-step6-final-handoff-<timestamp>.md
```

COCR-M19 阶段报告：

```text
docs/commercial-ocr-phase-reports/COCR-M19-step6-final-delivery.md
```

最终报告必须包含：

1. 当前分支
2. 当前 commit
3. 是否 push origin/mimo
4. 第 1～6 步完成状态
5. 环境状态
6. backend 状态
7. pdf-service 状态
8. admin-web 状态
9. h5-web 状态
10. admin H5 real preview 状态
11. force publish 状态
12. MiMo reviewer 状态
13. Playwright E2E 状态
14. admin preview 与真实 h5 一致性结果
15. 17-20 shared material 验收结果
16. M5A/M5B 回归状态
17. 测试命令与结果
18. 证据路径
19. known issues
20. 安全与 key 轮换提醒
21. git hygiene 状态
22. 合并 main 建议
23. 下一轮建议

handoff 必须包含：

- 当前分支
- 当前 commit
- 已完成阶段
- 未完成阶段
- 测试结果
- 服务启动/停止命令
- 证据路径
- 数据清理命令
- 合并 main 建议
- resume prompt

---

## 11. admin H5 预览功能验收标准

必须满足：

1. admin 中能打开 H5 真实预览。
2. 预览使用 h5-web 真实渲染逻辑或真实 h5 iframe。
3. 预览 viewport 接近手机端。
4. 17-20 shared material 可见。
5. 切换 17/18/19/20 不丢 shared material。
6. `local_stem` 不重复 `shared_stem`。
7. 图表/表格/材料图可见。
8. 选项、答案、解析可见或友好占位。
9. force publish warning 可见。
10. quality/publish warnings 可见或有入口。
11. admin preview 与真实 h5 页面关键内容一致。
12. 页面不出现：
    - `undefined`
    - `[object Object]`
    - `null` 裸显
    - `unknown` 裸显为正常解析
    - `visual parse unavailable`
    - 永久 loading
    - 严重 console error

---

## 12. force publish 验收标准

必须满足：

硬阻止：

- `answer=null` 不可发布，也不可 force publish。
- `layout-only` 不可发布，也不可 force publish。
- `incomplete material` 不可发布，也不可 force publish。

软放行：

- `analysis=unknown` 可 force publish，但必须有 warning。
- `fallback_used=true` 可 force publish，但必须有 warning。
- `needs_review=true` 可 force publish，但必须有人工确认 reason。

审计：

- force publish 必须记录 reason/operator/time/warnings 或项目等价字段。
- admin 必须能看到 force-published 状态或 warning。
- h5 必须友好展示暂无解析/需复核，不可裸显 `unknown/null`。

---

## 13. MiMo reviewer 验收标准

默认：mock/skipped。

必须满足：

- `mimo-v2.5` 只处理截图/图片。
- `mimo-v2.5-pro` 只处理 JSON/text。
- 真实 API 未开启时，报告写 `skipped by env`。
- mock visual review JSON 存在。
- mock text review JSON 存在。
- 如果出现 blocking issue，报告中明确。
- 真实 MiMo 调用失败不阻塞 E2E。

visual review JSON 结构建议：

```json
{
  "overall_verdict": "pass|warning|fail|skipped",
  "human_readable": true,
  "admin_review": {
    "question_stem_visible": true,
    "options_visible": true,
    "material_group_visible": true,
    "quality_gate_visible": true,
    "issues": []
  },
  "h5_review": {
    "mobile_readable": true,
    "shared_material_visible_for_17_20": true,
    "chart_or_table_visible": true,
    "answer_analysis_readable": true,
    "issues": []
  },
  "visual_quality": {
    "chart_title_preserved": true,
    "table_header_preserved": true,
    "figure_not_fragmented": true,
    "no_layout_overflow": true,
    "issues": []
  },
  "blocking_issues": [],
  "recommendations": [],
  "model": "mimo-v2.5",
  "skipped_reason": null
}
```

text review JSON 结构建议：

```json
{
  "overall_verdict": "pass|warning|fail|skipped",
  "same_material_id_for_17_20": true,
  "local_stem_not_polluted": true,
  "shared_assets_preserved": true,
  "quality_gate_reasonable": true,
  "publish_gate_reasonable": true,
  "h5_payload_consistent": true,
  "blocking_issues": [],
  "recommendations": [],
  "model": "mimo-v2.5-pro",
  "skipped_reason": null
}
```

---

## 14. Playwright 证据要求

证据路径：

```text
debug/e2e-commercial-ocr/admin/<timestamp>/
debug/e2e-commercial-ocr/h5/<timestamp>/
debug/e2e-commercial-ocr/admin-h5-preview/<timestamp>/
debug/e2e-commercial-ocr/mimo-review/<timestamp>/
```

至少保存：

- screenshots
- traces
- console.json
- network.json
- final-admin-review-state.json
- final-h5-state.json
- admin-preview-state.json
- h5-real-state.json
- consistency-report.json
- visual-review.json
- text-review.json

这些 debug 证据不提交 Git，只在报告记录路径。

---

## 15. progress、prd、handoff 更新

必须更新：

```text
progress.txt
prd.json
.agent/reports/mimo-commercial-ocr-step6-final-report.md
.agent/handoff/mimo-step6-final-handoff-<timestamp>.md
```

`progress.txt`：

- append-only
- 写入 M15/M16/M17/M18/M19 进展
- 写入测试结果
- 写入真实 API skipped / mock 情况
- 写入下一步建议

`prd.json`：

- 完成 story `passes=true`
- notes 写报告路径、证据路径、风险
- 未完成 story 保持 false

handoff：

- 当前分支
- 当前 commit
- 已完成阶段
- 未完成阶段
- 测试结果
- 服务启动/停止命令
- 证据路径
- 数据清理命令
- 合并 main 建议
- resume prompt

---

## 16. git hygiene

确认 `.gitignore` 覆盖：

```gitignore
.env
.env.*
!.env.example
backend/uploads/
debug/provider-trace/
debug/commercial-ocr-eval/
debug/e2e-commercial-ocr/
debug/e2e-upload/
**/api-responses.json
**/task-status.json
*.trace.zip
*.webm
*.mp4
题本/
答本/
rest2.0ocrv1paper_cut_edu.js
```

不要提交：

- `.env`
- API key / token / secret
- debug/e2e 截图、trace、video
- raw provider response
- 题本/答本
- 上传文件

可以提交：

- 源码
- tests
- Playwright spec
- mock fixture
- synthetic fixture
- `docker-compose.e2e.yml`
- `scripts/e2e/*`
- docs
- `prd.json`
- `progress.txt`
- `.env.example`

---

## 17. 提交与推送策略

当前在 `mimo` 分支。

建议分阶段 commit：

1. `force publish E2E and audit hardening`
2. `MiMo evidence review automation`
3. `backend preview API for H5 preview`
4. `h5 preview route / reusable renderer`
5. `admin H5 real preview integration`
6. `admin-preview vs h5 consistency Playwright E2E`
7. `full regression and merge readiness docs`
8. `step6 final reports/progress/prd/handoff/git hygiene`

最终：

```bash
git push origin mimo
```

不要自动合并 main。不要 force push。如果 BLOCKED，也 push 当前分支和报告，方便用户接手。

---

## 18. 最终 CLI 输出

最终输出必须包含：

1. 当前分支
2. 当前 commit
3. 是否 push origin/mimo
4. 修改文件清单
5. 第 1 步环境复验状态
6. 第 2 步后端链路复验状态
7. 第 3 步 admin E2E 状态
8. 第 4 步 h5 E2E 状态
9. 第 5 步 MiMo reviewer 状态
10. 第 6 步全量回归与 merge readiness 状态
11. COCR-M15 状态
12. COCR-M16 状态
13. COCR-M17 状态
14. COCR-M18 状态
15. COCR-M19 状态
16. force publish E2E 结果
17. MiMo reviewer 结果
18. admin H5 preview 功能结果
19. admin preview 与真实 h5 一致性结果
20. Playwright 证据路径
21. MiMo review JSON 路径
22. 测试命令结果
23. prd.json 更新摘要
24. progress.txt 更新摘要
25. git status 分类
26. 报告路径
27. handoff 路径
28. 合并 main 建议
29. 下一轮建议：
    - 真实 MiMo 最小 smoke
    - 真实百度/腾讯 OCR 1 页 smoke
    - 合并回 main
    - admin H5 preview UI polish
    - h5 mobile UX polish
    - 修复任何剩余 flaky/known regression

现在开始执行。

默认 mock commercial OCR + mock MiMo reviewer。真实外部 API 默认跳过。`mimo-v2.5` 用视觉，`mimo-v2.5-pro` 只用文本。本轮重点是完成第 6 步：admin 编辑题库/审核页面的真实 H5 预览、一致性 E2E、全量回归、合并 main 准备、最终报告和 handoff。
