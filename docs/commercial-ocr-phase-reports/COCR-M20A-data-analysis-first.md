# COCR-M20A: Data Analysis First OCR API + VLM/LLM Understanding

## 1. Baseline Tag

- 当前分支（开始实现前）: `mimo`
- baseline commit（打 tag 时）: `55947990e8afa98818673795b1321ad7c5c048b1`
- baseline tag: `pre-data-analysis-ocr-api-first-20260505-221735`
- tag push 状态: `git push origin pre-data-analysis-ocr-api-first-20260505-221735` 已执行

## 2. 为什么先做资料分析

本轮只先打通“根据以下资料，回答 17-20 题”这类共用材料链路，原因有三点：

1. 资料分析最依赖表头、单位、图例、标题和共享材料完整性，最能验证 OCR API First 是否真正可用。
2. 一旦 OCR 文本、bbox、shared material、图表资产和 LLM 解题过程都能闭环，后续再扩展到其他题型时，质量门禁和 workbench 展示骨架已经具备。
3. 这条链路天然适合“OCR 主识别 + VLM 做视觉上下文 + LLM 做题理解”的职责分离，不会把 VLM 错用成主 OCR。

## 3. OCR API bbox 如何接入

本轮没有新建数据库字段，而是把资料分析增强结果挂到现有 `question_quality.commercial_ocr` 结构，避免 schema 迁移。

落地方式：

- `pdf-service/commercial_ocr/types.py`
  - `NormalizedQuestion` 新增 `ocr_answer_candidate`、`ocr_analysis_candidate`、`provider_confidence`、`provider_bbox`、`provider_raw_ref`、`crop_image_ref`、`layout_only`
  - `MaterialGroup` 新增 `table_blocks`、`chart_blocks`
  - 新增 `DataAnalysisVisualContext`、`DataAnalysisUnderstandingResult`、`DataAnalysisQualityGate`
- `pdf-service/commercial_ocr/semantic_assembler.py`
  - 将 17-20 共用材料组提升为 `group_type=data_analysis_material`
  - 保留 provider bbox / answer candidate / analysis candidate / layout-only 语义
- `pdf-service/commercial_ocr/service.py`
  - 运行 provider → normalizer → semantic assembler → visual context → understanding → quality gate
  - 通过 `build_question_enrichment_payloads(...)` 把结果回灌到 parser kernel
- `backend/src/modules/pdf/pdf.service.ts`
  - 将 `data_analysis_visual_context`、`data_analysis_understanding_results`、`data_analysis_quality_gate` 映射到候选题和 `question_quality.commercial_ocr`
- `admin-web/src/utils/pdfHighlights.ts`
  - bbox overlay 优先消费 `question_quality.commercial_ocr.bbox_overlay.highlights`

## 4. 17-20 MaterialGroup 结果

当前 `shared_material_17_20_complete_blocks.json` 基线已经被补充为资料分析友好的结构化 fixture：

- 17/18/19/20 共用一个 `material_id`
- `question_range=[17,20]`
- `shared_stem` 保留“根据以下资料，回答17-20题”
- `shared_assets`、`table_blocks`、`chart_blocks` 被保留并传到 workbench / H5
- `local_stem` 不再重复污染 `shared_stem`
- `source_page_span` 和 provider bbox 可用于 workbench overlay

同时补了两类校验 fixture：

- `shared_material_17_20_complete_blocks.json`
  - 正常通过链路
  - `q18` 答案候选修正为 `D`，与资料数据和 H5 断言一致
- `shared_material_17_20_soft_warning_blocks.json`
  - 人工构造 OCR/LLM 冲突
  - 当前 E2E 验证 `q17` 会进入 `needs_human_review`

## 5. VLM Visual Context 结果

新增 prompt：

- `pdf-service/commercial_ocr/prompts/data_analysis_visual_context_zh.md`

当前实现：

- `pdf-service/commercial_ocr/data_analysis.py`
  - mock visual provider: `model_provider=mock`
  - mock model name: `qwen-vl-mock`
  - 检查 `source_material_complete`
  - 检查 `chart_title_present`
  - 检查 `table_header_present`
  - 检查 `unit_present`
  - 检查 `legend_present`
  - 检查 `material_group_visual_consistent`
  - 输出 `critical_data_points_visible`、`suspected_crop_errors`、`suspected_ocr_errors`
- `pdf-service/commercial_ocr/visual_understanding.py`
  - 将资料分析 visual context 并入既有 visual summary
  - 明确 VLM 只做视觉上下文，不替代 OCR

