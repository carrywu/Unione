# 后端逻辑说明

更新时间：2026-04-27

## 后端定位

`backend/` 是个人刷题系统的业务后端，负责：

- 用户注册、登录、刷新 token、修改密码。
- 管理端用户管理。
- 题库 CRUD 和发布。
- 题目 CRUD、发布、批量删除、审核统计。
- 材料 CRUD。
- 用户答题记录、错题本、统计。
- PDF 解析任务创建、暂停、重试、删除、回调接收。
- 系统配置和 PDF 服务监控。
- 文件上传。

技术栈：

- NestJS 10
- TypeORM 0.3
- PostgreSQL 当前运行配置
- JWT
- Swagger
- axios

入口：

- `src/main.ts`
- `src/app.module.ts`

## 全局行为

`src/main.ts`：

- JSON body limit：`50mb`
- URL encoded limit：`50mb`
- CORS：允许 credentials
- 全局 `ValidationPipe`
  - `whitelist: true`
  - `transform: true`
- 全局响应包装：`TransformInterceptor`
- 全局错误包装：`HttpExceptionFilter`
- Swagger：`/api-docs`

接口响应规范：

```json
{
  "code": 0,
  "data": {},
  "message": "ok"
}
```

失败：

```json
{
  "code": 400,
  "data": null,
  "message": "错误说明"
}
```

## 数据库连接

`src/app.module.ts` 使用 `TypeOrmModule.forRootAsync`。

当前环境：

```env
DB_TYPE=postgres
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASS=password
DB_NAME=quiz_app
```

注意：

- 当前 `synchronize: true`，开发方便，但生产不安全。
- 后续建议改 TypeORM migrations。

## 模块总览

```txt
src/modules/
  auth/          登录注册
  user/          用户资料和管理端用户管理
  bank/          题库
  question/      题目
  material/      材料
  record/        答题记录、错题
  pdf/           PDF 解析任务与回调
  system/        系统配置、PDF 服务监控
  upload/        文件上传
  admin-stats/   管理端统计
```

## Auth 模块

路径：

- `src/modules/auth/auth.controller.ts`
- `src/modules/auth/auth.service.ts`

主要接口：

- `POST /api/auth/register`
- `POST /api/auth/login`
- `PUT /api/auth/password`
- `POST /api/auth/refresh`
- `POST /api/auth/logout`

逻辑：

1. 注册时检查手机号是否已存在。
2. 密码用 bcrypt hash。
3. 登录时校验手机号和密码。
4. 返回 access token / refresh token。
5. JWT payload 含 `sub`、`phone`、`role`。

默认账号来自 `src/seed.ts`：

- 管理员：`13800138000` / `123456`
- 普通用户：`13900139000` / `123456`

## User 模块

路径：

- `src/modules/user/user.controller.ts`
- `src/modules/user/user.service.ts`
- `src/modules/user/entities/user.entity.ts`
- `src/modules/user/entities/user-question-book.entity.ts`

用户端：

- 查看/修改个人资料。
- 修改头像。
- 删除账号。
- 获取/设置选中的题库。

管理端：

- 用户列表。
- 用户详情。
- 用户答题记录。
- 用户统计。
- 修改用户。
- 删除用户。
- 启用/禁用用户。
- 重置密码。

## Bank 模块

路径：

- `src/modules/bank/bank.controller.ts`
- `src/modules/bank/bank.service.ts`
- `src/modules/bank/entities/question-bank.entity.ts`

实体 `QuestionBank`：

- `id`
- `name`
- `subject`
- `source`
- `year`
- `status`: `draft | published`
- `total_count`
- `created_at`
- `deleted_at`

用户端：

- `GET /api/banks`
- `GET /api/banks/:id`

管理端：

- `GET /admin/banks`
- `POST /admin/banks`
- `PUT /admin/banks/:id`
- `DELETE /admin/banks/:id`
- `PUT /admin/banks/:id/publish`

逻辑：

- 用户端只返回已发布题库。
- 管理端可看全部题库。
- 发布题库时会统计该题库已发布题目数量并写入 `total_count`。

## Question 模块

路径：

- `src/modules/question/question.controller.ts`
- `src/modules/question/question.service.ts`
- `src/modules/question/entities/question.entity.ts`
- `src/modules/question/entities/material.entity.ts`

实体 `Question` 核心字段：

- `bank_id`
- `material_id`
- `parse_task_id`
- `index_num`
- `type`: `single | judge`
- `content`
- `option_a/b/c/d`
- `answer`
- `analysis`
- `images`
- `ai_image_desc`
- `page_num`
- `source`
- `raw_text`
- `parse_confidence`
- `status`: `draft | published`
- `needs_review`
- `answer_count`
- `correct_rate`

