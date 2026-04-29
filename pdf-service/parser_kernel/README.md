# parser_kernel

`parser_kernel` 是 `pdf-service` 内部唯一的题目解析内核。

目标：
- 统一治理题目边界
- 统一治理材料归属
- 统一治理图表归属
- 让所有题本入口都走同一套规则

不做的事：
- 不改 API 路径
- 不改前后端
- 不改 `models.py` 字段语义
- 不为 `question_splitter.py`、`TextStrategy`、其他 fallback 保留第二套切题规则

## 模块

- `routing.py`
  - 判定 `text_layer_book`
  - 判定 `scanned_question_book`
  - 判定 `scanned_answer_book`
  - 判定 `answer_note`

- `layout_engine.py`
  - 把页面块标准化成统一 `PageElement` 输入

- `semantic_segmenter.py`
  - 标注 `question_anchor`
  - 标注 `option`
  - 标注 `material_prompt`
  - 过滤 `directory_heading` / `teaching_text`

- `question_group_builder.py`
  - 建立 `MaterialGroup`
  - 建立 `QuestionGroup`
  - 保证“下一段材料不要吞进上一题”

- `adapter.py`
  - 把 text-layer 和 visual fallback 都接到统一内核
  - 输出兼容旧调用方的 `RawQuestion` / strategy payload
  - 落 debug bundle

## 扫描题本路径

`scanned_question_book` 流程：

1. 整页截图
2. 调用视觉模型返回题目 / 材料 / 图表 / bbox
3. 归一化视觉结果 schema
4. 转成统一 `PageContent`
5. 回到 `layout_engine -> semantic_segmenter -> question_group_builder -> adapter`

视觉返回必须带入 debug：
- `raw_result`
- `normalized_result`
- `schema_validation`
- `page_warnings`
- `regions`

## 稳定性规则

- 视觉调用按页隔离
- 单页超时不能拖垮整本
- 超时页输出 `vision_page_timeout`
- 超时或失败页尽量保留 `page_fallback` 整页截图，供人工审核
- bbox 越界或坏框不允许抛异常中断整本；要裁剪、跳过或降级

当前 page-level timeout 默认值在 `adapter.py` 中配置：
- `DEFAULT_VISUAL_PAGE_TIMEOUT_SECONDS = 45.0`
- 可由 `PDF_VISUAL_PAGE_TIMEOUT_SECONDS` 覆盖

## 材料归属规则

优先级：

1. 视觉模型显式给出的 `material_temp_id`
2. 题组范围命中
3. 同页低置信后置材料回挂

同页低置信回挂场景：
- 题锚点/题干在页上半部分
- 材料或图表在同页后半部分
- 后续题显式挂到了这段材料

这种情况下，内核允许把前面的题回挂到后置材料，但必须保留：
- `backward_material_link_low_confidence`
- `material_range_uncertain`
- `needs_review=true`

## 兼容入口

- `question_splitter.py`
  - 兼容壳，实际调用 `parser_kernel`

- `strategies/text_strategy.py`
  - fallback 调用 `parse_extractor_with_kernel`

后续如果接入 markdown/layout-first 链路，也必须复用这套内核，而不是复制一套切题规则。

## 调试输出

`write_debug_bundle()` 当前会输出：

- `visual_pages.json`
- `page_elements.json`
- `annotated_elements.json`
- `material_groups.json`
- `question_groups.json`
- `raw_questions.json`
- `output_questions.json`
- `output_materials.json`
- `warnings.json`

这些文件用于审核：
- 视觉模型原始返回
- 归一化后的页面元素
- 题组 / 材料组
- warnings 和低置信回挂
