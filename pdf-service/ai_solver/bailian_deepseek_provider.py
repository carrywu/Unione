from __future__ import annotations

import json
import os
import re

from openai import OpenAI

from ai_solver.base import QuestionSolverProvider
from ai_solver.prompt_builder import build_question_solving_prompt
from ai_solver.schema import QuestionSolvingRequest, QuestionSolvingResponse
from monitor import record_ai_call


class BailianDeepSeekProvider(QuestionSolverProvider):
    name = "bailian-deepseek"

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
        self.model = model or os.getenv("BAILIAN_DEEPSEEK_MODEL") or "deepseek-r1"
        self.timeout_seconds = timeout_seconds or _float_env("AI_SOLVER_TIMEOUT_SECONDS", 60.0)
        self.max_retries = max_retries if max_retries is not None else _int_env("AI_SOLVER_MAX_RETRIES", 2)
        self.base_url = base_url or os.getenv("DASHSCOPE_BASE_URL") or "https://dashscope.aliyuncs.com/compatible-mode/v1"

    def solve_question(self, request: QuestionSolvingRequest) -> QuestionSolvingResponse:
        prompt = build_question_solving_prompt(request)
        last_error: Exception | None = None
        for _attempt in range(max(1, self.max_retries + 1)):
            try:
                record_ai_call("bailian_deepseek")
                client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout_seconds)
                response = client.chat.completions.create(
                    model=self.model,
                    temperature=0,
                    messages=[{"role": "user", "content": prompt}],
                )
                content = response.choices[0].message.content or "{}"
                return QuestionSolvingResponse.from_model_output(
                    json.loads(_extract_json(content)),
                    request.question_id,
                )
            except Exception as exc:
                last_error = exc
                record_ai_call("bailian_deepseek", str(exc))
        raise ValueError(f"ai_solver_bailian_deepseek_failed: {last_error}") from last_error


def provider_from_env() -> BailianDeepSeekProvider | None:
    provider = (os.getenv("AI_SOLVER_PROVIDER") or "bailian-deepseek").strip().lower()
    if provider not in {"bailian-deepseek", "bailian_deepseek", "deepseek", "dashscope-deepseek"}:
        return None
    api_key = os.getenv("DASHSCOPE_API_KEY") or ""
    if not api_key:
        return None
    return BailianDeepSeekProvider(api_key=api_key)


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
