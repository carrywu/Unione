from __future__ import annotations

import json

from ai_solver.schema import QuestionSolvingRequest


def build_question_solving_prompt(request: QuestionSolvingRequest) -> str:
    payload = {
        "question_id": request.question_id,
        "question_number": request.question_number,
        "stem": request.stem,
        "options": request.options,
        "material": request.material,
        "original_answer": request.original_answer,
        "original_analysis": request.original_analysis,
        "visual_refs": request.visual_refs,
        "image_refs": request.image_refs,
        "ai_review_notes": request.ai_review_notes,
        "ai_corrections": request.ai_corrections,
        "visual_descriptions": request.visual_descriptions,
        "source_page": request.source_page,
        "parse_warnings": request.parse_warnings,
        "needs_review": request.needs_review,
    }
    return f"""你是公务员/事业单位考试题目的解题助手。请基于题干、选项、材料和视觉上下文独立解题。

要求：
- 只能输出严格 JSON，不要 Markdown，不要解释 JSON 外文本。
- 可以参考 original_answer 和 original_analysis，但不要盲信；如冲突请标记 answer_conflict。
- 不要编造缺失数据；信息不足时降低 ai_answer_confidence 并加入 ai_risk_flags。
- 如果题目依赖表格/图片但 visual_descriptions、visual_refs 或 material 不足，ai_answer_confidence 必须 <= 0.6，ai_risk_flags 必须包含 missing_context。
- 答案只输出选项字母或判断题答案，不要输出长句。
- ai_candidate_analysis 要给出可供人工审核的候选解析。

输出 schema：
{{
  "question_id": "{request.question_id}",
  "ai_candidate_answer": "C",
  "ai_candidate_analysis": "A项……；B项……；C项……；D项……。因此选C。",
  "ai_answer_confidence": 0.86,
  "ai_reasoning_summary": "本题考查资料分析中的表格读取和增长率比较。",
  "ai_knowledge_points": ["资料分析", "表格读取", "增长率比较"],
  "ai_risk_flags": ["requires_table"],
  "answer_conflict": false
}}

当前题目 JSON：
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""