当前阶段真实 `qwen-vl` / `doubao-vl` 默认不调用；无 key 环境下按设计走 mock，并在报告中记为 `skipped by env`。

## 6. LLM Calculation Reasoning 结果

新增 prompt：

- `pdf-service/commercial_ocr/prompts/data_analysis_question_understanding_zh.md`

当前实现：

- `pdf-service/commercial_ocr/data_analysis.py`
  - mock text provider: `model_provider=mock`
  - mock model name: `qwen-text-mock`
  - 对 17/18/19/20 逐题输出：
    - `can_understand_material`
    - `can_solve_question`
    - `answer_suggestion`
    - `calculation_reasoning`
    - `formula_used`
    - `data_points_used`
    - `ocr_answer_agreement`
    - `conflict_with_ocr_answer`
    - `comprehension_confidence`
- `backend` / `admin-web`
  - workbench 展示 `LLM Understanding`
  - `calculation_reasoning` 裸显为空时显示 `未提供`
  - OCR/LLM 冲突时展示 `答案冲突`

本轮目标不是引入真实 DeepSeek / Qwen text / MiMo text 调用，而是先把数据结构、质量门禁和 UI 闭环跑通。

## 7. Quality Gate 置信度规则

新增 `DataAnalysisQualityGate`，并回灌到既有 parse quality gate。

硬阻止条件已落地到 `pdf-service/commercial_ocr/data_analysis.py`：

- shared material 缺失
- question range 非连续或非法
- 17-20 子题未共享同一 `material_id`
- 任一题缺失 `provider_bbox`
- `layout_only=true` 被当成完整题
- `shared_assets` 缺失
- 表头/图表标题/单位缺失
- LLM 无法理解材料
- LLM 无法解题
- 缺少计算过程
- OCR 答案与 LLM 答案冲突
- `local_stem` 被 `shared_stem` 污染

待审核条件：

- `fallback_used=true`
- `comprehension_confidence < 0.9`
- visual warnings / understanding warnings 存在

放行条件：

- `review_ready=true`
- `needs_human_review=false`
- `comprehension_confidence >= 0.9`

`backend/src/modules/question/question.service.ts` 也已将 `data_analysis_quality_gate` 接入发布门禁，避免资料分析题在冲突或低置信度下被误发布。

## 8. Workbench 展示结果

主流程已经从 `/banks` 直达 `/workbench?bankId=<id>`：

- `admin-web/src/views/banks/BankListView.vue`
  - 题库名点击进入 workbench
  - 新增“资料分析工作台”入口
- `admin-web/src/router/index.ts`
  - `/banks/:id/questions` 改为 redirect 到 `/workbench?bankId=...&taskId=...`
- `admin-web/src/views/workbench/ImmersiveWorkbench.vue`
  - header 文案替换为：
    - `待审核`
    - `审核通过`
    - `需复核`
    - `打开 H5 预览`
    - `发布到题库`
  - 删除“保留草稿”
  - 新增 4 个资料分析区块：
    - `17-20 Shared Material`
    - `VLM Visual Context`
    - `LLM Understanding`
    - `Quality Gate`
  - 切换 17/18/19/20 时共享材料保持不丢

## 9. E2E 测试结果

本轮实际执行：

| 命令 | 结果 |
|------|------|
| `./scripts/e2e/start-commercial-ocr-stack.sh` | PASS（使用持久 shell 托管服务） |
| `cd pdf-service && ./.venv/bin/python -m pytest tests/test_commercial_ocr_pipeline.py tests/test_commercial_ocr_quality_gate.py tests/test_commercial_ocr_visual_understanding.py tests/test_commercial_ocr_semantic_assembler.py -q` | `21 passed` |
| `cd backend && node --require ts-node/register --require tsconfig-paths/register test/pdf-review-workflow.test.ts` | PASS（测试内包含预期的 PDF 下载失败日志） |
| `cd backend && pnpm build` | PASS |
| `cd admin-web && pnpm build` | PASS |
| `cd h5-web && pnpm build` | PASS |
| `pnpm exec playwright test e2e/ --trace=on` | `9 passed` |

补充说明：

- `cd backend && pnpm test`
  - skipped
  - 原因：`backend/package.json` 没有 `test` script
- 真实 `qwen-vl` / `doubao-vl` / `deepseek` / `mimo`
  - skipped by env
  - 原因：本轮按要求默认 mock，不依赖真实 key

