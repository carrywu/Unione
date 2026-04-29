# PDF 题库解析与审核编辑交付任务

更新时间：2026-04-29

## 当前目标

把资料分析 PDF 解析链路从“纯切块解析”推进到可交付的半自动题库生产流程：

- 规则定位题目、页眉页脚、图表区域。
- AI 只做单题候选修复，不直接发布或无确认覆盖。
- Validator 对低置信、边界冲突、图片归属异常做兜底。
- 后台审核页可以人工编辑题干、选项、答案、解析、图片和发布状态。

## 项目勘察结果

### admin-web

- 审核页：`admin-web/src/views/banks/BankReviewView.vue`
  - 已有题目列表、审核筛选、移动端预览、PDF 定位入口。
  - 本次扩展为可直接编辑题干、选项、答案、解析、题型、图片顺序和图片插入位置。
- PDF 定位/框选页：`admin-web/src/views/banks/QuestionPreviewView.vue`
  - 已有 PDF.js 定位、区域框选 OCR、保存框选区域为题目/材料图片、图片替换/删除、AI 可读性预审。
  - 本次未破坏该页面，审核页继续保留“PDF定位”入口。
- API：`admin-web/src/api/question.ts`、`admin-web/src/api/pdf.ts`
  - 复用现有 `getQuestion`、`updateQuestion`、`ocrPdfRegion`。
  - 新增图片操作、AI 单题修复、发布结果返回字段类型。

### backend

- 题目实体：`backend/src/modules/question/entities/question.entity.ts`
  - 已有 `source_page_start`、`source_page_end`、`source_bbox`、`parse_confidence`、`parse_warnings`、`images` 等字段。
  - 本次新增 `visual_refs`、`review_status`。
- 材料实体：`backend/src/modules/question/entities/material.entity.ts`
  - 已有 `images`、`page_range`、`image_refs`、`raw_text`、`parse_warnings`。
- 解析任务实体：`backend/src/modules/pdf/entities/parse-task.entity.ts`
  - 已有任务状态、进度、结果摘要。
- 控制器/服务：
  - `AdminQuestionController`/`QuestionService` 已存在，本次扩展，不新增重复 controller/service。
  - `PdfController`/`PdfService` 已存在，本次扩展 crop-region、黑名单、发布低置信拦截。
- 权限：
  - 管理接口继续复用 `JwtAuthGuard`、`RolesGuard`、`@Roles('admin')`。
- 上传：
  - 手动截图继续复用已有 `UploadService.uploadBuffer`。

### pdf-service

- 主链路：`pdf-service/pipeline.py`
- 视觉/解析入口：`pdf-service/main.py`
- AI 封装：`pdf-service/ai_client.py`
- Validator：`pdf-service/validator.py`
- Parser kernel：
  - `pdf-service/parser_kernel/layout_engine.py`
  - `pdf-service/parser_kernel/semantic_segmenter.py`
  - `pdf-service/parser_kernel/question_group_builder.py`
  - `pdf-service/parser_kernel/adapter.py`
- 数据模型：`pdf-service/models.py`

## 根因判断

- 页眉混入：主 parser kernel 对跨页重复顶部/底部短文本没有统一过滤。
- 题目边界混乱：`根据材料...` 题干曾优先被识别为材料 prompt，导致 `1. 根据材料...` 被从题块中拿走。
- 图表错位：视觉结果中的未显式绑定图表缺少“向下最近题号/下一视觉种子前”的归属规则，容易被错误合并到前一题或第一页第一题。
- 表格拆分：同页相邻 table/image bbox 缺少合并规则和重新截图逻辑。
- 发布风险：解析任务发布曾可能把低置信、warning 题直接发布到 H5。
- 审核效率：轻量审核页不能直接处理图片删除、排序、移动、插入位置和单题 AI 修复。

## Phase 状态

### Phase 1：后台人工编辑闭环

状态：已完成核心闭环。

- 题干、A/B/C/D、答案、解析、题型可编辑。
- 图片可删除、上移/下移、移动到上一题/下一题。
- 图片插入位置可改：题干上方、题干下方、选项上方、选项下方。
- 图片可显式标记“合并下一张”，为相邻截图写入同一个 `same_visual_group_id`，用于连续表格展示和后续人工确认。
- 审核页可输入或选中文本加入页眉页脚黑名单。
- 保存/发布后刷新当前题和右侧移动端预览状态。
- 右侧移动端预览按图片插入位置展示，不再把所有题图固定塞在题干下方。
- 保留 PDF 定位入口；复杂框选继续进入 `QuestionPreviewView`。

### Phase 2：PDF 解析硬规则修复

状态：已完成第一版规则。

- 页眉页脚重复文本过滤。
- 题号优先于材料 prompt 识别。
- 未显式绑定视觉区域按下方最近题/共享材料组归属。
- 同页相邻表格/图片按 x 重叠、y 间距、题号间隔合并。
- Validator 增加 header/footer、边界冲突、缺选项、低置信图片、图片数量异常 warning。

### Phase 3：AI 当前题/当前页修复

状态：已完成单题候选修复接口和审核页入口。

- `POST /admin/questions/:id/ai-repair`
- `POST /repair-question`
- AI 复用 `ai_client.py` 现有 OpenAI-compatible 配置。
- 结果只返回 proposal，不直接持久化；审核页确认后写入编辑框，仍需人工保存。

### Phase 4：最终清理和验收

状态：已完成当前可用验证，仍需真实 PDF 回归抽样。

- 已跑后端构建、admin/h5 构建、pdf-service 全量 unittest。
- 未自动提交，因工作区存在多项本次任务外的既有改动和本地题本/上传目录，需要提交前手动精确 staging。

## 新增/修改接口

- `PATCH /admin/questions/:id`
- `POST /admin/questions/:id/images`
- `DELETE /admin/questions/:id/images/:imageKey`
- `PATCH /admin/questions/:id/images/reorder`
- `POST /admin/questions/:id/images/merge`
- `POST /admin/questions/:id/move-image`
- `POST /admin/questions/:id/ai-repair`
- `POST /admin/questions/:id/split`
- `POST /admin/questions/:id/merge`
- `POST /admin/pdf/crop-region`
- `POST /admin/pdf/header-footer-blacklist`
- `POST /repair-question`（pdf-service）

## 数据库变更

- `questions.visual_refs`：JSON，可空。
- `questions.review_status`：enum，默认 `pending`。
- 图片仍存于 `questions.images` / `materials.images` JSON 中，新增结构字段：
  - `image_role`
  - `image_order`
  - `insert_position`
  - `bbox`
  - `same_visual_group_id`
  - `assignment_confidence`
  - `ai_desc`

生产环境如果关闭 TypeORM synchronize，需要补迁移。

## 待办

- [ ] 用当前真实 `admin-demo-question-book.pdf` 或下册 9-12 页重新跑完整解析，核验例 1-4 图表归属。
- [x] 在审核页补“合并相邻图片”可视化操作；当前实现为相邻图片写入同一 `same_visual_group_id`。
- [x] 在审核页补“加入页眉页脚黑名单”的文本选择入口；支持输入或使用当前选中文本。
- [ ] 将单题 AI 修复扩展为带页面截图/bbox 的更强输入；当前先使用题目结构、来源、邻题和 warnings。
- [ ] 为 `review_status` 增加正式数据库迁移。