用户端：

- `GET /api/questions`
- `GET /api/questions/:id/answer`

管理端：

- `GET /admin/questions`
- `POST /admin/questions`
- `POST /admin/questions/batch-publish`
- `POST /admin/questions/batch-delete`
- `GET /admin/questions/review-stats/:bankId`
- `GET /admin/questions/:id`
- `PUT /admin/questions/:id`
- `DELETE /admin/questions/:id`

关键逻辑：

- 用户端题目列表会隐藏 `answer` 和 `analysis`。
- 用户获取答案时返回题目答案、解析和最近一次答题记录。
- 管理端详情会附带答题数和正确率。
- 新建题目会校验题库存在。
- 如果传 `material_id`，会校验材料属于该题库。
- 单选题至少需要 A、B 两个选项。
- 发布、批量发布、删除会刷新题库 `total_count`。
- 查询支持：
  - `bankId`
  - `taskId`
  - `status`
  - `needsReview`
  - `has_images`
  - `keyword`
  - `sort_by`
  - `sort_order`

当前排序字段白名单：

- `index_num`
- `created_at`
- `answer_count`
- `page_num`
- `parse_confidence`
- `needs_review`

注意：

- 当前 `update()` 直接 `Object.assign(question, dto)`，如果未来允许改 `bank_id/material_id`，需要补充材料归属校验。
- `has_images` 使用 `JSON_LENGTH`，适配 MySQL；当前运行 PostgreSQL 时需要确认 TypeORM/数据库是否兼容该 SQL。若继续使用 PostgreSQL，应改为 PostgreSQL JSON 查询。

## Material 模块

路径：

- `src/modules/material/material.controller.ts`
- `src/modules/material/material.service.ts`
- `src/modules/question/entities/material.entity.ts`

接口：

- `GET /admin/materials`
- `GET /admin/materials/:id`
- `PUT /admin/materials/:id`
- `DELETE /admin/materials/:id`

逻辑：

- 材料列表按题库过滤。
- 列表会返回材料截断内容和 `question_count`。
- 当前 `question_count` 使用一次 `GROUP BY` 聚合查询。
- 删除材料时，会先把关联题目的 `material_id` 置空，再 soft delete 材料。

## Record 模块

路径：

- `src/modules/record/record.controller.ts`
- `src/modules/record/record.service.ts`
- `src/modules/record/entities/user-record.entity.ts`

职责：

- 单题提交。
- 批量提交。
- 答题历史。
- 错题列表。
- 用户统计。
- 错题掌握/取消掌握。
- 清空错题。
- 错题练习。

核心实体 `UserRecord`：

- `user_id`
- `question_id`
- `user_answer`
- `is_correct`
- `time_spent`
- `created_at`

## PDF 模块

路径：

- `src/modules/pdf/pdf.controller.ts`
- `src/modules/pdf/pdf-internal.controller.ts`
- `src/modules/pdf/pdf.service.ts`
- `src/modules/pdf/entities/parse-task.entity.ts`

管理端接口：

- `POST /admin/pdf/parse`
- `GET /admin/pdf/task/:taskId`
- `GET /admin/pdf/tasks`
- `POST /admin/pdf/retry/:taskId`
- `POST /admin/pdf/pause/:taskId`
- `DELETE /admin/pdf/task/:taskId`

内部回调接口：

- `POST /internal/pdf/tasks/:taskId/materials`
- `POST /internal/pdf/tasks/:taskId/questions`
- `POST /internal/pdf/tasks/:taskId/finish`

解析任务实体 `ParseTask`：

- `bank_id`
- `file_url`
- `file_name`
- `status`: `pending | processing | done | failed | paused`
- `progress`
- `total_count`
- `done_count`
- `attempt`
- `result_summary`
- `error`
- `created_at`

### 创建解析任务

`PdfService.parse(dto)`：

1. 创建 `ParseTask`，状态为 `pending`。
2. 用 `setImmediate()` 异步触发 `processTask(task.id)`。
3. 返回 `task_id`。

### 处理解析任务

`processTask(taskId)`：

1. 读取任务。
2. 标记为 `processing`，进度 10。
3. 删除该任务之前的题目和材料结果。
4. 调用 PDF 服务 `/health`。
5. 读取 AI 配置：
   - 优先从 `system_configs` 表读。
   - 其次从后端 `.env` 读。
6. 调用 PDF 服务 `/parse-by-url`：

```json
{
  "url": "PDF 文件地址",
  "ai_config": {},
  "callback_url": "http://localhost:3010/internal/pdf/tasks/:taskId",
  "callback_token": "...",
  "callback_batch_size": 20
}
```

