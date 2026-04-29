# Visual API Smoke 记忆文件

更新时间：2026-04-29

## 当前阶段结论

当前已进入“真实视觉 API smoke”阶段，范围仍然严格限制为小样本：

- 前 1 页
- 前 2 页
- 前 5 页

禁止直接跑 `题本篇.pdf` 225 页全本。

截至本文件更新时间，前 1 页、前 2 页、前 5 页 smoke 均已完成；90 秒 page-level timeout 下小样本稳定。

## 本轮已完成

新增了一个轻量 smoke 工具：

```txt
pdf-service/tools/visual_api_smoke.py
```

它用于真实调用视觉模型，并保存这些诊断产物：

- `raw_model_response.json`
- `page_screenshots/page_001.png`
- `page_parse_summary.json`
- `rejected_candidates.json`
- `debug/visual_pages.json`
- `debug/warnings.json`
- `debug/page_elements.json`
- `debug/question_groups.json`
- `debug/output_questions.json`
- `debug/output_materials.json`

同时补充了截图尺寸限制能力：

```txt
pdf-service/extractor.py
```

`PDFExtractor.get_page_screenshot()` 现在支持：

```python
get_page_screenshot(page_num, dpi=110, max_side=1600)
```

并新增：

```python
get_page_screenshot_size(page_num, dpi=110, max_side=1600)
```

## 当前改动文件

```txt
pdf-service/extractor.py
pdf-service/parser_kernel/adapter.py
pdf-service/tools/visual_api_smoke.py
pdf-service/tests/test_extractor_screenshot_limits.py
pdf-service/tests/test_visual_api_smoke_tool.py
```

## 已验证

新增测试先红后绿：

```bash
cd pdf-service
./.venv/bin/python -m unittest tests.test_visual_api_smoke_tool tests.test_extractor_screenshot_limits -v
```

全量 unittest 已逐文件通过：

```bash
cd pdf-service
for t in tests/test_*.py; do
  m=${t#tests/}
  m=${m%.py}
  ./.venv/bin/python -m unittest tests.$m -v
done
```

编译检查通过：

```bash
cd pdf-service
./.venv/bin/python -m compileall -q .
```

diff 空白检查通过：

```bash
git diff --check
```

## 真实视觉 API smoke 结果

### 1 页，默认 45 秒超时

命令：

```bash
cd pdf-service
./.venv/bin/python tools/visual_api_smoke.py 题本篇.pdf --pages 1 --clean-output
```

输出目录：

```txt
pdf-service/tmp/visual-api-smoke/pages-1
```

结果：

- `request_status`: `failed`
- `warnings`: `vision_page_timeout`, `visual_page_fallback_used`
- `visual_question_candidates`: 0
- `accepted_questions`: 0

判断：45 秒默认超时过短，不代表模型不可用。

### 1 页，临时 90 秒超时

命令：

```bash
cd pdf-service
PDF_VISUAL_PAGE_TIMEOUT_SECONDS=90 ./.venv/bin/python tools/visual_api_smoke.py 题本篇.pdf --pages 1 --output-dir tmp/visual-api-smoke/pages-1-timeout90 --clean-output
```

输出目录：

```txt
pdf-service/tmp/visual-api-smoke/pages-1-timeout90
```

结果：

- `request_status`: `ok`
- `attempts`: 1
- `warnings`: `visual_bbox_clamped`
- `image_size`: `910 x 1286`
- `base64_size`: `375936`
- `raw_question_candidates`: 4
- `normalized_question_candidates`: 4
- `kernel_question_candidates`: 4
- `accepted_questions`: 4
- `rejected_candidates`: 0

识别出的题目预览：

1. `2021 年 7 月份，全国发电量大约是多少亿千瓦时`
2. `2022 年 1～7 月份，全国城乡居民生活用电量比 2021 年 1～7 月份约多`
3. `2021 年 7 月份，全社会用电量中第三产业用电量的占比与城乡居民生活用电量的占比相较约`
4. `2021 年 1～6 月全社会用电量累计约多少亿千瓦时`

判断：真实视觉模型可以稳定产出 candidate questions；当前关键参数是 page-level timeout。

### 2 页，临时 90 秒超时

命令：

