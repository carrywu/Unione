# PDF 解析核心处理逻辑源码快照

这里保存的是当前项目 PDF 解析服务的核心处理逻辑源码，方便后续单独分析、迁移或重构。

## 文件说明

- `pdf-service/main.py`：FastAPI 服务入口、解析接口、回调逻辑
- `pdf-service/models.py`：解析请求/响应数据结构
- `pdf-service/extractor.py`：PDF 文本、截图、图片、表格区域提取
- `pdf-service/detector.py`：PDF 类型检测与策略选择依据
- `pdf-service/pipeline.py`：解析流水线入口，负责检测、策略执行、校验、结果转换
- `pdf-service/ai_client.py`：通义千问/DeepSeek/OpenAI 兼容 AI 调用封装
- `pdf-service/validator.py`：题目清洗、过滤、待审核标记
- `pdf-service/strategies/text_strategy.py`：文本解析策略
- `pdf-service/strategies/visual_strategy.py`：视觉解析策略

- `pdf-service/strategies/universal_question_strategy.py`：通用 PyMuPDF 文本优先题目解析策略，支持多题号/选项模式、章节路径、材料绑定和审核元数据。
