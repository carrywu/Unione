# 项目背景
独立 Python 微服务，专门负责解析行测题目 PDF。
由 NestJS 后端通过 HTTP 调用，端口 8001。

# 技术栈
Python 3.11 + FastAPI + uvicorn
PyMuPDF(fitz) + pdfplumber + Pillow
dashscope（通义千问 VL，解析图片）
openai（兼容格式调用 DeepSeek，结构化文字）

# 核心流水线
PDF → 路由判定（text_layer_book | scanned_question_book | scanned_answer_book | answer_note）
    → parser_kernel 统一入口
    → layout_engine 分块
    → semantic_segmenter 识别题锚点 / 材料 / 选项 / 讲解 / 目录
    → question_group_builder 建立题组和材料组
    → adapter 输出兼容 models.py 的结果
    → 答案页解析 / 合并返回 JSON

说明：
- `question_splitter.py` 只保留兼容入口，实际切题规则统一在 `parser_kernel`
- `TextStrategy` fallback 也走同一套 `parser_kernel`
- 不保留第二套 `QUESTION_RE + next-match` 切题逻辑
- 扫描题本先整页截图走视觉识别，再回到同一套 `parser_kernel` 数据结构
- 扫描解析册和复盘笔记不走普通题本切题

# 截图原则
- 原样截取，不压缩，不 OCR，不修改像素
- padding=10px，保留周边上下文
- base64 编码后放在返回 JSON 里

# AI 配置
图片解析：dashscope qwen-vl-max（DASHSCOPE_API_KEY）
文字结构化：DeepSeek deepseek-chat（DEEPSEEK_API_KEY，openai兼容格式）

# 返回格式
见 models.py。

# 错误处理原则
单题 AI 解析失败 → needs_review=true，继续处理其他题
单页视觉超时/失败 → 输出 warning（如 `vision_page_timeout`），保留整页 screenshot，继续处理其他页
整体流水线报错 → 返回 HTTP 500 + { error: "..." }
不要因单题失败中断整个任务

# 扫描题本补充规则
- `scanned_question_book` 的视觉调用按页隔离；单页超时不能拖垮整本
- 同页“题在上、材料在下”允许低置信回挂；题目保留 `backward_material_link_low_confidence` / `material_range_uncertain`
- 低置信材料归属必须保留 `needs_review=true`
- debug 输出默认写入 `visual_pages.json`、`page_elements.json`、`question_groups.json`、`warnings.json`
