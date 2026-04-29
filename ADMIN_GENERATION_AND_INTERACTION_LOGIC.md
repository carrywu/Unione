# Admin 生成逻辑与交互逻辑梳理

本文档基于当前代码生成，用于后续改造 `admin-web` 管理后台。重点覆盖题库 PDF 生成/解析、答案册解析匹配、题目审核编辑、PDF 框选修复、系统配置与 PDF 服务监控。

## 1. 系统边界

当前 Admin 不是单体页面，而是三层协作：

- `admin-web`：Vue 3 + Element Plus 管理端，负责上传、任务状态、题目审核、PDF 预览框选、答案册匹配、系统设置。
- `backend`：NestJS API，负责鉴权、任务入库、调用 PDF 服务、保存题目/材料/图片、答案源匹配、系统配置代理。
- `pdf-service`：FastAPI 服务，负责 PDF 下载、结构化解析、图片/OCR/AI 识别、答案册解析、运行状态统计。

核心入口：

- Admin 前端路由：`admin-web/src/router/index.ts`
- PDF 解析 API：`backend/src/modules/pdf/pdf.controller.ts`
- PDF 解析服务：`backend/src/modules/pdf/pdf.service.ts`
- 答案册 API：`backend/src/modules/answer-book/answer-book.controller.ts`
- 答案册服务：`backend/src/modules/answer-book/answer-book.service.ts`
- 题目审核 API：`backend/src/modules/question/question.controller.ts`
- PDF 服务入口：`pdf-service/main.py`
- PDF 主解析管线：`pdf-service/pipeline.py`

## 2. Admin 导航与页面结构

Admin 登录后进入 `DefaultLayout`，左侧菜单包含：

- 首页：`/dashboard`
- 题库管理：`/banks`
- 材料管理：`/materials`
- 解析任务：`/pdf/tasks`
- 用户管理：`/users`
- 系统设置：`/system`

题库相关核心页面：

- `/banks/:id/upload`：上传题库 PDF 并触发解析。
- `/banks/:id/review`：批量审核、编辑、发布题目。
- `/banks/:id/questions`：题目列表。
- `/banks/:id/questions/:questionId/preview`：题目预览、PDF 定位、框选 OCR、图片替换。
- `/banks/:id/answer-book`：上传答案解析册、自动匹配答案/解析。

路由守卫读取 `localStorage.admin_token`：

- 未登录访问 Admin 页面会跳转 `/login`。
- 已登录访问 `/login` 会跳转 `/dashboard`。

## 3. 题库 PDF 生成/解析逻辑

### 3.1 前端上传流程

页面：`admin-web/src/views/banks/BankUploadView.vue`

交互步骤：

1. 管理员选择 PDF 文件。
2. 点击“开始上传并解析”。
3. 前端调用 `uploadFile(file)` 上传文件，得到 `url`。
4. 前端调用 `parsePdf(bankId, uploaded.url)` 创建解析任务。
5. 前端保存 `taskId`，每 3 秒调用 `getTaskStatus(taskId)` 轮询。
6. 任务完成后调用 `getQuestions({ bankId, taskId })` 拉取本次解析出的题目。
7. 页面展示结果表格，并提供三个去向：
   - 查看解析题目
   - 进入审核编辑
   - 上传解析册匹配答案

关键状态：

- `pending`：已创建任务，等待处理。
- `processing`：解析中，展示进度条。
- `done`：解析完成，展示题目数和结果表。
- `failed`：解析失败，展示错误。
- `paused`：已暂停，可重试。

### 3.2 后端任务创建

接口：`POST /admin/pdf/parse`

后端逻辑：

1. `PdfService.parse(dto)` 创建 `ParseTask`。
2. 写入 `bank_id`、`file_url`、`file_name`、`status=pending`、`progress=0`。
3. 通过 `EventEmitter` 异步触发 `processTask(task.id)`。
4. 立即返回 `{ task_id }`，前端开始轮询。