```bash
cd pdf-service
PDF_VISUAL_PAGE_TIMEOUT_SECONDS=90 ./.venv/bin/python tools/visual_api_smoke.py 题本篇.pdf --pages 2 --output-dir tmp/visual-api-smoke/pages-2-timeout90 --clean-output
```

输出目录：

```txt
pdf-service/tmp/visual-api-smoke/pages-2-timeout90
```

结果：

- `pages_attempted`: 2
- 每页 `request_status`: `ok`
- 每页 `attempts`: 1
- `attempt_errors`: 空
- 每页 `warnings`: `visual_bbox_clamped`
- `visual_question_candidates`: 7
- `kernel_question_candidates`: 7
- `accepted_questions`: 7
- `rejected_candidates`: 0
- `reject_reasons`: 空

补充观察：

- 第 2 页第 5 题有 `backward_material_link_low_confidence` / `material_range_uncertain`
- `debug/warnings.json` 中对应一条 `visual_link_warnings`
- 该 warning 与 AGENTS.md 中“题在上、材料在下允许低置信回挂”的规则一致

判断：2 页稳定，无 retry、无 timeout、无 rejected candidates。

### 5 页，临时 90 秒超时

命令：

```bash
cd pdf-service
PDF_VISUAL_PAGE_TIMEOUT_SECONDS=90 ./.venv/bin/python tools/visual_api_smoke.py 题本篇.pdf --pages 5 --output-dir tmp/visual-api-smoke/pages-5-timeout90 --clean-output
```

输出目录：

```txt
pdf-service/tmp/visual-api-smoke/pages-5-timeout90
```

结果：

- `pages_attempted`: 5
- 每页 `request_status`: `ok`
- 每页 `attempts`: 1
- `attempt_errors`: 空
- 每页 `warnings`: `visual_bbox_clamped`
- `visual_question_candidates`: 20
- `kernel_question_candidates`: 20
- `accepted_questions`: 20
- `rejected_candidates`: 0
- `reject_reasons`: 空

每页 candidate 数：

- 第 1 页：4
- 第 2 页：3
- 第 3 页：3
- 第 4 页：5
- 第 5 页：5

补充观察：

- `debug/warnings.json` summary：`page_elements_count=109`、`materials_count=4`、`visuals_count=109`
- parser warnings 仅为 1～5 页各自的 `visual_bbox_clamped`
- visual link warnings 仍只有第 2 页第 5 题的 `backward_material_link_low_confidence`
- `rejected_candidates.json` 为空

判断：5 页小样本稳定。后续已确认 `visual_bbox_clamped` 是 PyMuPDF `Rect` 求交后的浮点精度误报，不是实际 bbox 越界或截图归属错误。

### 5 页，修复 bbox clamp 误报后复跑

问题定位：

- `parser_kernel/adapter.py` 中 `_bbox_to_page_rect()` 使用 `normalized != original` 直接比较浮点坐标。
- PyMuPDF `rect & page_rect` 即使没有真实裁剪，也会产生 `1e-5` 级浮点差异。
- 因此每页都会误报 `visual_bbox_clamped`。
- 对 5 页样本的 129 个原始模型 bbox 做同尺度校验后，没有任何真实越界；`debug/visual_pages.json` 中 regions 也没有贴边或跨页。

修复：

```txt
pdf-service/parser_kernel/adapter.py
pdf-service/tests/test_scanned_question_book_kernel.py
```

新增回归测试：

```bash
cd pdf-service
./.venv/bin/python -m unittest tests.test_scanned_question_book_kernel.ScannedQuestionBookKernelTest.test_in_bounds_visual_bboxes_do_not_emit_clamped_warning -v
```

该测试先红后绿。实现改为使用 `VISUAL_BBOX_CLAMP_EPSILON = 1e-3` 容差，只在真实裁剪超过微小浮点误差时记录 `visual_bbox_clamped`。

复跑命令：

```bash
cd pdf-service
PDF_VISUAL_PAGE_TIMEOUT_SECONDS=90 ./.venv/bin/python tools/visual_api_smoke.py 题本篇.pdf --pages 5 --output-dir tmp/visual-api-smoke/pages-5-timeout90-bbox-fix --clean-output
```

输出目录：

```txt
pdf-service/tmp/visual-api-smoke/pages-5-timeout90-bbox-fix
```

复跑结果：

