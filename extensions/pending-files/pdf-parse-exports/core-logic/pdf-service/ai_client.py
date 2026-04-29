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
  "materials": [
    {
      "temp_id": "m1",
      "content": "材料文字（若有图表用[图表]占位）",
      "has_visual": true
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
      "analysis": "解析文字或null"
    }
  ]
}

规则：
1. page_type 不是 question 或 mixed 时，questions 返回 []
2. 判断题只有对/错两个选项，option_c 和 option_d 填 null
3. 题干不要包含题号数字
4. 只返回 JSON，不要任何解释或 markdown 代码块"""


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
            return result if isinstance(result, dict) else {"page_type": "unknown", "materials": [], "questions": []}
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
        return result if isinstance(result, dict) else {"page_type": "unknown", "materials": [], "questions": []}
    except Exception as exc:
        record_ai_call("qwen_vl", str(exc))
        message = str(exc)
        if sdk_fallback_error:
            message = f"OpenAI-compatible failed: {sdk_fallback_error}; DashScope SDK failed: {message}"
        return {"page_type": "unknown", "materials": [], "questions": [], "error": message}


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
