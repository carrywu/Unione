# Implementation Log

更新时间：2026-04-29

## 2026-04-29

### 本次改动概述

把 PDF 题库解析与后台审核编辑链路推进到可交付状态：

- 后台审核页支持直接编辑题干、选项、答案、解析、题型和图片元数据。
- 图片支持删除、排序、移动到上一题/下一题、修改插入位置。
- 新增单题 AI 修复入口，结果只作为候选建议，不自动持久化。
- PDF 服务与后端新增页眉页脚黑名单、单题修复和低置信发布拦截。
- PDF 解析规则增强：页眉页脚过滤、题号边界识别、视觉归属、表格合并、Validator 兜底。

### 修改文件

- `[admin-web/src/views/banks/BankReviewView.vue](/Users/apple/Downloads/公考/project2/admin-web/src/views/banks/BankReviewView.vue)`
- `[admin-web/src/api/question.ts](/Users/apple/Downloads/公考/project2/admin-web/src/api/question.ts)`
- `[admin-web/src/api/pdf.ts](/Users/apple/Downloads/公考/project2/admin-web/src/api/pdf.ts)`
- `[backend/src/modules/question/entities/question.entity.ts](/Users/apple/Downloads/公考/project2/backend/src/modules/question/entities/question.entity.ts)`
- `[backend/src/modules/question/dto/update-question.dto.ts](/Users/apple/Downloads/公考/project2/backend/src/modules/question/dto/update-question.dto.ts)`
- `[backend/src/modules/question/dto/question-review.dto.ts](/Users/apple/Downloads/公考/project2/backend/src/modules/question/dto/question-review.dto.ts)`
- `[backend/src/modules/question/question.controller.ts](/Users/apple/Downloads/公考/project2/backend/src/modules/question/question.controller.ts)`
- `[backend/src/modules/question/question.service.ts](/Users/apple/Downloads/公考/project2/backend/src/modules/question/question.service.ts)`
- `[backend/src/modules/pdf/pdf.controller.ts](/Users/apple/Downloads/公考/project2/backend/src/modules/pdf/pdf.controller.ts)`
- `[backend/src/modules/pdf/pdf.service.ts](/Users/apple/Downloads/公考/project2/backend/src/modules/pdf/pdf.service.ts)`
- `[backend/test/pdf-review-workflow.test.ts](/Users/apple/Downloads/公考/project2/backend/test/pdf-review-workflow.test.ts)`
- `[backend/test/pdf-publish-export.test.ts](/Users/apple/Downloads/公考/project2/backend/test/pdf-publish-export.test.ts)`
- `[backend/test/pdf-debug.service.test.ts](/Users/apple/Downloads/公考/project2/backend/test/pdf-debug.service.test.ts)`
- `[pdf-service/models.py](/Users/apple/Downloads/公考/project2/pdf-service/models.py)`
- `[pdf-service/ai_client.py](/Users/apple/Downloads/公考/project2/pdf-service/ai_client.py)`
- `[pdf-service/main.py](/Users/apple/Downloads/公考/project2/pdf-service/main.py)`
- `[pdf-service/pipeline.py](/Users/apple/Downloads/公考/project2/pdf-service/pipeline.py)`
- `[pdf-service/validator.py](/Users/apple/Downloads/公考/project2/pdf-service/validator.py)`
- `[pdf-service/parser_kernel/layout_engine.py](/Users/apple/Downloads/公考/project2/pdf-service/parser_kernel/layout_engine.py)`
- `[pdf-service/parser_kernel/semantic_segmenter.py](/Users/apple/Downloads/公考/project2/pdf-service/parser_kernel/semantic_segmenter.py)`
- `[pdf-service/parser_kernel/adapter.py](/Users/apple/Downloads/公考/project2/pdf-service/parser_kernel/adapter.py)`
- `[pdf-service/tests/test_pdf_review_flow_rules.py](/Users/apple/Downloads/公考/project2/pdf-service/tests/test_pdf_review_flow_rules.py)`

### 关键原因

- 题目审核页原本能看、能定位，但人工修复效率不够，无法在后台完成完整纠错闭环。
- PDF 解析的核心问题不是单点 OCR，而是边界、视觉归属和低置信结果缺少统一规则。
- 发布流程缺少“低置信不自动发布”的硬约束，容易把不稳定结果直接推给 H5。

### 接口变更

- `PATCH /admin/questions/:id`
- `POST /admin/questions/:id/images`
- `DELETE /admin/questions/:id/images/:imageKey`
- `PATCH /admin/questions/:id/images/reorder`
- `POST /admin/questions/:id/move-image`
- `POST /admin/questions/:id/ai-repair`
- `POST /admin/questions/:id/split`
- `POST /admin/questions/:id/merge`
- `POST /admin/pdf/crop-region`
- `POST /admin/pdf/header-footer-blacklist`
- `POST /repair-question`

### 数据库字段

- 新增/复用：
  - `questions.visual_refs`
  - `questions.review_status`
  - `questions.source_page_start`
  - `questions.source_page_end`
  - `questions.source_bbox`
  - `questions.parse_confidence`
  - `questions.parse_warnings`
  - `questions.images[].image_role`
  - `questions.images[].image_order`
  - `questions.images[].insert_position`
  - `questions.images[].same_visual_group_id`
- 生产环境若不启用 TypeORM `synchronize`，需要补迁移。

### 验证结果

- `backend`: `corepack pnpm build` 通过。
- `backend`: `npx ts-node -r tsconfig-paths/register test/pdf-review-workflow.test.ts` 通过。
- `backend`: `npx ts-node -r tsconfig-paths/register test/pdf-publish-export.test.ts` 通过。
- `backend`: `npx ts-node -r tsconfig-paths/register test/pdf-debug.service.test.ts` 通过。
- `admin-web`: `corepack pnpm build` 通过。
- `h5-web`: `corepack pnpm build` 通过。
- `pdf-service`: `.venv/bin/python -m unittest discover -s tests` 通过，47 tests。
- `pdf-service`: `.venv/bin/python -m compileall ai_client.py main.py models.py parser_kernel pipeline.py validator.py tests/test_pdf_review_flow_rules.py` 通过。

### 已知风险

- 目前是“规则 + AI + validator + 人工审核”的可交付版本，不是完全自动化。
- `review_status` 目前靠 TypeORM 同步；正式环境建议迁移固定字段。
- 审核页已支持单题 AI 修复，但还没有做成“先应用建议到编辑框再确认”的更细粒度 diff 视图。
- “合并相邻图片”的 UI 还未做成一键操作，当前主要依靠解析层的 `same_visual_group_id` 与手工排序。

### 追加改动：审核页显式人工修复入口

- 新增 `POST /admin/questions/:id/images/merge`，用于把当前题相邻两张图片标记为同一个 `same_visual_group_id`。
- 审核页题图卡片新增“合并下一张”按钮，解决表格被拆成多张时缺少显式人工标记入口的问题。
- 审核页新增页眉页脚黑名单输入入口，也支持读取当前页面选中文本后提交到 `POST /admin/pdf/header-footer-blacklist`。
- 移动端预览改为按 `insert_position` 分区渲染题图：题干上方、题干下方、选项上方、选项下方。
- 追加并通过后端回归：`testMergeAdjacentQuestionImagesMarksSharedGroup`。

### 追加验证

- `backend`: `npx ts-node -r tsconfig-paths/register test/pdf-review-workflow.test.ts` 通过。
- `backend`: `corepack pnpm build` 通过。
- `admin-web`: `corepack pnpm build` 通过。
