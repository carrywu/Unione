from __future__ import annotations

import json
import os
import re
from typing import Any

from openai import OpenAI

from monitor import record_ai_call
from vision_ai.base import VisionAIProvider
from vision_ai.prompt_builder import build_page_review_prompt
from vision_ai.schema import VisionAIRequest, VisionAIResponse


class QwenVLProvider(VisionAIProvider):
    name = "qwen-vl"

    def __init__(
        self,
        *,
        api_key: str,
        model: str | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        base_url: str | None = None,
    ):
        self.api_key = api_key
        self.model = model or os.getenv("QWEN_VL_MODEL") or "qwen-vl-plus"
        self.timeout_seconds = timeout_seconds or _float_env("VISION_AI_TIMEOUT_SECONDS", 60.0)
        self.max_retries = max_retries if max_retries is not None else _int_env("VISION_AI_MAX_RETRIES", 2)
        self.base_url = base_url or os.getenv("DASHSCOPE_BASE_URL") or "https://dashscope.aliyuncs.com/compatible-mode/v1"

    def review_page(self, request: VisionAIRequest) -> VisionAIResponse:
        if not request.image_base64:
            raise ValueError("vision_ai_page_image_missing")
        prompt = build_page_review_prompt(request)
        last_error: Exception | None = None
        for _attempt in range(max(1, self.max_retries + 1)):
            try:
                record_ai_call("qwen_vl")
                client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout_seconds)
                response = client.chat.completions.create(
                    model=self.model,
                    temperature=0,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/png;base64,{request.image_base64}"},
                                },
                            ],
                        }
                    ],
                )
                content = response.choices[0].message.content or "{}"
                return VisionAIResponse.from_model_output(json.loads(_extract_json(content)), request.page)
            except Exception as exc:
                last_error = exc
                record_ai_call("qwen_vl", str(exc))
        raise ValueError(f"vision_ai_qwen_vl_failed: {last_error}") from last_error


def provider_from_env() -> QwenVLProvider | None:
    provider = (os.getenv("VISION_AI_PROVIDER") or "qwen-vl").strip().lower()
    if provider not in {"qwen-vl", "qwen_vl", "qwen"}:
        return None
    api_key = os.getenv("DASHSCOPE_API_KEY") or ""
    if not api_key:
        return None
    return QwenVLProvider(api_key=api_key)


def _extract_json(text: str) -> str:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        return fenced.group(1).strip()
    return text


def _int_env(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, ""))
    except ValueError:
        return default


def _float_env(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, ""))
    except ValueError:
        return default
