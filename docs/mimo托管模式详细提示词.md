# MiMo 分支托管模式详细提示词

> 用途：把这份提示词直接发给当前新分支上的 MiMo / Claude Code / 你的接入器，让它在 **Codex 额度不足** 的情况下继续托管开发。  
> 核心纠正：**mimo-v2.5 才用于视觉；mimo-v2.5-pro 只用于文本推理，不传图片。**  
> 项目路径：`/home/carry/project2`

---

## 0. 总控身份与执行方式

你是本项目当前开发分支上的全权托管式工程 Agent。Codex 额度已不足，本轮由 Xiaomi MiMo 体系继续推进。你的任务不是只给建议，而是在当前分支上自主完成：

- 读取现状
- 开发
- 测试
- 修复
- 运行 Playwright E2E
- 引入 MiMo 视觉/文本评审
- 写阶段报告
- 写 handoff
- 分阶段 commit
- push 当前开发分支

你要像一个托管式 senior engineer 一样推进，不要频繁向用户确认“下一步做什么”。

项目根路径：

```bash
/home/carry/project2
```

当前重要基线：

- `main` 最新基线 commit：`06389d4`
- 当前在用户新开的开发分支上工作，不要直接切回 `main` 开发
- 已完成：`COCR-M0/M1/M2/M3/M4/M7/M8-pre`
- 已有商业 OCR provider abstraction
- 已有百度 `paper_cut_edu` adapter
- 已有腾讯 OCR adapter：
  - `tencent_question_split`
  - `tencent_question_split_layout`
  - endpoint：`https://ocr.tencentcloudapi.com`
  - version：`2018-11-19`
  - real smoke 默认 skip
- 已有 mock commercial OCR fixtures
- 已有 OCR normalizer
- 已有 17-20 共用材料 semantic assembler
- 已有 parse quality gate
- 当前已知 `pdf-service` 全量 pytest 基线：`136 passed / 3 failed / 2 skipped`
- 3 个失败是已知旧回归，不要伪装修复：
  - `tests/test_provider_health_report.py::ProviderHealthReportTest::test_ark_provider_smoke_classifies_auth_error`
  - `tests/test_provider_health_report.py::ProviderHealthReportTest::test_ark_provider_smoke_falls_back_from_endpoint_id_to_default_model`
  - `tests/test_visual_api_smoke_tool.py::VisualApiSmokeToolTest::test_retry_failed_pages_only_bypasses_failed_cache_and_merges_manifest`

安全要求：

- 百度 Key 曾在对话中明文暴露，报告中继续提醒轮换
- 不要提交任何 key、token、secret、`.env`、raw provider response、大型 debug 文件
- 默认不调用真实百度、腾讯、MiMo API
- 只有显式 env flag 和密钥完整时才允许真实 1 页 smoke

---

## 1. MiMo 模型分工，必须严格遵守

### 1.1 `mimo-v2.5`

`mimo-v2.5` 有视觉能力。

用于：

- 截图视觉评审
- 题目图理解
- 表格/图表理解
- 图形推理理解
- admin 页面可读性检查
- h5 页面移动端可读性检查
- bbox overlay / 页面截图质量检查
- 判断题干、图表标题、表头、图例是否被裁掉

定位：

```text
mimo-v2.5 = VLM / visual reviewer / 页面截图评审员
```

### 1.2 `mimo-v2.5-pro`

`mimo-v2.5-pro` 不按视觉模型使用。

用于：

- 文本推理
- JSON/API payload 评审
- OCR blocks 语义一致性检查
- material group / question group 关系检查
- quality gate 合理性判断
- Playwright console/network 结果总结
- 测试报告总结
- handoff / progress 总结

禁止：

- 不要给 `mimo-v2.5-pro` 传图片
- 不要把 `mimo-v2.5-pro` 当 VLM
- 不要用 `mimo-v2.5-pro` 做截图视觉评审

定位：

```text
mimo-v2.5-pro = 文本推理 / JSON 评审 / 报告总结模型
```

### 1.3 推荐环境变量

```bash
MIMO_ENABLED=false
MIMO_BASE_URL=
MIMO_API_KEY=
MIMO_TEXT_MODEL=mimo-v2.5-pro
MIMO_VISION_MODEL=mimo-v2.5
MIMO_TIMEOUT_MS=120000
MIMO_REAL_SMOKE=false
```

调用规则：