- `pages_attempted`: 5
- 每页 `request_status`: `ok`
- 每页 `attempts`: 1
- 每页 `warnings`: 空
- `visual_question_candidates`: 20
- `kernel_question_candidates`: 20
- `accepted_questions`: 20
- `rejected_candidates`: 0
- `reject_reasons`: 空
- `debug/warnings.json` 中 parser warnings 均为空
- visual link warnings 仍只有第 2 页第 5 题的 `backward_material_link_low_confidence`

判断：bbox clamp 误报已消除；当前剩余 warning 只与跨页/前页材料低置信回挂有关。

### 可视化 debug image export

新增调试导出能力，只用于 smoke/debug，不改变 parser 主规则：

```txt
pdf-service/tools/visual_debug_exporter.py
pdf-service/tools/visual_api_smoke.py
pdf-service/tests/test_visual_api_smoke_tool.py
```

导出内容：

- `debug/overlays/page_001_overlay.png` 等每页 overlay 图
- `debug/crops/page_XXX_qYYY_conf_ZZ_crop.png` 每题 crop
- `debug/crops/page_XXX_material_<id>_conf_ZZ_crop.png` 每个材料 crop
- `debug/bbox_lineage.json` 记录 raw / expanded / clamped / final bbox、clamp_reason、source_candidate_id、linked_question_id、linked_material_id、warnings

颜色约定：

- question：绿色
- material：蓝色
- visual：橙色
- warning / low confidence：红色
- final crop bbox：紫色；如果有 warning 或低置信，则用红色

真实 5 页复跑命令：

```bash
cd pdf-service
PDF_VISUAL_PAGE_TIMEOUT_SECONDS=90 ./.venv/bin/python tools/visual_api_smoke.py 题本篇.pdf --pages 5 --output-dir tmp/visual-api-smoke/pages-5-timeout90-debug-images --clean-output
```

输出目录：

```txt
pdf-service/tmp/visual-api-smoke/pages-5-timeout90-debug-images
```

验证结果：

- `debug/overlays/` 生成 5 张 overlay 图
- `debug/crops/` 生成 26 张 crop 图
- `debug/bbox_lineage.json` 生成 26 条 lineage
- 5 页仍全部 `request_status=ok`
- 每页 `warnings`: 空
- `accepted_questions`: 20
- `rejected_candidates`: 0

第 2 页第 5 题重点产物：

```txt
pdf-service/tmp/visual-api-smoke/pages-5-timeout90-debug-images/debug/overlays/page_002_overlay.png
pdf-service/tmp/visual-api-smoke/pages-5-timeout90-debug-images/debug/crops/page_002_q005_conf_0.70_crop.png
pdf-service/tmp/visual-api-smoke/pages-5-timeout90-debug-images/debug/crops/page_002_material_m_2_conf_0.85_crop.png
```

第 2 页第 5 题 lineage：

- `linked_question_id`: 5
- `linked_material_id`: `m_2`
- `warnings`: `backward_material_link_low_confidence`, `material_range_uncertain`
- `visual_bbox_clamped`: false
- `clamp_reason`: 空

肉眼快速判断：overlay 上 q005 红框位于页面上方，材料 m_2 蓝框位于其下方，图表橙框在材料区域内；当前可以直接打开 overlay/crop 判断第 2 页第 5 题是否应回挂该材料。

## 下次继续步骤

继续不要跑 225 页全本。下一步应先分析 5 页产物，而不是继续扩大页数：

1. 对比页面截图和 bbox/debug 产物：

```txt
pdf-service/tmp/visual-api-smoke/pages-5-timeout90/page_screenshots/*.png
pdf-service/tmp/visual-api-smoke/pages-5-timeout90/debug/page_elements.json
pdf-service/tmp/visual-api-smoke/pages-5-timeout90/debug/question_groups.json
pdf-service/tmp/visual-api-smoke/pages-5-timeout90/debug/output_questions.json
pdf-service/tmp/visual-api-smoke/pages-5-timeout90/debug/output_materials.json
```

2. 重点确认：

- 第 2 页第 5 题低置信材料回挂是否符合预期
- `output_questions.json` 中题目序号/content 是否连续且合理
- `output_materials.json` 是否能表达材料与题组关系

## 当前不要做

- 不要迁移到 pytest。
- 不要扩大 parser scope。
- 不要大重构 adapter。
- 不要直接跑 225 页全本。
- 不要引入新依赖。
