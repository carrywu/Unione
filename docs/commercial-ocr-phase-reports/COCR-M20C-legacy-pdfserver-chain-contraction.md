# COCR-M20C: Legacy PDF-Service Chain Contraction

## 1. 结论

M20C 没有大删旧链路，但已经进一步证明：

- `commercial_ocr.*` 是资料分析主审核链路的权威来源
- `page_understanding`、`semantic_groups`、`recrop_plan` 仍可保留给旧 review/debug 页面看证据，但不再是 bbox 和 material group 的权威来源
- `local_parser` 只应作为最终兜底；一旦走到 `fallback_used=true`，必须强制 `needs_human_review=true`

## 2. 表 1：pdf-service 定位/裁切相关模块

| 文件 | 函数/类 | 当前作用 | 是否仍参与资料分析主链路 | 是否会生成 bbox | 是否会覆盖 OCR provider bbox | 分类 | 本轮处理 | 后续建议 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `pdf-service/commercial_ocr/service.py` | `run_commercial_ocr_pipeline` | 串起 provider -> semantic assembler -> visual context -> understanding -> quality gate，并生成 `bbox_source`/`fallback_used` | 是 | 是 | 否 | `active_new_chain` | 保持为主入口；继续支持 precomputed import | 不可删 |
| `pdf-service/commercial_ocr/semantic_assembler.py` | `assemble_semantic_result` | 组装 shared material / normalized questions，保留 provider 语义 | 是 | 否 | 否 | `active_new_chain` | 保持对 17-20 资料分析的权威分组 | 不可删 |
| `pdf-service/commercial_ocr/data_analysis.py` | visual/understanding/gate builders | 负责资料分析 visual context、LLM understanding、quality gate | 是 | 否 | 否 | `active_new_chain` | 继续作为资料分析门禁核心 | 不可删 |
| `pdf-service/parser_kernel/adapter.py` | `page_understanding` 相关构建 | 旧视觉页理解和 debug 产物 | 否 | 否 | 否 | `deprecated_compat` | 保留给旧 review/source_artifacts 诊断 | 下轮可继续弱化 UI 可见性 |
| `pdf-service/parser_kernel/adapter.py` | `semantic_groups` debug 构建 | 旧 parser semantic debug 输出 | 否 | 否 | 否 | `deprecated_compat` | 保留兼容，不再驱动资料分析主链 | 下轮可收缩为 debug-only |
| `pdf-service/parser_kernel/adapter.py` | `recrop_plan` debug 构建 | 旧裁切计划 debug 输出 | 否 | 否 | 否 | `removable_later` | 仍保留文件输出，但不参与 bbox/material 判定 | 下轮可优先删除或彻底隐藏 |
| `pdf-service/parser_kernel/adapter.py` | local parser fallback path | 商业 OCR 全失败时的最终兜底 | 仅 fallback | 是 | 仅在 fallback 选中时成为来源 | `fallback_only` | 保持可回退，但资料分析 gate 明确拉人工复核 | 不可当作默认主链 |
| `pdf-service/commercial_ocr/fixtures.py` | precomputed import loader | 供 E2E / import / replay 注入真实 smoke 结果 | 否 | 否 | 只在导入时显式指定 | `test_only` | M20C 继续用于 real batch workbench import | 保持 test-only |

## 3. 表 2：admin 路由 / UI

| 路由 / 组件 | 当前作用 | 主链路地位 | 本轮结论 | 后续建议 |
| --- | --- | --- | --- | --- |
| `/banks` | 主入口，进入资料分析题库和 workbench | `active` | 继续作为主入口 | 保持 |
| `/workbench` / `ImmersiveWorkbench.vue` | 主审核界面，展示 `bbox_source`、visual context、LLM understanding、quality gate | `active` | 当前资料分析主消费面 | 保持 |
| `/banks/:bankId/questions` | 旧入口 redirect 到 workbench | `deprecated_compat` | 不再是主流程，只保留兼容 | 后续可继续简化 |
| old review page / `PaperReviewView.vue` | 旧人工审核页，仍显示 `source_artifacts_refs.page_understanding/semantic_groups/recrop_plan` | `deprecated_compat` | 可看旧证据，但不应被当成资料分析主链 UI | 下轮可减少误导性字段 |
| H5 preview | 预览 shared material 是否丢失 | `active` | 17-20 真实 batch import 已验证不丢 | 保持 |
| bbox overlay consumer | 消费 `question_quality.commercial_ocr.bbox_overlay.highlights` | `active` | bbox 权威来源已切到 commercial OCR enrichment | 保持 |

## 4. 表 3：backend DTO / publish gate

| 合同 / gate | 当前作用 | 主链路状态 | 本轮结论 | 后续建议 |
| --- | --- | --- | --- | --- |
| `commercial_ocr` fields | 承载 provider、bbox、material_group、`bbox_source`、`fallback_used` | `active` | 资料分析 review / preview / import 的主数据面 | 保持 |
| `data_analysis_visual_context` fields | 展示 `source_material_complete`、表头/单位/图例状态 | `active` | 只能补视觉上下文，不能覆盖 bbox | 保持 |
| `data_analysis_understanding_result` fields | 展示 `calculation_reasoning` 或 refusal reason | `active` | 低置信或缺推理时正确挡住 | 保持 |
| `data_analysis_quality_gate` fields | 控制 approve / publish / preview 放行 | `active` | 对 `needs_human_review`、`fallback_used`、冲突、缺推理生效 | 保持 |

## 5. 清单

active：

- `commercial_ocr/service.py`
- `commercial_ocr/semantic_assembler.py`
- `commercial_ocr/data_analysis.py`
- backend `commercial_ocr` DTO 映射
- workbench / H5 shared material 展示与 gate

fallback_only：

- local parser fallback

deprecated_compat：

- `page_understanding`
- `semantic_groups`
- old review page 上的旧 source artifact 展示

removable_later：

- `recrop_plan`
- 仅为旧 debug 保留的 recovered page-understanding 衍生产物

风险点：

- 旧 review 页仍能看到 `page_understanding` / `semantic_groups` / `recrop_plan`，如果 reviewer 不清楚“谁是权威来源”，会误把旧 debug 当主结果
- 真实 OCR provider 未接入时，`tesseract_local_ocr` 虽然不是 `local_parser`，但仍应按人工复核链路处理
