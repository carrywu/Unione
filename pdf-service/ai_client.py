from __future__ import annotations

import json
import os
import re
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

import dashscope
from openai import OpenAI
from monitor import record_ai_call

_AI_CONFIG: ContextVar[dict[str, str]] = ContextVar("AI_CONFIG", default={})


PAGE_PARSE_PROMPT = """你是行测题目提取助手。这是一份PDF页面截图，请提取其中所有题目。

返回严格的 JSON，格式如下：
{
  "page_type": "question（题目页）| toc（目录）| chapter（章节标题）| explanation（讲解）| mixed（混合）",
  "warnings": ["可选警告"],
  "materials": [
    {
      "temp_id": "m1",
      "content": "材料文字（若有图表用[图表]占位）",
      "has_visual": true,
      "bbox": [x0, y0, x1, y1]
    }
  ],
  "questions": [
    {
      "index": 1,
      "material_temp_id": null,
      "content": "完整题干",
      "option_a": "选项A内容",
      "option_b": "选项B内容",
      "option_c": "选项C内容",
      "option_d": "选项D内容",
      "answer": "A（确定）或 null（不确定）",
      "analysis": "解析文字或null",
      "bbox": [x0, y0, x1, y1],
      "stem_bbox": [x0, y0, x1, y1],
      "options": [
        {"label": "A", "text": "选项A内容", "bbox": [x0, y0, x1, y1]}
      ]
    }
  ],
  "visuals": [
    {
      "kind": "chart|image|table",
      "bbox": [x0, y0, x1, y1],
      "caption": "可选",
      "material_temp_id": null,
      "question_index": null
    }
  ]
}

规则：
1. page_type 不是 question 或 mixed 时，questions 返回 []
2. 判断题只有对/错两个选项，option_c 和 option_d 填 null
3. 题干不要包含题号数字
4. 所有 bbox 都使用图片像素坐标
5. 看不清的 bbox 可以填 null，但不要编造
6. 只返回 JSON，不要任何解释或 markdown 代码块"""


ANSWER_ANCHOR_PROMPT = """请识别这页答案解析册图片中的所有题号锚点。

锚点示例：
- 【例6】
- 例 6：
- 第6题
- 6.
- 6、

只返回严格 JSON 数组，不要解释，不要 markdown：
[
  {
    "question_index": 6,
    "anchor_text": "【例6】",
    "bbox": [x0, y0, x1, y1]
  }
]

要求：
1. bbox 使用输入图片的像素坐标，左上角为 [0, 0]
2. 只标出题号锚点文字本身，不要框住整段解析
3. 没有识别到锚点时返回 []
4. question_index 必须是数字"""


OCR_REGION_PROMPT = """请识别用户框选的 PDF 区域内容。

模式：{mode}

要求：
1. stem：只输出题干正文，去掉页眉、页脚、章节标题、题号和 A/B/C/D 选项。
2. options：拆分 A/B/C/D，返回 JSON 对象 {{"A":"...","B":"...","C":"...","D":"..."}}。
3. material：保留材料段落、表格信息和必要图表占位。
4. analysis：保留解析文本和公式推导。
5. 不要编造看不清的内容。

只返回严格 JSON：
{{"text":"...","options":{{"A":"...","B":"...","C":"...","D":"..."}},"confidence":0.0,"warnings":[]}}"""


READABILITY_REVIEW_PROMPT = """你是题库入库前的质量预审助手，只判断题目是否可读、是否足够让管理员理解并确认。

禁止改写题目，禁止补全缺失内容，禁止输出解析或答案建议。

请检查：
1. 题干是否完整、语义是否能独立理解。
2. 单选题选项是否可读，A/B/C/D 是否明显缺失或串行。
3. 材料/图表依赖是否缺失，是否需要重新框选材料区或图片区。
4. 现有解析警告是否影响理解。

只返回严格 JSON：
{{"readable":true,"needs_review":false,"score":0.0,"reasons":[],"prompts":[],"focus_areas":[]}}

字段说明：
- readable：题目当前内容是否基本可读可理解。
- needs_review：不可读或关键区域缺失时为 true。
- score：0 到 1 的可读性分数。
- reasons：简短原因。
- prompts：给管理员的动作提示，例如“重新框选题干区域”“重新框选选项区域”“补选材料图表”。
- focus_areas：只能使用 stem、options、material、images、analysis、warnings。

题目 JSON：
{question_json}"""