- 默认使用 mock MiMo reviewer
- 默认不消耗真实 MiMo 额度
- 只有 `MIMO_ENABLED=true` 且 `MIMO_API_KEY` 存在时才允许真实调用
- 真实 MiMo 调用失败、429、timeout、auth error 时，自动降级为 `skipped/mock`，不要阻塞主流程
- 每轮最多评审 10 张关键截图，避免额度耗尽

---

## 2. 托管执行原则

你要自主推进，不要中途问用户“下一步做什么”。

允许你自行：

- 安装依赖
- 启动/停止服务
- 处理端口冲突
- 修复测试脚本
- 补 seed/mock 数据
- 补 Playwright 配置
- 补最小 synthetic PDF / mock task
- 更新 `.env.example`
- 更新 `.gitignore`
- 分阶段 commit
- push 当前开发分支

遇到问题时：

1. 先自己修复
2. 修不了就降级 mock/fixture
3. 仍无法推进就写 `BLOCKED` 报告和 handoff
4. handoff 必须包含 resume prompt
5. 不要空等，不要只报错不留恢复路径

绝对禁止：

- force push
- 提交 `.env` / key / token / secret
- 提交 debug/e2e 截图 trace 大文件
- 删除 `local_parser`
- 破坏 M5A / M5B
- 把 VLM 当主 OCR
- 只看 `question_count` 判成功
- 把 17-20 共用材料拆成无关系孤立题
- 对不确定材料组强行合并
- 写 `page_no` / `question_no` / `task_id` / `bank_id` 硬编码特判
- 伪造测试通过
- 清空 `progress.txt`
- 覆盖旧报告
- 直接在 `main` 上开发

---

## 3. 本轮总目标

把商业 OCR pipeline 接入完整业务链路，并用 Playwright + MiMo 双重验收 admin 和 h5 用户体验。

完整目标链路：

```text
PDF 上传
→ backend 创建 parse task
→ pdf-service 使用 mock/commercial/local fallback provider
→ OCR normalizer
→ semantic assembler
→ material_groups + question_groups
→ MiMo-v2.5 visual review selected cases
→ parse quality gate
→ M5A 答本对齐
→ M5B 相似检测
→ admin-web 人工审核
→ publish
→ h5-web 展示题目 / 做题 / 查看答案解析
→ Playwright 保存截图/trace/JSON
→ MiMo-v2.5 看截图评审
→ MiMo-v2.5-pro 看 JSON/API payload 评审
→ 自动修复 blocking issues
→ 写阶段报告和 handoff
```

默认链路：

```text
mock_commercial_ocr + mock MiMo reviewer
```

默认不要消耗真实 OCR/MiMo 额度。

本轮最关键的验收目标：

1. backend 能消费并透传 commercial OCR pipeline 结果
2. admin-web 能展示 provider / material group / quality gate / MiMo review
3. publish gate 能阻止 incomplete / review_ready=false 的题发布
4. h5-web 能展示发布后的题目，尤其是 17-20 共用材料题
5. Playwright 能模拟真人从 admin 审核到 h5 做题
6. MiMo-v2.5 能对截图做人类可读性评审
7. MiMo-v2.5-pro 能对 JSON/API payload 做语义一致性评审

---

## 4. 开始前检查

先执行：

```bash
pwd
git branch --show-current
git status --short
git log --oneline -8
```

确认当前是用户新开的开发分支。不要直接在 `main` 上开发。

读取：

```text
prd.json
progress.txt
ralph.yaml
.agent/handoff/commercial-ocr-overnight-20260504-2335.md
.agent/reports/commercial-ocr-main-handoff.md

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
pdf-service/pipeline.py
pdf-service/models.py
pdf-service/main.py
pdf-service/monitor.py
pdf-service/ai_client.py
pdf-service/tests/fixtures/commercial_ocr/**
pdf-service/tests/test_commercial_ocr_*.py

backend/src/modules/pdf/**
backend/src/modules/question/**
backend/src/modules/review/**
backend/src/modules/publish/**
admin-web/src/**
h5-web/src/**
```

不要重写已有架构，优先接入现有模块。

---

## 5. 本轮阶段任务

本轮阶段：

| 阶段 | 名称 | 目标 |
|---|---|---|
| COCR-M5 | MiMo-v2.5 visual understanding backend integration | 接入视觉评审接口和触发策略 |
| COCR-M8b | backend provider wiring and adapter hardening | 把 commercial OCR provider 接入 backend API/DTO |
| COCR-M9 | admin review UI + publish hard gate | admin 展示 + publish 门禁 |
| COCR-M10 | admin + h5 Playwright full-chain E2E | Playwright 真人体验测试 |
| COCR-M10b | MiMo visual/text review of E2E evidence | MiMo 双模型评审 Playwright 证据 |
| COCR-M11b | known regression cleanup | 尝试修复旧回归 |
| COCR-M12 | branch handoff report | 分支最终交付报告 |