### 3.3 后端调用 PDF 服务

`processTask` 做这些事：

1. 将任务更新为 `processing`，进度 `10`。
2. 清理当前任务旧结果：删除该 `parse_task_id` 下已有题目和材料。
3. 检查 `PDF_SERVICE_URL/health`。
4. 读取系统配置和环境变量，组装 `ai_config`：
   - `DASHSCOPE_API_KEY`
   - `DASHSCOPE_BASE_URL`
   - `AI_VISUAL_MODEL`
   - `AI_TEXT_API_KEY`
   - `AI_TEXT_BASE_URL`
   - `AI_TEXT_MODEL`
   - `DEEPSEEK_API_KEY`
   - `DEEPSEEK_BASE_URL`
   - `DEEPSEEK_MODEL`
5. 调用 `POST {PDF_SERVICE_URL}/parse-by-url`。
6. 传入：
   - `url`
   - `ai_config`
   - `callback_url`
   - `callback_token`
   - `callback_batch_size=20`

### 3.4 PDF 服务解析管线

入口：`pdf-service/main.py` 的 `/parse-by-url`

流程：

1. 下载 PDF 到临时文件。
2. 调用 `parse_pdf(path, url, ai_config)`。
3. 成功后记录统计：解析份数、题目数、耗时、AI 调用次数。
4. 如果传入 `callback_url`：
   - 先回调材料：`POST {callback_url}/materials`
   - 再按批次回调题目：`POST {callback_url}/questions`
   - 最后回调完成：`POST {callback_url}/finish`
5. 返回轻量 summary 给后端。

主解析管线：`pdf-service/pipeline.py`

当前优先级：

1. 先尝试 `MarkdownQuestionStrategy`。
2. 经过 `validate_and_clean` 校验清洗。
3. 如果解析出题目数量大于 0，直接返回。
4. 如果失败或无结果，进入旧策略：
   - `PDFDetector` 检测 PDF 类型。
   - 当前各类型都映射到 `UniversalQuestionStrategy`。
   - 如果题目数少于 3 且页数不超过 50，降级尝试 `VisualStrategy`。
5. 最终统一转换为 `ParseResult`，包含：
   - `questions`
   - `materials`
   - `stats`
   - `detection`
   - `strategy`

PDF 类型检测维度：

- 文本行数
- 图片页比例
- 目录行比例
- 选项数量
- 题号数量
- 章节关键词
- 材料关键词
- 考试结构关键词

检测类型：

- `pure_text`
- `visual_heavy`
- `textbook`
- `exam_paper`
- `unknown`
- `markdown_layout`

### 3.5 解析结果入库

后端支持两种入库方式：

1. 回调批量入库：PDF 服务分批推送材料和题目，适合大文件。
2. 同步返回入库：如果没有 callback delivery，则后端直接保存返回结果。

材料保存：

- 表：`Material`
- 字段包括：
  - `bank_id`
  - `parse_task_id`
  - `content`
  - `images`
  - `page_range`
  - `image_refs`
  - `raw_text`
  - `parse_warnings`

题目保存：

- 表：`Question`
- 字段包括：
  - `bank_id`
  - `parse_task_id`
  - `material_id`
  - `index_num`
  - `type`
  - `content`
  - `option_a/b/c/d`
  - `answer`
  - `analysis`
  - `images`
  - `page_num`
  - `page_range`
  - `source_page_start/end`
  - `source_bbox`
  - `source_anchor_text`
  - `source_confidence`
  - `raw_text`
  - `parse_confidence`
  - `parse_warnings`
  - `status=draft`
  - `needs_review`

图片保存：

- 如果解析结果里有 `base64`，后端通过 `UploadService.uploadBuffer` 上传。
- 题目图片路径前缀：`pdf-parse/{taskId}/question`
- 材料图片路径前缀：`pdf-parse/{taskId}/material`
- 入库后移除 `base64`，保留 `url` 和元信息。

