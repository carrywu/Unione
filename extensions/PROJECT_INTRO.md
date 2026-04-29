# 项目简介

这是一个面向公考刷题场景的个人学习系统，包含 **H5 用户端、管理后台、NestJS 后端、Python PDF 解析服务** 四部分。

项目目标是支持题库管理、PDF 题本解析、题目审核、用户刷题、错题复习和学习数据统计，整体对标粉笔/腰果等公考刷题产品的精简版。

## 核心模块

### 1. H5 用户端

路径：

```txt
h5-web/
```

主要功能：

- 用户登录
- 题库列表
- 题库详情
- 在线刷题
- 答题结果页
- 错题本
- 错题重做
- 学习统计
- 个人中心

### 2. 管理后台

路径：

```txt
admin-web/
```

主要功能：

- 管理员登录
- 首页数据看板
- 题库管理
- 题目管理
- PDF 上传解析
- PDF 解析任务列表
- 解析任务状态终端
- PDF 服务监控面板
- AI Key 配置
- 提示词管理
- 用户管理
- 系统配置

### 3. 后端服务

路径：

```txt
backend/
```

技术栈：

- Node.js
- NestJS
- TypeORM
- PostgreSQL / MySQL
- JWT
- 七牛云 / OSS 上传
- Redis 可选

主要能力：

- 用户注册登录
- 管理员权限控制
- 题库 CRUD
- 题目 CRUD
- 错题记录
- 答题记录
- 用户统计
- PDF 解析任务调度
- PDF 服务回调入库
- 系统配置管理
- 上传服务

### 4. PDF 解析服务

路径：

```txt
pdf-service/
```

技术栈：

- Python
- FastAPI
- PyMuPDF
- pdfplumber
- Pillow
- httpx
- OpenAI SDK 兼容调用
- 阿里云百炼 / 通义千问 VL
- DeepSeek / qwen-plus

主要能力：

- PDF 下载
- PDF 文本提取
- PDF 页面截图
- 图片/表格区域提取
- PDF 类型检测
- 文本解析策略
- 视觉 AI 解析策略
- 题目结构化
- 答案/解析提取
- 材料题处理
- 图片描述生成
- 解析结果回调后端
- 服务状态与统计监控

## PDF 解析流程

当前 PDF 解析链路大致是：

```txt
上传 PDF
  ↓
后端创建解析任务
  ↓
PDF Service 下载 PDF
  ↓
PDF 类型检测
  ↓
选择解析策略
  ├─ 文本型 PDF：文本提取 + AI/规则结构化
  └─ 图文型 PDF：页面截图 + 通义千问 VL 视觉解析
  ↓
清洗与校验题目
  ↓
按批回调后端
  ↓
后端保存材料和题目
  ↓
管理端展示解析任务和审核结果
```

## 当前特色功能

- PDF 解析任务支持：
  - 任务列表
  - 解析进度
  - 暂停
  - 重试
  - 删除
  - 查看结果
  - 实时状态终端

- PDF 服务监控支持：
  - 服务在线状态
  - 队列状态
  - 内存占用
  - 今日解析统计
  - AI 调用状态
  - 通义千问/DeepSeek 最近错误
  - 实时队列终端

- AI 配置支持：
  - 后台配置通义千问 API Key
  - 后台配置 DeepSeek API Key
  - PDF 服务热更新配置
  - 提示词管理与清缓存

## 当前目录结构摘要

```txt
project2/
├── admin-web/        # 管理后台 Vue 应用
├── h5-web/           # H5 用户端 Vue 应用
├── backend/          # NestJS 后端服务
├── pdf-service/      # Python PDF 解析微服务
├── extensions/       # 扩展/待处理文件
├── IMPLEMENTED_FEATURES.md
├── NEXT_SESSION.md
├── PDF_PARSE_ERROR_NOTES.md
├── kuakuashua_pdf_parse_data.json
├── kuakuashua_pdf_parse_data.md
└── pdf_parse_export_7edc0cc5.*
```

## 项目定位

这是一个 **AI 辅助题库生产 + 公考刷题练习系统**。

它既能作为个人刷题 App 使用，也能作为题库生产工具，通过 PDF 解析服务把纸质/电子题本转成结构化题库，再经过后台审核后发布给 H5 用户端刷题。