TEXT_PARSE_PROMPT = """你是行测题目解析助手。将以下原始文本解析为结构化JSON数组。

规则：
1. 识别所有完整题目（有题干+ABCD选项的才算）
2. 目录行（格式如"考法一..........3"）直接跳过，不要包含
3. 章节标题和讲解文字跳过
4. answer 字段：能明确识别则填写，不确定填 null
5. 判断题 option_c/option_d 填 null
6. 只返回JSON数组，不要markdown代码块，不要任何说明

输出格式：
[
  {
    "index": 1,
    "type": "single（单选）| judge（判断）",
    "content": "题干",
    "option_a": "...", "option_b": "...", "option_c": "...", "option_d": "...",
    "answer": "A 或 null",
    "analysis": "解析或null",
    "material_text": "若是材料题，这里填材料内容，否则null"
  }
]

原始文本：
{text}"""


def _extract_json(text: str) -> str:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        return fenced.group(1).strip()
    return text


@contextmanager
def use_config(config: dict[str, str] | None):
    token = _AI_CONFIG.set(config or {})
    try:
        yield
    finally:
        _AI_CONFIG.reset(token)


def _config_value(key: str, env_key: str | None = None, default: str | None = None) -> str | None:
    config = _AI_CONFIG.get()
    value = config.get(key)
    if value:
        return value
    if env_key:
        return os.getenv(env_key) or default
    return default


def _chat_completion_json(
    *,
    api_key: str,
    base_url: str,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.1,
) -> Any:
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=90.0)
    response = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=messages,
    )
    content = response.choices[0].message.content or "{}"
    return json.loads(_extract_json(content))


def parse_page_visual(page_b64: str) -> dict[str, Any]:
    """Full-page screenshot -> structured question JSON via Qwen-VL."""
    api_key = _config_value("dashscope_api_key", "DASHSCOPE_API_KEY")
    if not api_key:
        return {
            "page_type": "unknown",
            "materials": [],
            "questions": [],
            "visuals": [],
            "warnings": ["visual_api_key_missing"],
            "error": "DASHSCOPE_API_KEY not configured",
        }

    base_url = _config_value(
        "dashscope_base_url",
        "DASHSCOPE_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    model = _config_value("visual_model", "AI_VISUAL_MODEL", "qwen-vl-max")

    if base_url:
        try:
            record_ai_call("qwen_vl")
            result = _chat_completion_json(
                api_key=api_key,
                base_url=base_url,
                model=model or "qwen-vl-max",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": PAGE_PARSE_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{page_b64}"},
                            },
                        ],
                    }
                ],
            )
            return _normalize_page_visual_result(result)
        except Exception as exc:
            record_ai_call("qwen_vl", str(exc))
            # Fall back to DashScope SDK below; return the final SDK error if that also fails.
            sdk_fallback_error = str(exc)
    else:
        sdk_fallback_error = ""

    dashscope.api_key = api_key
    try:
        record_ai_call("qwen_vl")
        response = dashscope.MultiModalConversation.call(
            model="qwen-vl-max",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"image": f"data:image/png;base64,{page_b64}"},
                        {"text": PAGE_PARSE_PROMPT},
                    ],
                }
            ],
        )
        content = response.output.choices[0].message.content
        text = content[0].get("text") if isinstance(content, list) else str(content)
        result = json.loads(_extract_json(text))
        return _normalize_page_visual_result(result)
    except Exception as exc:
        record_ai_call("qwen_vl", str(exc))
        message = str(exc)
        if sdk_fallback_error:
            message = f"OpenAI-compatible failed: {sdk_fallback_error}; DashScope SDK failed: {message}"
        return {
            "page_type": "unknown",
            "materials": [],
            "questions": [],
            "visuals": [],
            "warnings": ["visual_model_failed"],
            "error": message,
        }