Playwright 覆盖到的资料分析主链路：

1. `/banks` 点击资料分析题库进入 `/workbench`
2. 旧 `/banks/:bankId/questions` redirect 到 `/workbench`
3. workbench 显示 17-20 shared material
4. bbox overlay / quality gate / calculation reasoning 可见
5. 冲突 fixture 进入 `needs_human_review`
6. H5 preview 中 17-20 shared material 保持不丢
7. 页面不出现 `undefined` / `[object Object]` / `null` 裸显

## 10. 暂未覆盖的题型

本轮没有扩展以下题型主链路：

- 言语理解
- 判断推理
- 数量关系
- 常识判断
- 图形推理

这些题型当前仍可保留旧链路或 mock，不在 COCR-M20A 验收范围。

## 11. 重复代码分类

| 模块 | 分类 | 说明 |
|------|------|------|
| local parser | `fallback_only` | 仍是 commercial OCR 失败时的最终兜底；一旦走到 fallback，资料分析 gate 会进入 `needs_human_review` |
| page_understanding | `deprecated` | 仍存在于 `parser_kernel/adapter.py` 的旧视觉链路和 debug 产物中，但不是 M20A 主审核链路 |
| semantic_groups | `deprecated` | 旧 parser-kernel semantic debug 输出保留兼容；新 workbench 主消费的是 `commercial_ocr.material_group` |
| recrop_plan | `deprecated` | 保留旧 debug 计划输出，不作为资料分析主链路依赖 |
| visual_understanding | `active` | 仍在主链路中，但职责被限制为 visual context，不做主 OCR / 主 bbox |
| mimo_reviewer | `deprecated` | 保留历史 reviewer 能力；本轮不作为资料分析视觉主层 |
| commercial_ocr providers | `active` | 当前资料分析主识别层，百度/腾讯/mock 均在 provider registry 中 |
| bbox normalizer | `active` | 商业 OCR 输出进入 semantic assembler 前的统一入口 |
| pipeline.py | `active` | FastAPI `/parse-by-url` 仍通过 `pipeline.parse_pdf` 进入全链路 |
| models.py | `active` | 仍是 parse result / page content 的共享数据模型 |
| ai_client.py | `active` | 旧视觉链路、provider config 和未来真实模型接线仍依赖它；本轮真实 data-analysis 模型调用默认 skipped |

本轮没有把任何模块提升到 `removable`，因为资料分析主链路刚落地，还需要后续更大范围覆盖后再收缩旧代码。

## 12. 下一步如何扩展到图形推理 / 言语理解 / 判断推理

建议按“复用资料分析骨架、替换中间理解层”的方式扩展：

1. 图形推理
   - 复用 OCR bbox、workbench overlay、quality gate 壳子
   - 将 VLM visual context 改为“图形元素、旋转/镜像/数量变化、选项差异摘要”
   - LLM 输出改为“图形规律解释 + 选项排除过程”
2. 言语理解
   - 共享材料模型可继续复用到长段落阅读
   - VLM 作用缩小为版面完整性、跨栏/跨页完整性检查
   - LLM 侧重点改为句间关系、主旨、指代、排序推理
3. 判断推理
   - 定义新的 `question_subtype` 和 reasoning schema
   - VLM 仅处理流程图/表格/示意图类题面
   - LLM 输出演绎链、假设排除和冲突点

推荐下一阶段原则：

- 先按题型逐个扩，不要一次铺开全部
- 每个题型都坚持 OCR API First，不把 VLM 拉回主 OCR
- 每个题型都先在 workbench 验收，再考虑其他页面复用

## 证据路径

- 阶段报告: `docs/commercial-ocr-phase-reports/COCR-M20A-data-analysis-first.md`
- Playwright 证据目录: `debug/e2e-commercial-ocr/2026-05-05T15-03-11-354Z/`
- Playwright trace: `test-results/`
- agent 汇总报告: `.agent/reports/data-analysis-first-ocr-api-understanding-report.md`
- handoff: `.agent/handoff/data-analysis-first-ocr-api-understanding-20260505-230923.md`

## 风险与后续

- 真实 `qwen-vl` / `doubao-vl` / `deepseek` / `mimo` 仍未 smoke，当前只验证 mock 契约
- `page_understanding` / `semantic_groups` / `recrop_plan` 旧链路尚未正式下线
- backend 没有统一 `pnpm test` script，当前仍需靠 targeted workflow script 补位
