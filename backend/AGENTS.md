# 项目背景
个人刷题 Web App 后端，对标粉笔行测功能（精简版）。
无会员体系、无支付、无直播、无评论。
个人开发者，代码简洁优先，不需要写单元测试。

# 技术栈
- Node.js 20 + NestJS 10 + TypeORM 0.3
- MySQL 8 + Redis（ioredis）
- JWT 鉴权（@nestjs/jwt）
- 阿里云 OSS（ali-oss）
- axios 调用 Python PDF 微服务（内部端口 8001）

# 目录结构
src/
  modules/
    auth/         注册、登录、刷新 token
    user/         用户信息
    bank/         题库 CRUD（管理端+用户端）
    question/     题目 CRUD、批量导入
    record/       答题记录、错题本
    pdf/          调用 PDF 微服务、解析进度
    upload/       OSS 文件上传
  common/
    guards/       JwtAuthGuard、RolesGuard
    decorators/   @Roles() @CurrentUser()
    interceptors/ TransformInterceptor（统一响应）
    filters/      HttpExceptionFilter（统一错误）
    dto/          PaginationDto

# 接口规范
- 成功：{ code: 0, data: any, message: 'ok' }
- 失败：{ code: 非0, data: null, message: '错误说明' }
- 分页：入参 page/pageSize，出参 { list, total, page, pageSize }
- 用户接口前缀：/api
- 管理端接口前缀：/admin（需要 role=admin）

# 数据库 Entity（TypeORM）
User: id(uuid), phone(unique), password(bcrypt), nickname, avatar, role(user/admin), created_at, updated_at
QuestionBank: id(uuid), name, subject(行测/申论等), source(超格/四海等), year(int), status(draft/published), total_count, created_at
Material: id(uuid), bank_id(fk), content(text), images(json)
Question: id(uuid), bank_id(fk), material_id(fk nullable), index_num(int), type(single/judge),
          content(text), option_a, option_b, option_c, option_d,
          answer(varchar10), analysis(text), images(json),
          ai_image_desc(text), status(draft/published), needs_review(bool), created_at
UserRecord: id(uuid), user_id(fk), question_id(fk), user_answer, is_correct(bool), time_spent(int秒), created_at

# 不实现的功能
会员/订单/支付/评论/社区/直播课程/单元测试