def _normalize_page_visual_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {
            "page_type": "unknown",
            "materials": [],
            "questions": [],
            "visuals": [],
            "warnings": ["visual_schema_invalid"],
            "schema_validation": {"invalid_root": True},
            "raw_model_result": result,
        }

    page_type = str(result.get("page_type") or "unknown")
    if page_type not in {"question", "toc", "chapter", "explanation", "mixed"}:
        page_type = "unknown"
    warnings = [str(item) for item in (result.get("warnings") or []) if item]
    raw_materials = result.get("materials") or []
    raw_questions = result.get("questions") or []
    raw_visuals = result.get("visuals") or []
    materials = [_normalize_visual_material(item) for item in raw_materials]
    questions = [_normalize_visual_question(item) for item in raw_questions]
    visuals = [_normalize_visual_region(item) for item in raw_visuals]
    invalid_materials = len([item for item in materials if not item])
    invalid_questions = len([item for item in questions if not item])
    invalid_visuals = len([item for item in visuals if not item])
    normalized_materials = [item for item in materials if item]
    normalized_questions = [item for item in questions if item]
    normalized_visuals = [item for item in visuals if item]
    if invalid_materials:
        warnings.append("visual_materials_dropped")
    if invalid_questions:
        warnings.append("visual_questions_dropped")
    if invalid_visuals:
        warnings.append("visual_regions_dropped")
    return {
        "page_type": page_type,
        "materials": normalized_materials,
        "questions": normalized_questions,
        "visuals": normalized_visuals,
        "warnings": sorted(set(warnings)),
        "schema_validation": {
            "input_material_count": len(raw_materials) if isinstance(raw_materials, list) else 0,
            "input_question_count": len(raw_questions) if isinstance(raw_questions, list) else 0,
            "input_visual_count": len(raw_visuals) if isinstance(raw_visuals, list) else 0,
            "normalized_material_count": len(normalized_materials),
            "normalized_question_count": len(normalized_questions),
            "normalized_visual_count": len(normalized_visuals),
            "dropped_material_count": invalid_materials,
            "dropped_question_count": invalid_questions,
            "dropped_visual_count": invalid_visuals,
        },
        "raw_model_result": result,
    }


def _normalize_visual_material(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    content = str(item.get("content") or "").strip()
    if not content:
        return None
    return {
        "temp_id": str(item.get("temp_id") or ""),
        "content": content,
        "has_visual": bool(item.get("has_visual")),
        "bbox": _normalize_bbox(item.get("bbox")),
    }


def _normalize_visual_question(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    try:
        index = int(item.get("index"))
    except (TypeError, ValueError):
        return None
    if index <= 0:
        return None

    options = [_normalize_visual_option(opt) for opt in (item.get("options") or [])]
    options = [opt for opt in options if opt]
    question = {
        "index": index,
        "material_temp_id": item.get("material_temp_id"),
        "content": _normalize_text(item.get("content")),
        "option_a": _normalize_text(item.get("option_a")),
        "option_b": _normalize_text(item.get("option_b")),
        "option_c": _normalize_text(item.get("option_c")),
        "option_d": _normalize_text(item.get("option_d")),
        "answer": _normalize_text(item.get("answer")),
        "analysis": _normalize_text(item.get("analysis")),
        "bbox": _normalize_bbox(item.get("bbox")),
        "stem_bbox": _normalize_bbox(item.get("stem_bbox") or item.get("bbox")),
        "options": options,
    }
    for option in options:
        key = f"option_{option['label'].lower()}"
        if not question.get(key):
            question[key] = option["text"]
    return question


def _normalize_visual_option(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    label = str(item.get("label") or "").strip().upper()
    if label not in {"A", "B", "C", "D"}:
        return None
    return {
        "label": label,
        "text": _normalize_text(item.get("text")) or "",
        "bbox": _normalize_bbox(item.get("bbox")),
    }


def _normalize_visual_region(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    bbox = _normalize_bbox(item.get("bbox"))
    if not bbox:
        return None
    kind = str(item.get("kind") or "").strip().lower()
    if kind not in {"chart", "image", "table"}:
        kind = "image"
    return {
        "kind": kind,
        "bbox": bbox,
        "caption": _normalize_text(item.get("caption")),
        "material_temp_id": item.get("material_temp_id"),
        "question_index": item.get("question_index"),
    }


def _normalize_bbox(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        bbox = [float(item) for item in value]
    except (TypeError, ValueError):
        return None
    if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        return None
    return bbox


def _normalize_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def parse_answer_anchors_visual(page_b64: str) -> list[dict[str, Any]]:
    """Full-page answer-book screenshot -> anchor bboxes via vision model."""
    api_key = _config_value("dashscope_api_key", "DASHSCOPE_API_KEY")
    if not api_key:
        return []

    base_url = _config_value(
        "dashscope_base_url",
        "DASHSCOPE_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    model = _config_value("visual_model", "AI_VISUAL_MODEL", "qwen-vl-max")

    if base_url:
        try:
            record_ai_call("qwen_vl")
            result = _chat_completion_json(
                api_key=api_key,
                base_url=base_url,
                model=model or "qwen-vl-max",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": ANSWER_ANCHOR_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{page_b64}"},
                            },
                        ],
                    }
                ],
            )
            return _normalize_answer_anchor_result(result)
        except Exception as exc:
            record_ai_call("qwen_vl", str(exc))
            sdk_fallback_error = str(exc)
    else:
        sdk_fallback_error = ""

    dashscope.api_key = api_key
    try:
        record_ai_call("qwen_vl")
        response = dashscope.MultiModalConversation.call(
            model=model or "qwen-vl-max",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"image": f"data:image/png;base64,{page_b64}"},
                        {"text": ANSWER_ANCHOR_PROMPT},
                    ],
                }
            ],
        )
        content = response.output.choices[0].message.content
        text = content[0].get("text") if isinstance(content, list) else str(content)
        return _normalize_answer_anchor_result(json.loads(_extract_json(text)))
    except Exception as exc:
        message = str(exc)
        if sdk_fallback_error:
            message = f"OpenAI-compatible failed: {sdk_fallback_error}; DashScope SDK failed: {message}"
        record_ai_call("qwen_vl", message)
        return []


