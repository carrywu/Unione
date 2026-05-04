# PDF Visual Debug Agent Task

## 目标

不要只修图片归属，要修完整 PDF 审核链路。

当前真实 bug：

1. 例 1 的图片卡是 p1-img1，右侧预览也对，但左侧原卷定位橙色框把例 2 的图也框进去了。
2. 例 2 的图片卡是 p1-img2，右侧预览也对，但左侧原卷定位框包含了例 1 尾部。
3. 所以问题不是单纯 question.images，而是 source_bbox / 原卷定位框 / review region 跨题。

## 必须做

1. 建立 Visual Debug Harness。
2. 覆盖真实 PDF 的例 1-10，不要只测例 1-4。
3. 导出 layout.json。
4. 生成 overlay 图片，图上必须画：
   - 橙色：source_bbox
   - 蓝色：visual bbox
   - 绿色：question marker
   - 紫色：LayoutElement
5. 生成 VISUAL_DEBUG_REPORT.md。
6. 让你自己查看 overlay 图片，判断橙色框有没有吞相邻题图表。
7. 修复 source_bbox 边界。
8. 确认 backend review API 没有重新混合 bbox/images。
9. 确认 admin-web 左侧原卷定位使用正确字段。

## 重点验收

例 1-10 必须全部检查。

强制断言：

1. 例 1 visual_ids 是 p1-img1。
2. 例 1 source_bbox 不能覆盖 p1-img2。
3. 例 2 visual_ids 是 p1-img2。
4. 例 2 source_bbox 不能覆盖例 1 主体区域。
5. 例 3 visual_ids 是 p2-img1。
6. 例 3 source_bbox 不能覆盖 p2-img2。
7. 例 4 visual_ids 是 p2-img2。
8. 例 4 source_bbox 不能覆盖 p2-img1。
9. 例 5-10 也必须检查 visual_ids 和 source_bbox，不允许只跳过。
10. 每题 source_bbox 不应包含页眉、页码、章节标题、下一题图表标题。

## 建议新增文件

在 pdf-service 下新增：

- debug_tools/export_visual_debug.py
- debug_tools/draw_overlay.py
- debug_tools/visual_assertions.py
- debug_tools/cases/example_1_10.yml

输出到：

- debug_artifacts/example_1_10/layout.json
- debug_artifacts/example_1_10/page*_overlay.png
- debug_artifacts/example_1_10/VISUAL_DEBUG_REPORT.md

debug_artifacts 不要提交。

## 修复方向

优先检查：

- pdf-service/block_segmenter.py
- pdf-service/visual_linker.py
- pdf-service/layout_models.py
- pdf-service/parser_kernel/adapter.py
- backend/src/modules/question/question.service.ts
- admin-web/src/views/banks/BankReviewView.vue

source_bbox 应主要基于当前题的题干和选项文本。

source_bbox 不应该合并：

- image
- table
- caption
- heading
- 页眉
- 页脚
- 下一题图表标题
- 相邻题内容

visual_ids 负责题目图片展示，不要和 source_bbox 混用。

## 必跑命令

完成后运行：

```bash
cd pdf-service
.venv/bin/python debug_tools/export_visual_debug.py --case debug_tools/cases/example_1_10.yml --out debug_artifacts/example_1_10
.venv/bin/python -m unittest tests.test_pdf_review_flow_rules -v

cd ../backend
npx ts-node -r tsconfig-paths/register test/pdf-review-workflow.test.ts
corepack pnpm build

cd ../admin-web
corepack pnpm build

cd ..
git diff --check