## 4. 题目审核与发布逻辑

页面：`admin-web/src/views/banks/BankReviewView.vue`

### 4.1 左侧题目池

左侧提供：

- 审核统计：
  - 总题数
  - 待审核
  - 草稿
  - 已发布
- Tab：
  - 全部
  - 待审核
  - 已发布
- 批量发布：仅发布“不需要复查且未发布”的题目。
- 分页题目列表。

查询参数：

- `bankId`
- `status`
- `needsReview`
- `page`
- `pageSize`

### 4.2 右侧编辑器

选中题目后右侧展示：

- 解析质量信息：
  - `parse_confidence`
  - `parse_warnings`
  - `source`
  - `raw_text`
- 材料内容与材料图片。
- 题目图片。
- 题号、题型、题干、选项、答案、解析、状态。
- 操作：
  - 保存
  - 通过发布
  - 删除
  - 打开 PDF 定位页

脏数据保护：

- 表单修改后 `dirty=true`。
- 切换题目前，如果存在未保存修改，会弹确认。
- 保存/发布成功后 `dirty=false`。

### 4.3 后端审核接口

题目列表：

- `GET /admin/questions`
- 支持 `bankId`、`taskId`、`status`、`needsReview`、`has_images`、`keyword`、排序、分页。

题目详情：

- `GET /admin/questions/:id`
- 额外返回：
  - `material`
  - `pdf_source`
  - `answer_count`
  - `correct_rate`

题目更新：

- `PUT /admin/questions/:id`
- 保存题干、选项、答案、解析、图片、状态、复查标记等。
- 如果状态变化，会刷新题库已发布数量。

批量发布：

- `POST /admin/questions/batch-publish`
- 将题目状态改为 `published`，并清掉 `needs_review`。

删除：

- `DELETE /admin/questions/:id`
- 软删除题目，并刷新题库数量。

## 5. 题目预览、PDF 定位与框选修复

页面：`admin-web/src/views/banks/QuestionPreviewView.vue`

这是当前 Admin 里最关键的精修页面，目标是把“PDF 原文、结构化题目、图片区域、AI/OCR 修复”放在同一工作台。

### 5.1 页面布局

顶部工具栏：

- 返回列表
- 进入审核
- 保存修改
- 保存并通过
- AI 预审
- 撤销最近修复

左侧题目编辑：

- 材料与材料图片
- 题目图片
- 题型
- 题号
- 题干
- 选项
- 答案
- 解析
- 状态
- AI 预审结果
- 解析信息

右侧 PDF 面板：

- 原 PDF 预览
- 当前页定位
- 高亮 `source_bbox`
- 框选识别开关
- 点击打开原 PDF

PDF 地址来源：

- 优先使用后端代理：`/admin/pdf/proxy/:taskId`
- 没有任务时使用题目 `pdf_source.file_url`

### 5.2 框选识别流程

用户点击“框选识别”后：

1. `PdfLocator` 开启区域选择。
2. 用户在 PDF 页面拖拽选区。
3. 前端收到 `region-selected`，保存：
   - `page`
   - `bbox`
4. 弹出“区域处理”对话框。
5. 管理员选择用途：
   - 识别为题干
   - 识别为选项
   - 识别为材料
   - 识别为解析
   - 保存为题目图片
   - 保存为材料图片
   - 替换选中的题目/材料图片

前端调用：

- `POST /admin/pdf/ocr-region`

参数：

- `task_id`
- `file_url`
- `question_id`
- `page_num`
- `bbox`
- `mode`

### 5.3 后端 OCR 代理

`PdfService.ocrRegion(dto)`：

1. 校验 `task_id` 或 `file_url` 至少一个。
2. 如果传入 `question_id`，校验题目存在且属于同一题库。
3. 调用 PDF 服务 `/ocr-region`。
4. 如果 PDF 服务返回 `image_base64`：
   - 上传成图片文件。
   - 返回 `image_url`。
