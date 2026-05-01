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
    return f"""你是 PDF 题库解析结果的 AI 预审核助手。你必须在人类审核前完成题目理解、视觉归属、图表摘要、答案建议、解析建议和质量预审核。

请同时依据页面截图和当前规则解析 JSON 判断：
1. source_bbox 是否混入了图片、表格、图题。
2. visual_refs/images 是否归属到正确题目。
3. 同页/跨页表格片段是否应归为同一个 visual_group。
4. 题号前的资料说明文字是否应作为后续题目的材料。
5. 每道题的题干、选项、图表上下文是否完整。
6. 题目是否可作答，答案建议和解析建议是什么。
7. 如果图表数据看不清，必须输出结构化失败原因和风险标签，不能把失败占位符写进题干、选项、答案或解析。

硬性约束：
- 只输出严格 JSON，不要 Markdown，不要解释文字。
- 不允许删除题目。
- 不允许改写 question stem 核心文本。
- 可以输出 AI 答案建议和解析建议；它们是预审核建议，不覆盖官方答案。
- 如果不确定，answer_suggestion.answer 填 "unknown"，analysis_suggestion.analysis_unknown_reason 写明原因，降低 confidence 并写入 risk_flags。
- 禁止输出或复述 "visual parse unavailable"、"[visual parse unavailable]"、"[page N visual parse ...]"、"page visual parse"、"unavailable" 等占位文本。

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
  "questions": [
    {{
      "question_id": "q6",
      "question_no": 6,
      "question_type": "资料分析/图表题/单选题",
      "stem": "题干摘要，不要含视觉失败占位符",
      "options": [
        {{"label": "A", "text": "选项A"}},
        {{"label": "B", "text": "选项B"}},
        {{"label": "C", "text": "选项C"}},
        {{"label": "D", "text": "选项D"}}
      ],
      "visuals": [
        {{
          "visual_id": "p3-img1",
          "belongs_to_question": true,
          "image_role": "chart/table/diagram/stem_material/option_image/irrelevant/unknown",
          "linked_by": "ai",
          "link_reason": "为什么属于或不属于该题",
          "visual_summary": "图表标题、坐标轴/字段、年份、数值、单位和关键信息摘要",
          "key_values": [],
          "visual_parse_status": "success/partial/failed/skipped",
          "visual_error": null,
          "confidence": 0.0
        }}
      ],
      "understanding": {{
        "question_intent": "题目问什么",
        "required_visual_evidence": "需要哪些图表证据",
        "can_answer_from_available_context": true,
        "missing_context": []
      }},
      "answer_suggestion": {{
        "answer": "A/B/C/D/unknown",
        "confidence": 0.0,
        "reasoning": "答案依据",
        "calculation_steps": [],
        "evidence": [],
        "answer_unknown_reason": null
      }},
      "analysis_suggestion": {{
        "text": "候选解析",
        "confidence": 0.0,
        "analysis_unknown_reason": null
      }},
      "question_quality": {{
        "stem_complete": true,
        "options_complete": true,
        "visual_context_complete": true,
        "answer_derivable": true,
        "analysis_derivable": true,
        "duplicate_suspected": false,
        "needs_review": false,
        "review_reasons": []
      }},
      "ai_audit": {{
        "status": "passed/warning/failed",
        "verdict": "可通过/需复核/不建议入库",
        "summary": "预审核摘要",
        "needs_review": false,
        "risk_flags": [],
        "review_reasons": []
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