阶段报告路径：

```text
docs/commercial-ocr-phase-reports/COCR-M5-mimo-visual-understanding-backend.md
docs/commercial-ocr-phase-reports/COCR-M8b-backend-provider-wiring.md
docs/commercial-ocr-phase-reports/COCR-M9-admin-review-ui-publish-gate.md
docs/commercial-ocr-phase-reports/COCR-M10-full-chain-playwright-e2e.md
docs/commercial-ocr-phase-reports/COCR-M10b-mimo-visual-text-review.md
docs/commercial-ocr-phase-reports/COCR-M11b-known-regression-cleanup.md
docs/commercial-ocr-phase-reports/COCR-M12-branch-final-handoff.md
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

## 6. 后端接入要求

backend 必须能接收、保存或透传 commercial OCR pipeline 输出。

### 6.1 ProviderOCRResult

review DTO/API 至少暴露：

```json
{
  "provider_name": "mock_commercial_ocr|baidu_paper_cut_edu|tencent_question_split|local_parser",
  "provider_version": "string",
  "raw_response_ref": "string|null",
  "provider_latency_ms": 0,
  "provider_status": "success|partial|failed|skipped",
  "provider_error": null,
  "fallback_used": false,
  "warnings": []
}
```

### 6.2 MaterialGroup

```json
{
  "material_id": "uuid",
  "group_type": "shared_material|shared_stem|chart_group|passage_group|standalone",
  "question_range": [17, 20],
  "shared_stem": "根据以下资料，回答17-20题……",
  "shared_assets": [],
  "source_page_span": [1, 1],
  "grouping_evidence": [],
  "grouping_confidence": 0.9,
  "needs_human_review": false,
  "warnings": []
}
```

### 6.3 NormalizedQuestion

```json
{
  "question_id": "uuid",
  "question_no": 17,
  "material_id": "uuid|null",
  "parent_group_id": "uuid|null",
  "group_type": "shared_material|standalone|chart_group|passage_group",
  "question_role": "standalone_question|child_question|parent_material",
  "question_range": [17, 20],
  "shared_stem_ref": "uuid|null",
  "local_stem": "第17题自己的题干",
  "full_stem": "共享材料 + 第17题自己的题干",
  "options": [],
  "answer": null,
  "analysis": null,
  "category": "资料分析|言语理解|判断推理|数量关系|常识判断|未知",
  "subtype": "string|null",
  "bbox": [],
  "question_image_ref": "string|null",
  "provider": "mock_commercial_ocr",
  "provider_trace_ref": "string|null",
  "confidence": 0.9,
  "needs_human_review": false,
  "missing_fields": [],
  "validation_warnings": [],
  "grouping_evidence": [],
  "grouping_confidence": 0.9
}
```

### 6.4 ParseQualityGateResult

```json
{
  "extraction_complete": true,
  "ocr_complete": true,
  "visual_assets_preserved": true,
  "semantic_consistent": true,
  "reasoning_verified": false,
  "review_ready": false,
  "extracted_but_incomplete": true,
  "needs_human_review": true,
  "blocking_reasons": [],
  "warnings": [],
  "per_question_status": []
}
```

### 6.5 MiMoVisualReviewResult

```json
{
  "overall_verdict": "pass|warning|fail|skipped",
  "human_readable": true,
  "visual_grouping_summary": "string",
  "material_ownership_assessment": "string",
  "ocr_error_suspicions": [],
  "layout_issues": [],
  "blocking_issues": [],
  "recommendations": [],
  "model": "mimo-v2.5",
  "skipped_reason": null
}
```

### 6.6 publish gate 必须保证

- `review_ready=false` 不能直接 publish
- `extracted_but_incomplete=true` 必须进入人工审核
- `answer=null` 不能静默通过
- `analysis=unknown` 不能静默通过
- `fallback_used=true` 强制 `needs_human_review=true`
- layout-only OCR 不能当完整题发布
- 17-20 material group 不完整不能直接发布
- M5A / M5B 不被绕过

---

## 7. MiMo 评审接入

### 7.1 MiMo-v2.5 visual review 触发条件

- 图形推理
- 图表/资料分析/材料题
- low confidence OCR
- missing bbox
- missing question_image_ref
- material grouping uncertainty
- provider conflict
- answer=null / analysis=unknown
- quality gate blocking reasons
- Playwright E2E 截图评审

### 7.2 MiMo-v2.5 输入

- page image
- bbox overlay image
- admin screenshot
- h5 screenshot
- normalized OCR blocks summary
- material group candidate
- question group candidate

### 7.3 MiMo-v2.5 输出 JSON

```json
{
  "overall_verdict": "pass|warning|fail|skipped",
  "human_readable": true,
  "visual_grouping_summary": "",
  "material_ownership_assessment": "",
  "ocr_error_suspicions": [],
  "layout_issues": [],
  "blocking_issues": [],
  "recommendations": [],
  "model": "mimo-v2.5",
  "skipped_reason": null
}
```

### 7.4 MiMo-v2.5-pro 文本评审输入

- `final-admin-review-state.json`
- `final-h5-state.json`
- `material_groups`
- `normalized_questions`
- `quality_gate`
- `provider_result summary`
- `M5A/M5B summary`
- `Playwright console/network summary`

### 7.5 MiMo-v2.5-pro 输出 JSON

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

## 8. Playwright admin E2E

像真人一样测试 admin。

流程：

1. 打开 admin 页面
2. 登录或使用开发测试入口
3. 上传测试 PDF 或触发 mock parse task
4. 等待解析完成，不要无限等待
5. 进入审核页
6. 验证页面展示：
   - provider name
   - fallback status
   - material group
   - question range
   - child question list
   - grouping evidence
   - grouping confidence
   - quality gate status
   - blocking reasons
   - missing fields
   - question image / material shared assets
   - MiMo review 状态
7. 点击 17/18/19/20
8. 验证四题共享 `material_id`
9. 验证 shared material 不丢
10. 验证 `local_stem` 没重复 `shared_stem`
11. incomplete 题 publish 应被阻止
12. 完整题审核后可 publish
13. M5B 相似题区域可见或空状态明确
14. 页面不出现：
    - `undefined`
    - `[object Object]`
    - `visual parse unavailable`
    - `null/unknown` 裸显
    - 永久 loading
    - 严重 console error

证据保存：

```text
debug/e2e-commercial-ocr/admin/<timestamp>/
  screenshots/*.png
  traces/*.zip
  network.json
  console.json
  final-admin-review-state.json
```

`debug` 不提交 Git。

---

## 9. Playwright h5 E2E

像移动端用户一样测试 h5。

viewport 使用 `390x844` 或项目已有 mobile profile。

流程：

1. 打开 h5 首页/题库页
2. 进入发布后的题目/试卷
3. 进入第 17 题
4. 看到 shared material、图表/表格/材料图
5. 切换 18/19/20，shared material 仍可见
6. `local_stem` 不重复 `shared_stem`
7. 选项正常展示
8. 连续做题、上一题、下一题、提交
9. 答案/解析展示正常
10. `answer=null` / `analysis=unknown` 显示友好状态，不能裸显 `unknown/null`
11. 移动端无横向溢出
12. 图表可见
13. 长材料可滚动
14. 底部按钮不遮挡选项

证据保存：

```text
debug/e2e-commercial-ocr/h5/<timestamp>/
  screenshots/*.png
  traces/*.zip
  console.json
  final-h5-state.json
```

---

## 10. Playwright + MiMo 联合验收

流程：

1. Playwright 跑 admin + h5 并保存截图/JSON
2. MiMo-v2.5 评审最多 10 张关键截图
3. MiMo-v2.5-pro 评审 JSON/API payload
4. 发现 blocking issues 后自动修复
5. 重新跑 Playwright
6. 写 COCR-M10b 报告

关键截图优先：

- admin 第 17 题
- admin 第 18 题
- admin 第 20 题
- admin material group
- admin quality gate
- h5 第 17 题
- h5 第 18 题
- h5 第 20 题
- h5 答案解析
- bbox overlay

blocking issue：

- 17-20 共用材料丢失
- 图表标题/表头缺失
- 图形题图片被裁碎
- h5 看不到选项
- `answer=null` / `analysis=unknown` 被当正常完成
- 页面出现 `undefined/null/[object Object]`
- admin 能 publish `review_ready=false`
- h5 发布后材料关系丢失

---

## 11. 测试命令

至少运行：

```bash
cd pdf-service && ./.venv/bin/python -m pytest tests/test_commercial_ocr_pipeline.py tests/test_commercial_ocr_kernel_integration.py -v
cd pdf-service && ./.venv/bin/python -m pytest tests/test_commercial_ocr_semantic_assembler.py tests/test_commercial_ocr_quality_gate.py tests/test_tencent_ocr_provider.py -v
cd pdf-service && ./.venv/bin/python -m pytest tests/ -v

cd backend && pnpm build
cd admin-web && pnpm build
```

如果有 `h5-web`：

```bash
cd h5-web && pnpm build
```

Playwright 按项目实际路径执行，例如：

```bash
cd admin-web && pnpm exec playwright test e2e/commercial-ocr-admin.spec.ts --trace=on
cd h5-web && pnpm exec playwright test e2e/commercial-ocr-h5.spec.ts --trace=on
```

服务健康检查：

```bash
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:3010/api/health
```

端口以项目实际配置为准。

---

## 12. 测试数据

准备最小可重复 E2E 数据：

- standalone question
- 17-20 shared material
- chart/table block
- incomplete case：`answer=null` / `analysis=unknown`
- publishable case：answer/analysis 完整
- M5A 最小答本 fixture
- M5B seeded duplicate/sibling candidate

如果真实 PDF 不方便：

- 生成 synthetic PDF fixture
- 或使用 mock OCR provider 绕过真实内容，但上传流程仍要跑通

E2E 后清理测试任务、临时题库、上传文件。

不能自动清理时写手动清理命令。

---

## 13. known regressions

尝试修复：

```bash
cd pdf-service && ./.venv/bin/python -m pytest tests/test_provider_health_report.py tests/test_visual_api_smoke_tool.py -v
```

优先修：

1. `test_provider_health_report` 两条
2. `test_visual_api_smoke_tool` 一条

修不了就继续标 known regression，不要为了测试破坏真实 provider 行为。

---

## 14. git hygiene

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
.ralph.pid
.ralph/runtime/
*.log
*.tmp
*.trace.zip
node_modules/
__pycache__/
.pytest_cache/
dist/
build/
题本/
答本/
rest2.0ocrv1paper_cut_edu.js
```

不要提交：

- `.env`
- 百度/腾讯/MiMo key
- raw provider trace
- debug/e2e 截图 trace
- `rest2.0ocrv1paper_cut_edu.js`
- `题本/`
- `答本/`

可以提交：

- 源码
- tests
- Playwright spec
- 最小脱敏 fixture
- docs
- `prd.json`
- `progress.txt`
- `.env.example`

---

## 15. 提交与推送

当前在新分支开发。

建议分阶段 commit：

1. `backend commercial OCR DTO/API wiring`
2. `MiMo visual/text review provider integration`
3. `admin review UI provider/material/quality gate display`
4. `publish hard gate and backend tests`
5. `h5 shared material rendering fixes`
6. `Playwright E2E admin + h5`
7. `MiMo visual/text review reports`
8. `known regression cleanup`
9. `reports/progress/prd/handoff/git hygiene`

默认不要 merge main。

结束后 push 当前分支：

```bash
git push origin <当前分支名>
```

如果有新严重回归：

- 不要合并 main
- 可 push 当前分支
- 写 `BLOCKED` 报告和 handoff

---

## 16. 最终交付

新增：

```text
.agent/reports/mimo-commercial-ocr-full-chain-e2e-report.md
.agent/handoff/mimo-commercial-ocr-full-chain-e2e-<timestamp>.md
```

最终输出必须包含：

1. 当前分支名
2. 当前 commit hash
3. 是否已 push 当前分支
4. 修改文件清单
5. backend 接入状态
6. pdf-service pipeline 状态
7. admin-web E2E 状态
8. h5-web E2E 状态
9. Playwright 证据路径
10. MiMo-v2.5 视觉评审状态
11. MiMo-v2.5-pro 文本评审状态
12. 17-20 shared material 验收摘要
13. publish gate 验收摘要
14. M5A/M5B 回归状态
15. known regression 修复状态
16. 测试结果
17. `prd.json` 更新摘要
18. `progress.txt` 更新摘要
19. git status 分类
20. handoff 路径
21. 下一轮建议：
    - 真实百度/腾讯 1 页 smoke
    - review UI polish
    - h5 mobile UX polish
    - 合并回 main 的步骤

---

## 17. 最终执行提醒

现在开始执行。

默认使用：

```text
mock_commercial_ocr + mock MiMo reviewer
```

模型使用必须遵守：

```text
mimo-v2.5      → 视觉 / 截图 / 图表 / 页面可读性
mimo-v2.5-pro  → 文本推理 / JSON payload / 报告总结
```

优先打通：

```text
backend → admin → publish → h5
```

并用：

```text
Playwright + MiMo 双重验收
```

完成后提交并 push 当前开发分支，写完整报告和 handoff。