5. 统一返回：
   - `text`
   - `options`
   - `image_url`
   - `page_num`
   - `bbox`
   - `confidence`
   - `source`
   - `warnings`

### 5.4 PDF 服务区域处理

入口：`pdf-service/main.py` 的 `/ocr-region`

支持模式：

- `stem`
- `options`
- `material`
- `analysis`
- `image`

处理逻辑：

- 如果传入 URL，先下载 PDF。
- 根据页码和 `bbox` 裁剪区域。
- `image` 模式返回裁剪图。
- 文本类模式调用 AI/OCR 识别并按模式结构化。

### 5.5 修复写回逻辑

识别结果会先进入确认弹窗，不直接覆盖：

- 选项模式：管理员可以编辑 A/B/C/D，再替换。
- 题干/解析模式：可选择替换或追加。
- 材料模式：可替换或追加材料文本。
- 图片模式：可保存为题目图片、材料图片，或替换当前选中的图片。

页面维护 `lastUndo`：

- 每次自动写回前记录旧值。
- 点击“撤销最近修复”可回滚最近一次字段/图片修复。

## 6. AI 可读性预审逻辑

入口：

- 前端：`QuestionPreviewView.vue` 的“AI预审”
- 后端：`POST /admin/questions/:id/readability-review`
- PDF 服务：`POST /review-question-readability`

后端构造题目 payload：

- 题号
- 题型
- 题干
- 选项
- 答案
- 解析
- 材料
- 图片
- 解析警告

PDF 服务根据提示词判断：

- 是否可读
- 是否需要复查
- 可读性分数
- 原因
- 管理员动作提示
- 重点区域：
  - `stem`
  - `options`
  - `material`
  - `images`
  - `analysis`
  - `warnings`

如果 PDF 服务失败，后端有启发式兜底：

- 题干太短或缺失：提示重新框选题干。
- 单选题选项缺失：提示重新框选选项。
- 存在解析警告：提示复查。

当 AI 判断 `needs_review=true`，后端会给题目追加 `ai_readability_needs_review` 警告。

## 7. 答案解析册生成与匹配逻辑

页面：`admin-web/src/views/banks/AnswerBookMatchView.vue`

### 7.1 前端交互

管理员在题库下上传答案解析册：

1. 选择解析模式：
   - 自动
   - 文字优先
   - 图片切块
2. 上传 PDF。
3. 调用 `createAnswerBookTask(bankId, { file_url, file_name, mode })`。
4. 轮询 `getTaskStatus(taskId)`。
5. 任务完成后加载答案源列表。
6. 页面展示：
   - 题库题目数
   - 答案源数量
   - 已匹配数量
   - 待处理数量
   - 答案源表格
7. 可执行：
   - 重新匹配
   - 查看匹配题目
   - 解除绑定

### 7.2 后端答案册任务

接口：

- `POST /admin/banks/:bankId/answer-books`
- `POST /admin/answer-books/:taskId/match`
- `GET /admin/answer-sources`
- `POST /admin/answer-sources/:id/bind`
- `POST /admin/answer-sources/:id/unbind`

创建任务：

1. 校验题库存在。
2. 创建 `ParseTask`：
   - `task_type=answer_book`
   - `answer_book_mode=auto/text/image`
   - `status=pending`
3. 异步触发 `processAnswerBookTask`。

调用 PDF 服务：

- `POST /parse-answer-book-by-url`
- 传入 `url`、`mode`、`ai_config`

### 7.3 PDF 服务答案册解析

入口：`pdf-service/answer_book_parser.py`

逻辑：

1. 如果模式为 `auto`，先检测解析册形态。
2. 检测规则：
   - 答案/解析/参考答案关键词多且文本量大：`text`
   - 图片页比例高或文本量低：`image`
   - 其他情况默认 `image`