7. 如果 PDF 服务没有 callback，则直接保存返回的 materials/questions。
8. 如果 PDF 服务 callback 成功，则等待回调接口分批保存。
9. 异常时标记任务 `failed`。
10. 暂停时 abort 当前请求并标记 `paused`。

### 回调保存材料

`appendCallbackMaterials(taskId, materials)`：

1. 找任务。
2. 如果任务已暂停，忽略。
3. 保存材料。
4. 在内存 `callbackMaterialMaps` 保存临时 material id 到真实 Material 的映射。

风险：

- 这是内存 Map，服务重启会丢。
- 如果 callback questions 先于 materials 到达，材料绑定会失败。

### 回调保存题目

`appendCallbackQuestions(taskId, questions, total)`：

1. 找任务。
2. 如果任务已暂停，忽略。
3. 根据 `callbackMaterialMaps` 映射 `material_id`。
4. 保存题目。
5. 更新 `done_count / total_count / progress`。

当前保存题目支持字段：

- `index` / `index_num`
- `type`
- `content`
- `options.A/B/C/D`
- `option_a/b/c/d`
- `answer`
- `analysis`
- `images`
- `page_num` / `page` / `pageNumber`
- `source` / `parse_source`
- `raw_text` / `rawText`
- `parse_confidence` / `confidence`
- `needs_review`

### 完成回调

`finishCallbackTask(taskId, body)`：

1. 标记任务 `done`。
2. 设置 `progress=100`。
3. 保存 `stats/detection/delivery` 到 `result_summary`。
4. 清理内存 material map。
5. 刷新题库 `total_count`。

### PDF 模块优化点

优先级高：

- callback 幂等：同一批重复回调会重复插题。
- 内存 `callbackMaterialMaps` 不可靠，应改成 DB 暂存或让 question payload 带足 material 内容/稳定 id。
- `remove(taskId)` 当前只删除任务记录，不一定删除该任务导入的题目和材料，需要确认产品期望。
- 内部 token 如果为空会放行，生产应强制配置。
- 解析任务状态在 callback 模式下依赖 PDF 服务最终 finish；如果 finish 丢失，任务可能卡在 processing。

## System 模块

路径：

- `src/modules/system/system.controller.ts`
- `src/modules/system/system.service.ts`
- `src/modules/system/pdf-service-monitor.controller.ts`
- `src/modules/system/entities/system-config.entity.ts`

职责：

- 系统配置读取/更新。
- AI key 配置。
- PDF 服务状态代理。
- PDF 服务测试解析。
- PDF 服务缓存清理。

重要逻辑：

- 后端 `getAiConfig()` 会优先读 `system_configs`。
- 管理端可以通过接口更新 Qwen/DeepSeek key。
- PDF 服务也支持 `/admin/config` 读取脱敏配置。

## Upload 模块

路径：

- `src/modules/upload/upload.controller.ts`
- `src/modules/upload/upload.service.ts`

职责：

- 管理端上传文件。
- 支持 OSS / 七牛等配置。
- PDF 解析通常依赖上传后得到的 URL。

## Admin Stats 模块

路径：

- `src/modules/admin-stats/admin-stats.controller.ts`
- `src/modules/admin-stats/admin-stats.service.ts`

职责：

- 管理端 overview。
- 趋势统计。
- 热门题目。
- 活跃用户。
- 题库统计。

## 后端当前风险清单

1. `synchronize: true` 不适合生产。
2. `QuestionService.update()` 缺少跨题库更新时的材料归属校验。
3. PDF callback 无幂等保护。
4. PDF callback material 映射存在内存丢失风险。
5. `has_images` 查询写法需要按实际数据库方言调整。
6. 删除解析任务是否删除导入题目，语义未定。
7. 内部回调 token 生产环境应该强制存在。
8. AI key 同时存在 `.env` 和 DB 配置，优先级要在文档和 UI 中说明清楚。
9. 缺少自动化测试，当前主要靠 `npm run build` 和人工接口验证。

## 推荐后端优化顺序

1. 修正 PostgreSQL 下 JSON 查询兼容性。
2. 为 PDF callback 增加幂等字段和去重逻辑。
3. 将 callback material 映射持久化。
4. 扩展 `Question` metadata：`page_range / image_refs / parse_warnings`。
5. 拆分 `PdfService`：任务管理、PDF 服务客户端、callback 保存、AI 配置读取。
6. 增加 migrations，关闭生产 `synchronize`。
7. 补一组最小 e2e 或 service-level 测试，至少覆盖 PDF callback 保存。