def _normalize_answer_anchor_result(result: Any) -> list[dict[str, Any]]:
    if isinstance(result, dict):
        result = result.get("anchors") or result.get("items") or []
    if not isinstance(result, list):
        return []

    anchors: list[dict[str, Any]] = []
    for item in result:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("question_index") or item.get("index"))
            bbox = [float(value) for value in item.get("bbox", [])[:4]]
        except (TypeError, ValueError):
            continue
        if index <= 0 or len(bbox) != 4 or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
            continue
        anchors.append(
            {
                "question_index": index,
                "anchor_text": str(item.get("anchor_text") or item.get("text") or f"例{index}"),
                "bbox": bbox,
            }
        )
    return anchors


def ocr_region_visual(region_b64: str, mode: str) -> dict[str, Any]:
    api_key = _config_value("dashscope_api_key", "DASHSCOPE_API_KEY")
    if not api_key:
        return {
            "text": "",
            "options": {},
            "confidence": 0,
            "warnings": ["vision_model_not_configured"],
        }

    base_url = _config_value(
        "dashscope_base_url",
        "DASHSCOPE_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    model = _config_value("visual_model", "AI_VISUAL_MODEL", "qwen-vl-max")
    prompt = OCR_REGION_PROMPT.replace("{mode}", mode)

    if base_url:
        try:
            record_ai_call("qwen_vl")
            result = _chat_completion_json(
                api_key=api_key,
                base_url=base_url,
                model=model or "qwen-vl-max",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{region_b64}"},
                            },
                        ],
                    }
                ],
            )
            return _normalize_ocr_region_result(result)
        except Exception as exc:
            record_ai_call("qwen_vl", str(exc))
            sdk_fallback_error = str(exc)
    else:
        sdk_fallback_error = ""

    dashscope.api_key = api_key
    try:
        record_ai_call("qwen_vl")
        response = dashscope.MultiModalConversation.call(
            model=model or "qwen-vl-max",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"image": f"data:image/png;base64,{region_b64}"},
                        {"text": prompt},
                    ],
                }
            ],
        )
        content = response.output.choices[0].message.content
        text = content[0].get("text") if isinstance(content, list) else str(content)
        return _normalize_ocr_region_result(json.loads(_extract_json(text)))
    except Exception as exc:
        message = str(exc)
        if sdk_fallback_error:
            message = f"OpenAI-compatible failed: {sdk_fallback_error}; DashScope SDK failed: {message}"
        record_ai_call("qwen_vl", message)
        return {"text": "", "options": {}, "confidence": 0, "warnings": [message]}