3. `text` 模式使用 `TextAnswerStrategy`。
4. `image` 模式使用 `ImageAnswerStrategy`。
5. 返回候选答案源：
   - 题号
   - 答案
   - 解析文本
   - 解析图片
   - 来源页码
   - bbox
   - anchor
   - confidence

### 7.4 答案源保存与自动匹配

后端保存 `AnswerSource`：

- `bank_id`
- `parse_task_id`
- `source_pdf_url`
- `source_page_num`
- `source_bbox`
- `section_key`
- `question_index`
- `question_anchor`
- `answer`
- `analysis_text`
- `analysis_image_url`
- `raw_text`
- `confidence`
- `parse_mode`
- `status=unmatched`

匹配逻辑：

1. 按题号把题库题目分组。
2. 对每个答案源找相同 `question_index` 的候选题。
3. 计算分数：
   - 题号一致：+45
   - section 命中题目文本：+10
   - anchor 完全匹配：+20
   - 文本证据重合：最高 +35
   - 答案源置信度 >= 85：+5
   - 题号唯一：+10
4. 如果候选唯一且分数 >= 85：自动写入题目。
5. 如果分数 >= 70 但不唯一：标记 `ambiguous`。
6. 如果无可靠候选：标记 `unmatched`。
7. 顺序兜底图片块默认更保守，可能标记 `ambiguous` 或 `ignored`。

自动写入题目字段：

- `answer`
- `analysis`
- `analysis_image_url`
- `answer_source_id`
- `analysis_match_confidence`

## 8. 系统设置与 PDF 服务监控

页面：`admin-web/src/views/system/SystemView.vue`

### 8.1 基础配置

前端调用：

- `GET /admin/system/configs`
- `PUT /admin/system/configs/:key`
- `GET /admin/system/info`

配置表展示：

- key
- 说明
- 类型
- 值
- 保存按钮

敏感 key 规则：

- key 包含 `API_KEY` 或 `SECRET` 时使用 password 输入。

### 8.2 PDF 解析服务页

当前系统设置里的 PDF 服务页承担四块能力：

1. 服务状态卡片：
   - PDF 服务是否可达
   - 响应耗时
   - 队列处理中/等待中
   - 内存占用
   - 今日解析份数/题数
2. 解析队列实时终端：
   - 每 30 秒刷新一次
   - 展示队列、内存、session 统计、AI 调用、最近错误
3. AI 供应商配置：
   - 视觉 AI 供应商
   - 文字 AI 供应商
   - 通义千问 API Key
   - DeepSeek API Key
4. 提示词管理与测试解析：
   - 整页截图识别提示词
   - 文字结构化提示词
   - 图表描述提示词
   - 输入 PDF URL 和测试页码后运行测试解析

### 8.3 后端代理逻辑

Admin 前端不直接请求 Python PDF 服务，而是请求 Nest 后端：

- `GET /admin/pdf-service/status`
- `GET /admin/pdf-service/stats`
- `GET /admin/pdf-service/config`
- `PUT /admin/pdf-service/config`
- `POST /admin/pdf-service/cache-invalidate`
- `POST /admin/pdf-service/test-parse`

后端再代理到 PDF 服务：

- `/status`
- `/stats`
- `/admin/config`
- `/admin/cache/invalidate`
- `/admin/test-parse`

内部接口会带 `Authorization: Bearer {PDF_SERVICE_INTERNAL_TOKEN}`。

### 8.4 配置写入关系

保存 PDF 服务配置时，前端当前会同时做两件事：

1. 调用 `PUT /admin/pdf-service/config`，让 PDF 服务热更新运行配置。
2. 调用 `PUT /admin/system/configs/:key`，把关键配置持久化到数据库。

保存提示词时：

1. 更新 `SystemConfig` 中 `prompt.*`。
2. 调用 PDF 服务清缓存。
3. 下次解析立即使用新提示词。

