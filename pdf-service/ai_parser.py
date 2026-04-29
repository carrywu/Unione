from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

import dashscope
from openai import OpenAI


def _extract_json(text: str) -> str:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        return fenced.group(1).strip()
    return text


def analyze_image(base64_str: str) -> Optional[Dict[str, Any]]:
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        return None

    dashscope.api_key = api_key
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "image": f"data:image/png;base64,{base64_str}",
                },
                {
                    "text": (
                        "识别图表类型、提取关键数据（表格转markdown）、一句话概括。"
                        "只返回JSON：{\"chart_type\":\"\",\"data_markdown\":\"\",\"summary\":\"\"}"
                    ),
                },
            ],
        }
    ]

    try:
        response = dashscope.MultiModalConversation.call(
            model="qwen-vl-max",
            messages=messages,
        )
        content = response.output.choices[0].message.content
        text = content[0].get("text") if isinstance(content, list) else str(content)
        return json.loads(_extract_json(text))
    except Exception:
        return None


def structure_questions(raw_text: str) -> List[Dict[str, Any]]:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return []

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            temperature=0.1,
            messages=[
                {
                    "role": "system",
                    "content": "你是行测题目解析助手，只返回JSON数组，不返回任何其他内容",
                },
                {
                    "role": "user",
                    "content": (
                        "解析以下题目，字段为 index/type/content/options/answer/analysis。"
                        "type 只能是 single 或 judge。\n\n"
                        + raw_text
                    ),
                },
            ],
        )
        content = response.choices[0].message.content or "[]"
        data = json.loads(_extract_json(content))
        return data if isinstance(data, list) else []
    except Exception:
        return []
