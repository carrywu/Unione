from __future__ import annotations

import json

from vision_ai.schema import VisionAIRequest


def build_page_review_prompt(request: VisionAIRequest) -> str:
    payload = {
        "page": request.page,
        "questions": request.questions,
        "visual_refs": request.visual_refs,
        "page_blocks": request.page_blocks,
        "ocr_text": request.ocr_text,
    }
    return f"""你是 PDF 题库解析结果的视觉纠偏助手。你只做增强判断，不重新解析整本题库。

请同时依据页面截图和当前规则解析 JSON 判断：
1. source_bbox 是否混入了图片、表格、图题。
2. visual_refs/images 是否归属到正确题目。
3. 同页/跨页表格片段是否应归为同一个 visual_group。
4. 题号前的资料说明文字是否应作为后续题目的材料。

硬性约束：
- 只输出严格 JSON，不要 Markdown，不要解释文字。
- 不允许删除题目。
- 不允许新增答案，除非页面中明确出现答案。
- 不允许改写 question stem 核心文本。
- 只能建议或修正 material、visual_refs、bbox、need_review、warnings。
- 如果不确定，降低 confidence 并写入 warnings。

输出 schema：
{{
  "page": {request.page},
  "corrections": [
    {{
      "question_id": "q6",
      "action": "update_visual_refs",
      "reason": "该表格标题和表格主体属于第6题前置资料",
      "confidence": 0.92,
      "updates": {{
        "visual_refs": ["p3-img1"],
        "same_visual_group_id": "vg_p3_1",
        "source_bbox": [132.72, 344.54, 408, 680],
        "need_review": false,
        "warnings": []
      }}
    }}
  ],
  "warnings": [
    {{
      "type": "uncertain_table_ownership",
      "message": "第5题和第6题附近均有资料，但表格标题明显属于第6题"
    }}
  ]
}}

当前规则解析 JSON：
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""