## 9. 当前 Admin 交互的主要问题

下面是后续改造 Admin 时应优先处理的点。

### 9.1 生成链路信息分散

同一条“PDF 入库”链路分散在：

- 上传页
- 审核页
- 预览页
- 答案册页
- 系统设置页
- 任务历史页

建议改为统一的“解析工作台”心智：

- 上传/解析进度
- 解析质量
- 待修复题目
- 答案册匹配
- 发布进度
- 服务健康

### 9.2 任务状态可解释性不足

目前进度只有百分比和错误文案，管理员不知道卡在哪一步。

建议任务状态增加阶段：

- 上传完成
- PDF 下载
- 类型检测
- 页面解析
- 图片抽取
- AI 结构化
- 校验清洗
- 入库
- 答案册匹配
- 完成/失败

### 9.3 审核页与预览页职责重叠

`BankReviewView` 和 `QuestionPreviewView` 都能编辑题目，但能力不同：

- 审核页适合批量快速编辑。
- 预览页适合带 PDF 原文的精修。

建议：

- 审核页定位为“列表批处理 + 快速修字段”。
- 预览页定位为“单题精修 + PDF 证据 + OCR 修复”。
- 两者共享同一套保存状态、脏数据提示、发布校验规则。

### 9.4 框选替换能力需要更显性

当前图片替换已具备基础能力，但入口藏在图片 hover/操作里，管理员不一定知道可以框选替换。

建议改造：

- 图片卡片上固定展示“替换图片”“删除”“定位来源”。
- 进入替换模式后，右侧 PDF 明确显示“请选择新图片区域”。
- 选区完成后展示裁剪预览，再确认替换。
- 替换后保留一键撤销。

### 9.5 AI 配置与提示词管理混杂

系统设置页现在同时处理系统配置、服务监控、提示词、测试解析，信息密度偏高。

建议拆成：

- 系统配置
- PDF 服务监控
- AI 模型配置
- 提示词实验室
- 测试解析沙盒

## 10. 建议的 Admin 改造目标

后续代码改造可以按以下顺序推进：

1. 先重构 Admin 的“题库解析工作台”页面，把上传、任务、结果、去审核、去答案册合并成清晰流程。
2. 强化 `QuestionPreviewView`：
   - PDF 框选替换图片更直观。
   - OCR 结果确认更清晰。
   - 保存/发布/撤销状态更稳定。
3. 优化 `BankReviewView`：
   - 更强的筛选和批处理。
   - 列表中显示解析风险原因。
   - 快速跳到 PDF 精修。
4. 调整系统页：
   - 状态监控和配置分区。
   - 解析测试结果可保存为样例。
   - 提示词修改有版本/恢复机制。
5. 增加浏览器级回归脚本：
   - 登录 Admin。
   - 打开题库上传页。
   - 打开审核页。
   - 打开题目预览页。
   - 模拟框选入口。
   - 打开答案册页。
   - 打开系统页并检查 PDF 服务状态。

## 11. 推荐的关键验收路径

改造 Admin 后，至少用真实浏览器验收这些路径：

1. 登录 Admin 后进入 `/banks`，页面不白屏。
2. 进入某题库 `/upload`，可以选择 PDF、创建任务、看到轮询状态。
3. 任务完成后可以跳转到 `/review` 和 `/answer-book`。
4. `/review` 里可以选择题目、编辑、保存、发布、删除。
5. `/questions/:questionId/preview` 能加载题目、PDF、source bbox 高亮。
6. 预览页开启框选后，能弹出区域处理动作。
7. 框选题干/选项/材料/解析后，能确认替换或追加。
8. 框选图片后，能保存为题目图片/材料图片，也能替换已有图片。
9. 答案册页能上传、轮询、展示答案源、重新匹配、跳转题目。
10. 系统页能显示 PDF 服务状态，保存配置，运行测试解析。