def _normalize_ocr_region_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {"text": str(result or ""), "options": {}, "confidence": 0.5, "warnings": []}
    options = result.get("options") if isinstance(result.get("options"), dict) else {}
    return {
        "text": str(result.get("text") or ""),
        "options": {key: str(options.get(key) or options.get(key.lower()) or "") for key in ["A", "B", "C", "D"]},
        "confidence": float(result.get("confidence") or 0.7),
        "warnings": result.get("warnings") if isinstance(result.get("warnings"), list) else [],
    }


def review_question_readability(question: dict[str, Any]) -> dict[str, Any]:
    fallback = _heuristic_readability_review(question)
    api_key = (
        _config_value("text_api_key", "AI_TEXT_API_KEY")
        or _config_value("deepseek_api_key", "DEEPSEEK_API_KEY")
        or _config_value("dashscope_api_key", "DASHSCOPE_API_KEY")
    )
    if not api_key:
        return {**fallback, "source": "heuristic_no_ai_config"}

    try:
        base_url = (
            _config_value("text_base_url", "AI_TEXT_BASE_URL")
            or _config_value("deepseek_base_url", "DEEPSEEK_BASE_URL")
            or _config_value(
                "dashscope_base_url",
                "DASHSCOPE_BASE_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            )
        )
        model = (
            _config_value("text_model", "AI_TEXT_MODEL")
            or _config_value("deepseek_model", "DEEPSEEK_MODEL")
            or "qwen-plus"
        )
        prompt = READABILITY_REVIEW_PROMPT.replace(
            "{question_json}",
            json.dumps(question, ensure_ascii=False)[:12000],
        )
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=90.0)
        provider = "deepseek" if "deepseek" in (base_url or "") or _config_value("deepseek_api_key", "DEEPSEEK_API_KEY") else "qwen_text"
        record_ai_call(provider)
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {"role": "system", "content": "你只返回 JSON，不返回 markdown 或解释。"},
                {"role": "user", "content": prompt},
            ],
        )
        result = json.loads(_extract_json(response.choices[0].message.content or "{}"))
        return _normalize_readability_review(result, fallback)
    except Exception as exc:
        record_ai_call("readability_review", str(exc))
        return {**fallback, "source": "heuristic_ai_failed", "warnings": [str(exc)]}


def _heuristic_readability_review(question: dict[str, Any]) -> dict[str, Any]:
    content = str(question.get("content") or "").strip()
    qtype = str(question.get("type") or "single")
    options = question.get("options") if isinstance(question.get("options"), dict) else {}
    images = question.get("images") if isinstance(question.get("images"), list) else []
    material = str(question.get("material") or "").strip()
    parse_warnings = question.get("parse_warnings") if isinstance(question.get("parse_warnings"), list) else []
    reasons: list[str] = []
    prompts: list[str] = []
    focus_areas: list[str] = []

    if len(content) < 12:
        reasons.append("题干过短或缺失")
        prompts.append("重新框选题干区域")
        focus_areas.append("stem")
    if qtype != "judge":
        missing = [key for key in ["A", "B", "C", "D"] if not str(options.get(key) or "").strip()]
        if missing:
            reasons.append(f"选项缺失：{','.join(missing)}")
            prompts.append("重新框选选项区域")
            focus_areas.append("options")
    if any(token in content for token in ["[图表]", "[图片]", "见图", "如下图"]) and not images and not material:
        reasons.append("题干依赖图表或材料但未检测到对应内容")
        prompts.append("重新框选材料区或图片区")
        focus_areas.extend(["material", "images"])
    if parse_warnings:
        reasons.append("存在解析警告")
        prompts.append("根据解析警告复查题干、选项和图片")
        focus_areas.append("warnings")

    focus_areas = list(dict.fromkeys(focus_areas))
    needs_review = bool(reasons)
    return {
        "readable": not needs_review,
        "needs_review": needs_review,
        "score": 0.55 if needs_review else 0.88,
        "reasons": reasons,
        "prompts": prompts,
        "focus_areas": focus_areas,
        "source": "heuristic",
    }


