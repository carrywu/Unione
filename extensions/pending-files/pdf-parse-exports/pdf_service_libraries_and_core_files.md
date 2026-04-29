# PDF Service 使用的库与核心文件

## PDF 处理库

- PyMuPDF / fitz
  - 当前核心 PDF 处理库
  - 用于打开 PDF、获取页数、提取页面文本、页面截图、区域截图、提取图片位置、检测图表/线条区域

- pdfplumber
  - 已加入依赖
  - 当前主要作为备用 PDF 解析工具预留

- Pillow
  - 图片处理依赖
  - 配合截图/图像处理使用

## 服务与网络库

- FastAPI + uvicorn
  - 提供 PDF 解析微服务接口

- httpx
  - 下载 PDF URL
  - PDF service 回调 backend

## AI 相关库/模型

- openai
  - 使用 OpenAI 兼容格式调用阿里云百炼/通义千问或 DeepSeek

- dashscope
  - 阿里云 DashScope SDK，作为备用调用方式

- qwen-vl-max
  - 通义千问视觉模型，用于整页截图视觉解析

- qwen-plus / DeepSeek
  - 用于纯文本结构化解析

## 核心实现文件

- `pdf-service/extractor.py`
  - PDF 文本、截图、图片、表格区域提取

- `pdf-service/detector.py`
  - PDF 类型检测与策略分流

- `pdf-service/strategies/text_strategy.py`
  - 纯文本/规则解析策略

- `pdf-service/strategies/visual_strategy.py`
  - 视觉 AI 整页解析策略

- `pdf-service/ai_client.py`
  - AI 调用封装、视觉解析、文本结构化、图表描述

- `pdf-service/pipeline.py`
  - 总解析流水线：检测、策略执行、校验、返回结果

- `pdf-service/main.py`
  - FastAPI 服务入口、解析接口、回调接口调用
