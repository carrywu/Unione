# Unione

Unione 是一个面向公考学习场景的刷题与题库管理平台，包含移动端练题、管理后台、后端 API 以及 PDF 试卷解析服务。项目支持题库、题目、材料、答题记录、错题本、用户管理和 PDF 自动解析等核心能力。

## 项目组成

| 目录 | 说明 |
| --- | --- |
| `h5-web/` | 学员端 H5 应用，基于 Vue 3、Vite、Pinia、Vant。 |
| `admin-web/` | 管理后台，基于 Vue 3、Vite、Pinia、Element Plus。 |
| `backend/` | 后端 API 服务，基于 NestJS、TypeORM，提供认证、题库、题目、记录、上传、PDF 任务等接口。 |
| `pdf-service/` | PDF 解析服务，基于 FastAPI，负责试卷/答案册解析、OCR 区域识别、视觉模型调用等能力。 |
| `scripts/` | 项目辅助脚本，包含前端路由冒烟、静态检查、后端冒烟等。 |
| `docs/` | 项目文档与补充说明。 |

## 核心功能

- 学员端：登录注册、题库选择、顺序练习、答题记录同步、错题与笔记辅助。
- 管理端：用户管理、题库管理、题目管理、材料管理、PDF 解析任务和系统配置。
- 后端服务：JWT 认证、角色权限、分页查询、记录提交、文件上传、PDF 服务联动。
- PDF 解析：文本型/扫描型试卷解析、答案册解析、题目分组、版面识别、视觉 API 冒烟工具。

## 技术栈

- 前端：Vue 3、TypeScript、Vite、Pinia、Vue Router、Vant、Element Plus。
- 后端：NestJS、TypeScript、TypeORM、MySQL/PostgreSQL、Redis、Swagger。
- PDF 服务：FastAPI、PyMuPDF、pdfplumber、Pillow、DashScope/OpenAI 兼容视觉/文本模型。
- 包管理：pnpm、pip。

## 环境要求

- Node.js 20+
- pnpm
- Python 3.10+
- MySQL 或 PostgreSQL
- Redis（可通过环境变量关闭）

## 快速开始

### 1. 安装依赖

```bash
pnpm install

cd backend && pnpm install
cd ../admin-web && pnpm install
cd ../h5-web && pnpm install

cd ../pdf-service
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置环境变量

后端和前端均提供了示例配置：

```bash
cp backend/.env.example backend/.env
cp admin-web/.env.example admin-web/.env.local
cp h5-web/.env.example h5-web/.env.local
```

常用后端变量：

```env
PORT=3000
DB_TYPE=mysql
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASS=
DB_NAME=quiz_app
JWT_SECRET=your_secret_here
REDIS_ENABLED=true
PDF_SERVICE_URL=http://localhost:8001
PDF_SERVICE_INTERNAL_TOKEN=local_pdf_internal_token
```

PDF 服务可按需配置：

```env
PDF_SERVICE_INTERNAL_TOKEN=local_pdf_internal_token
QWEN_API_KEY=your_qwen_api_key
DEEPSEEK_API_KEY=your_deepseek_api_key
```

### 3. 启动服务

后端 API：

```bash
cd backend
pnpm start:dev
```

PDF 解析服务：

```bash
cd pdf-service
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

管理后台：

```bash
cd admin-web
pnpm dev
```

学员端 H5：

```bash
cd h5-web
pnpm dev
```

默认接口文档地址：`http://localhost:3000/api-docs`。

## 常用命令

### 后端

```bash
cd backend
pnpm build
pnpm start:dev
pnpm seed
pnpm test:smoke
pnpm lint
```

### 前端

```bash
cd admin-web
pnpm build
pnpm test:routes
pnpm test:static

cd ../h5-web
pnpm build
pnpm test:routes
pnpm test:static
```

### PDF 服务

```bash
cd pdf-service
pytest
python tools/visual_api_smoke.py --help
python tools/evaluate_self_parser.py --help
```

## API 概览

后端启动后可通过 Swagger 查看完整接口：

```text
GET /api-docs
```

PDF 服务主要接口：

- `GET /health`：健康检查。
- `POST /parse`：上传 PDF 并解析题目。
- `POST /parse-by-url`：通过 URL 下载并解析 PDF。
- `POST /parse-answer-book-by-url`：通过 URL 解析答案册。
- `POST /ocr-region`：对指定区域执行 OCR/视觉识别。
- `POST /review-question-readability`：题目可读性预审。

## 目录说明

```text
.
├── admin-web/      # 管理后台
├── backend/        # NestJS 后端
├── h5-web/         # 学员端 H5
├── pdf-service/    # PDF 解析服务
├── scripts/        # 辅助脚本
├── docs/           # 文档
└── README.md
```

## 开发注意事项

- 本地开发时，前端 `VITE_API_BASE_URL` 应指向后端 API 地址。
- 后端默认开启 TypeORM `synchronize`，生产环境应谨慎使用并改为迁移管理。
- PDF 服务涉及大模型 API Key，提交代码前请确认 `.env`、密钥文件和本地凭据未被加入版本控制。
- Redis 可通过 `REDIS_ENABLED=false` 在本地开发环境关闭。

## License

当前仓库暂未声明开源许可证。