def _normalize_readability_review(result: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return fallback
    focus_areas = result.get("focus_areas") if isinstance(result.get("focus_areas"), list) else []
    allowed = {"stem", "options", "material", "images", "analysis", "warnings"}
    normalized_focus = [str(item) for item in focus_areas if str(item) in allowed]
    score = result.get("score")
    try:
        numeric_score = max(0.0, min(1.0, float(score)))
    except (TypeError, ValueError):
        numeric_score = float(fallback["score"])
    needs_review = bool(result.get("needs_review"))
    readable = bool(result.get("readable")) and not needs_review
    return {
        "readable": readable,
        "needs_review": needs_review,
        "score": numeric_score,
        "reasons": [str(item) for item in result.get("reasons", []) if str(item).strip()],
        "prompts": [str(item) for item in result.get("prompts", []) if str(item).strip()],
        "focus_areas": normalized_focus,
        "source": "ai_text_model",
    }


def parse_text_block(raw_text: str) -> list[dict[str, Any]]:
    """Text chunk -> structured questions via DeepSeek."""
    if not raw_text.strip() or len(raw_text.strip()) < 50:
        return []

    api_key = (
        _config_value("text_api_key", "AI_TEXT_API_KEY")
        or _config_value("deepseek_api_key", "DEEPSEEK_API_KEY")
        or _config_value("dashscope_api_key", "DASHSCOPE_API_KEY")
    )
    if not api_key:
        return []

    try:
        base_url = (
            _config_value("text_base_url", "AI_TEXT_BASE_URL")
            or _config_value("deepseek_base_url", "DEEPSEEK_BASE_URL")
            or _config_value(
                "dashscope_base_url",
                "DASHSCOPE_BASE_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            )
        )
        model = (
            _config_value("text_model", "AI_TEXT_MODEL")
            or _config_value("deepseek_model", "DEEPSEEK_MODEL")
            or ("deepseek-chat" if _config_value("deepseek_api_key", "DEEPSEEK_API_KEY") else "qwen-plus")
        )
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=90.0)
        provider = "deepseek" if "deepseek" in (base_url or "") or _config_value("deepseek_api_key", "DEEPSEEK_API_KEY") else "qwen_vl"
        record_ai_call(provider)
        response = client.chat.completions.create(
            model=model,
            temperature=0.1,
            messages=[
                {
                    "role": "system",
                    "content": "你是行测题目解析助手，只返回JSON，不返回任何其他内容",
                },
                {
                    "role": "user",
                    "content": TEXT_PARSE_PROMPT.replace("{text}", raw_text[:8000]),
                },
            ],
        )
        text = response.choices[0].message.content or "[]"
        result = json.loads(_extract_json(text))
        return result if isinstance(result, list) else []
    except Exception:
        record_ai_call("deepseek", "text parse failed")
        return []


def describe_visual_element(img_b64: str, question_context: str = "") -> str:
    """Image/table -> textual description for review/search."""
    api_key = _config_value("dashscope_api_key", "DASHSCOPE_API_KEY")
    if not api_key:
        return ""

    base_url = _config_value(
        "dashscope_base_url",
        "DASHSCOPE_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    model = _config_value("visual_model", "AI_VISUAL_MODEL", "qwen-vl-max")
    context_hint = f"这道题的题干是：{question_context[:100]}" if question_context else ""
    prompt = f"""{context_hint}
请描述这张图表：
1. 图表类型（折线图/柱状图/饼图/数据表格/示意图/其他）
2. 关键数据（若是表格或图表，提取核心数值，用markdown表格格式）
3. 一句话概括主要内容
只返回JSON：{{"chart_type":"...","key_data":"...","summary":"..."}}"""
    if base_url:
        try:
            record_ai_call("qwen_vl")
            result = _chat_completion_json(
                api_key=api_key,
                base_url=base_url,
                model=model or "qwen-vl-max",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                            },
                        ],
                    }
                ],
            )
            return "\n".join(
                part for part in [result.get("summary", ""), result.get("key_data", "")] if part
            )
        except Exception:
            record_ai_call("qwen_vl", "visual describe failed")
            pass

    dashscope.api_key = api_key
    try:
        record_ai_call("qwen_vl")
        response = dashscope.MultiModalConversation.call(
            model="qwen-vl-max",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"image": f"data:image/png;base64,{img_b64}"},
                        {
                            "text": prompt,
                        },
                    ],
                }
            ],
        )
        content = response.output.choices[0].message.content
        text = content[0].get("text") if isinstance(content, list) else str(content)
        result = json.loads(_extract_json(text))
        return "\n".join(
            part
            for part in [result.get("summary", ""), result.get("key_data", "")]
            if part
        )
    except Exception:
        record_ai_call("qwen_vl", "visual describe failed")
        return ""
