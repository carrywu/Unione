from __future__ import annotations

import json
import os
import queue
import re
import threading
import time
import httpx
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

import dashscope
from openai import OpenAI
from monitor import record_ai_call

_AI_CONFIG: ContextVar[dict[str, str]] = ContextVar("AI_CONFIG", default={})


PAGE_PARSE_PROMPT = """你是“先读题再识别”的试卷阅片引擎。请基于整页图像理解题目结构、图表关系，并返回完整结构化 JSON，不得编造。

你必须先理解整页，不要先分割小块再理解。

规则:
1. 严格返回 JSON，不要 Markdown 和解释。
2. 所有 bbox 为图片像素坐标 [x0, y0, x1, y1]。
3. 所有题目必须给出完整题干与完整选项（可缺项时用空值）。
4. 题图必须给出归属，禁止以“同页即归属”替代判断。
5. 不允许输出占位文本（如 visual parse unavailable / [visual parse ...] / unavailable）。

返回格式示例：
{
  "page_type": "question|toc|chapter|explanation|mixed|unknown",
  "page_analysis": {
    "page_no": 1,
    "questions_detected": 2,
    "cross_page_needed": false,
    "page_level_risk_flags": []
  },
  "materials": [
    {
      "temp_id": "m1",
      "content": "材料正文",
      "has_visual": true,
      "bbox": [x0, y0, x1, y1]
    }
  ],
  "questions": [
    {
      "index": 6,
      "material_temp_id": "m1",
      "content": "完整题干",
      "question_type": "资料分析/图表题/单选题",
      "pages": [1],
      "is_cross_page": false,
      "stem_bbox": [x0, y0, x1, y1],
      "options_bbox": [x0, y0, x1, y1],
      "visual_groups": [
        {
          "group_id": "vg_page_1_1",
          "type": "chart|table|diagram|image|material",
          "member_blocks": ["b1", "b2"],
          "merged_bbox": [x0, y0, x1, y1],
          "title_bbox": [x0, y0, x1, y1],
          "legend_bbox": [x0, y0, x1, y1],
          "table_header_bbox": [x0, y0, x1, y1],
          "axis_bbox": [x0, y0, x1, y1],
          "notes_bbox": [x0, y0, x1, y1],
          "title_included": true,
          "legend_included": true,
          "axis_included": true,
          "table_header_included": true,
          "notes_included": true,
          "is_fragmented_before_merge": false,
          "belongs_to_question": true,
          "link_reason": "依据题干“2017~2021”与图表标题匹配",
          "visual_summary": "图表摘要",
          "key_values": ["单位: 元", "年份:2017-2021"],
          "confidence": 0.0
        }
      ],
      "content_quality": {
        "question_complete": true,
        "visual_complete": true,
        "stem_complete": true,
        "options_complete": true,
        "title_missing": false,
        "stem_missing": false,
        "options_missing": false,
        "needs_review": false,
        "risk_flags": [],
        "review_reasons": []
      },
      "capture_plan": {
        "should_recrop": true,
        "crop_targets": ["stem", "options", "visual_group_1"],
        "padding": 24,
        "must_include": ["chart_title", "legend", "axis_labels", "table_header", "notes"]
      },
      "understanding": {
        "question_intent": "题目考查什么",
        "required_visual_evidence": "必须用哪个图/表",
        "can_answer_from_available_context": true,
        "missing_context": []
      },
      "answer_suggestion": {
        "answer": "A|B|C|D|unknown",
        "confidence": 0.0,
        "reasoning": "候选答案与依据",
        "calculation_steps": [],
        "evidence": [],
        "answer_unknown_reason": null
      },
      "analysis_suggestion": {
        "text": "可见解题说明",
        "confidence": 0.0,
        "analysis_unknown_reason": null
      },
      "question_quality": {
        "stem_complete": true,
        "options_complete": true,
        "visual_context_complete": true,
        "answer_derivable": true,
        "analysis_derivable": true,
        "duplicate_suspected": false,
        "needs_review": false,
        "review_reasons": []
      },
      "ai_audit": {
        "status": "passed|warning|failed|skipped",
        "verdict": "可通过|需复核|不建议入库",
        "summary": "预审核摘要",
        "needs_review": false,
        "risk_flags": [],
        "review_reasons": []
      },
      "option_a": "A 选项内容",
      "option_b": "B 选项内容",
      "option_c": "C 选项内容",
      "option_d": "D 选项内容",
      "answer": null,
      "analysis": null,
      "bbox": [x0, y0, x1, y1],
      "options": [
        {"label": "A", "text": "...", "bbox": [x0, y0, x1, y1]}
      ]
    }
  ],
  "visuals": [
    {
      "kind": "chart|image|table|diagram",
      "bbox": [x0, y0, x1, y1],
      "caption": "标题/图例或表头文本",
      "material_temp_id": null,
      "question_index": null,
      "group_id": "vg_page_1_1",
      "belongs_to_question": false
    }
  ],
  "visual_merge_candidates": [
    {"group_id": "vg_page_1_1", "candidate_blocks": [1, 2, 3], "reason": "检测框相邻且属于同一图表"}
  ],
  "warnings": ["可选警告"],
  "page_level_risk_flags": []
}

规则：
1. page_type 不是 question 或 mixed 时，questions 可以为空。
2. 若存在跨页题目，设置 pages 与 is_cross_page true。
3. stem/visuals/options 的边界尽量包含标题、表头、图例、坐标轴、脚注等必要上下文。
4. 若缺失题干或选项，必须通过 content_quality 或 question_quality 标注并设置 need_review。
5. 先返回“理解结果”，再输出答案建议/解析建议（若不能给出写 unknown 并说明原因）。
"""


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

REPAIR_QUESTION_PROMPT = """你是资料分析题库的单题解析修复助手。

你只能基于输入内容提出候选修正，不要编造看不清或输入中不存在的信息。

请去除页眉页脚、章节标题、目录残留，修正题干和 A/B/C/D 选项边界，并保留需要人工复核的 warnings。

只返回严格 JSON：
{
  "content": "",
  "options": {"A": "", "B": "", "C": "", "D": ""},
  "visual_refs": [],
  "material_text": "",
  "remove_texts": [],
  "warnings": [],
  "confidence": 0.0
}

当前题与上下文 JSON：
{repair_json}"""


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


DEFAULT_VISION_TIMEOUT_SECONDS = 120.0


def _safe_positive_timeout(value: str | None, default: float) -> float:
    try:
        timeout = float(value or 0)
    except (TypeError, ValueError):
        return default
    return timeout if timeout > 0 else default


def _vision_timeout_seconds(default: float = DEFAULT_VISION_TIMEOUT_SECONDS) -> float:
    return _safe_positive_timeout(
        os.getenv("VISION_AI_TIMEOUT_SECONDS")
        or os.getenv("PDF_VISUAL_OPENAI_TIMEOUT_SECONDS")
        or os.getenv("PDF_VISUAL_PAGE_TIMEOUT_SECONDS"),
        default,
    )


def _vision_provider_timeout_seconds(default: float = DEFAULT_VISION_TIMEOUT_SECONDS) -> float:
    return _safe_positive_timeout(
        os.getenv("VISION_AI_PROVIDER_TIMEOUT_SECONDS")
        or os.getenv("PDF_VISUAL_PROVIDER_TIMEOUT_SECONDS"),
        default,
    )


def _call_with_timeout(callable_obj: Any, timeout_seconds: float) -> Any:
    result_queue: queue.Queue[Any] = queue.Queue(maxsize=1)
    error_queue: queue.Queue[BaseException] = queue.Queue(maxsize=1)

    def _runner() -> None:
        try:
            result_queue.put(callable_obj())
        except BaseException as exc:  # pragma: no cover - defensive wrapper
            error_queue.put(exc)

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join(timeout_seconds)
    if thread.is_alive():
        raise TimeoutError(f"provider_call_timeout_after_{timeout_seconds:.1f}s")
    if not error_queue.empty():
        raise error_queue.get()
    if result_queue.empty():
        raise RuntimeError("provider_call_empty_result")
    return result_queue.get()


def _chat_client(
    api_key: str,
    base_url: str,
    timeout: float | None = None,
    default_headers: dict[str, str] | None = None,
) -> OpenAI:
    visual_timeout = _safe_positive_timeout(
        os.getenv("PDF_VISUAL_OPENAI_TIMEOUT_SECONDS")
        or os.getenv("VISION_AI_TIMEOUT_SECONDS")
        or os.getenv("PDF_VISUAL_PAGE_TIMEOUT_SECONDS"),
        float(timeout or DEFAULT_VISION_TIMEOUT_SECONDS),
    )
    kwargs: dict[str, Any] = {}
    if default_headers:
        kwargs["default_headers"] = default_headers
    try:
        http_client = httpx.Client(timeout=httpx.Timeout(visual_timeout), trust_env=False)
        return OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=visual_timeout,
            http_client=http_client,
            **kwargs,
        )
    except Exception:
        return OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=visual_timeout,
            **kwargs,
        )


def _chat_completion_json(
    *,
    api_key: str,
    base_url: str,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.1,
    timeout: float | None = None,
    default_headers: dict[str, str] | None = None,
) -> Any:
    client = _chat_client(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout or _vision_timeout_seconds(),
        default_headers=default_headers,
    )
    response = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=messages,
    )
    content = response.choices[0].message.content or "{}"
    return json.loads(_extract_json(content))


def _vision_call_messages(prompt: str, page_b64: str) -> list[dict[str, Any]]:
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{page_b64}"},
                },
            ],
        }
    ]


def _provider_failed(result: dict[str, Any]) -> bool:
    warnings = set(str(item) for item in result.get("warnings") or [])
    if warnings & {"visual_model_failed", "vision_page_timeout", "visual_schema_invalid"}:
        return True
    return bool(result.get("error") and result.get("page_type") == "unknown")


def _vision_attempt_payload(
    *,
    provider: str,
    model: str,
    timeout_seconds: float,
    started_at: float,
    status: str,
    error_type: str | None = None,
    error_message: str | None = None,
    fallback_from: str | None = None,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "model": model,
        "timeout_seconds": timeout_seconds,
        "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
        "status": status,
        "error_type": error_type,
        "error_message": error_message,
        "fallback_from": fallback_from,
    }


def _annotate_vision_result(
    result: dict[str, Any],
    *,
    provider: str,
    model: str,
    timeout_seconds: float,
    elapsed_ms: int,
    attempts: list[dict[str, Any]],
    fallback_from: str | None = None,
) -> dict[str, Any]:
    result["_vision_provider"] = provider
    result["_vision_model"] = model
    result["_vision_timeout_seconds"] = timeout_seconds
    result["_vision_elapsed_ms"] = elapsed_ms
    result["_vision_provider_attempts"] = attempts
    result["_vision_fallback_from"] = fallback_from
    return result


def _call_openai_vision_provider(
    *,
    provider: str,
    api_key: str,
    base_url: str,
    model: str,
    page_b64: str,
    timeout_seconds: float,
    default_headers: dict[str, str] | None = None,
    fallback_from: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    started = time.perf_counter()
    record_ai_call(provider)
    try:
        raw = _call_with_timeout(
            lambda: _chat_completion_json(
                api_key=api_key,
                base_url=base_url,
                model=model,
                messages=_vision_call_messages(PAGE_PARSE_PROMPT, page_b64),
                timeout=timeout_seconds,
                default_headers=default_headers,
            ),
            timeout_seconds,
        )
        normalized = _normalize_page_visual_result(raw)
        status = "failed" if _provider_failed(normalized) else "ok"
        attempt = _vision_attempt_payload(
            provider=provider,
            model=model,
            timeout_seconds=timeout_seconds,
            started_at=started,
            status=status,
            error_type="model_result_failed" if status == "failed" else None,
            error_message=normalized.get("error") if status == "failed" else None,
            fallback_from=fallback_from,
        )
        if status == "failed":
            record_ai_call(provider, str(normalized.get("error") or "model_result_failed"))
        return normalized, attempt
    except Exception as exc:
        record_ai_call(provider, str(exc))
        attempt = _vision_attempt_payload(
            provider=provider,
            model=model,
            timeout_seconds=timeout_seconds,
            started_at=started,
            status="failed",
            error_type=type(exc).__name__,
            error_message=str(exc),
            fallback_from=fallback_from,
        )
        return {
            "page_type": "unknown",
            "materials": [],
            "questions": [],
            "visuals": [],
            "warnings": ["visual_model_failed"],
            "error": str(exc),
            "schema_validation": {"exception": str(exc)},
            "raw_model_result": {"error": str(exc), "provider": provider, "model": model},
        }, attempt


def parse_page_visual(page_b64: str) -> dict[str, Any]:
    """Full-page screenshot -> structured question JSON via Qwen-VL."""
    page_timeout_seconds = _vision_timeout_seconds()
    timeout_seconds = _vision_provider_timeout_seconds(page_timeout_seconds)
    api_key = _config_value("dashscope_api_key", "DASHSCOPE_API_KEY")
    if not api_key:
        return {
            "page_type": "unknown",
            "materials": [],
            "questions": [],
            "visuals": [],
            "warnings": ["visual_api_key_missing"],
            "error": "DASHSCOPE_API_KEY not configured",
            "_vision_provider": "qwen_vl",
            "_vision_model": _config_value("visual_model", "AI_VISUAL_MODEL", "qwen-vl-max"),
            "_vision_timeout_seconds": timeout_seconds,
            "_vision_elapsed_ms": 0,
            "_vision_provider_attempts": [
                {
                    "provider": "qwen_vl",
                    "model": _config_value("visual_model", "AI_VISUAL_MODEL", "qwen-vl-max"),
                    "timeout_seconds": timeout_seconds,
                    "elapsed_ms": 0,
                    "status": "failed",
                    "error_type": "missing_api_key",
                    "error_message": "DASHSCOPE_API_KEY not configured",
                    "fallback_from": None,
                }
            ],
        }

    base_url = _config_value(
        "dashscope_base_url",
        "DASHSCOPE_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    model = _config_value("visual_model", "AI_VISUAL_MODEL", "qwen-vl-max")
    attempts: list[dict[str, Any]] = []

    if base_url:
        primary_result, primary_attempt = _call_openai_vision_provider(
            provider="qwen_vl",
            api_key=api_key,
            base_url=base_url,
            model=model or "qwen-vl-max",
            page_b64=page_b64,
            timeout_seconds=timeout_seconds,
        )
        attempts.append(primary_attempt)
        if not _provider_failed(primary_result):
            return _annotate_vision_result(
                primary_result,
                provider="qwen_vl",
                model=model or "qwen-vl-max",
                timeout_seconds=timeout_seconds,
                elapsed_ms=primary_attempt["elapsed_ms"],
                attempts=attempts,
            )
        sdk_fallback_error = primary_result.get("error") or primary_attempt.get("error_message") or ""
    else:
        sdk_fallback_error = ""

    mimo_api_key = _config_value("mimo_api_key", "MIMO_API_KEY")
    mimo_base_url = _config_value(
        "mimo_base_url",
        "MIMO_BASE_URL",
        "https://token-plan-cn.xiaomimimo.com/v1",
    )
    mimo_model = (
        _config_value("mimo_vision_model", "MIMO_VISION_MODEL")
        or _config_value("mimo_model", "MIMO_MODEL")
        or "mimo-v2.5"
    )
    if mimo_api_key and mimo_base_url:
        fallback_result, fallback_attempt = _call_openai_vision_provider(
            provider="mimo_vl",
            api_key=mimo_api_key,
            base_url=mimo_base_url,
            model=mimo_model,
            page_b64=page_b64,
            timeout_seconds=timeout_seconds,
            default_headers={"api-key": mimo_api_key},
            fallback_from="qwen_vl",
        )
        attempts.append(fallback_attempt)
        if not _provider_failed(fallback_result):
            return _annotate_vision_result(
                fallback_result,
                provider="mimo_vl",
                model=mimo_model,
                timeout_seconds=timeout_seconds,
                elapsed_ms=fallback_attempt["elapsed_ms"],
                attempts=attempts,
                fallback_from="qwen_vl",
            )
        sdk_fallback_error = (
            f"OpenAI-compatible failed: {sdk_fallback_error}; "
            f"MiMo fallback failed: {fallback_result.get('error') or fallback_attempt.get('error_message')}"
        )

    if os.getenv("VISION_AI_ENABLE_DASHSCOPE_SDK_FALLBACK", "").lower() not in {"1", "true", "yes"}:
        return _annotate_vision_result(
            {
                "page_type": "unknown",
                "materials": [],
                "questions": [],
                "visuals": [],
                "warnings": ["visual_model_failed"],
                "error": sdk_fallback_error or "vision providers failed",
                "schema_validation": {"provider_attempts": attempts},
                "raw_model_result": {"error": sdk_fallback_error or "vision providers failed"},
            },
            provider="mimo_vl" if any(item.get("provider") == "mimo_vl" for item in attempts) else "qwen_vl",
            model=mimo_model if any(item.get("provider") == "mimo_vl" for item in attempts) else (model or "qwen-vl-max"),
            timeout_seconds=timeout_seconds,
            elapsed_ms=sum(int(item.get("elapsed_ms") or 0) for item in attempts),
            attempts=attempts,
            fallback_from="qwen_vl" if any(item.get("provider") == "mimo_vl" for item in attempts) else None,
        )

    dashscope.api_key = api_key
    sdk_started = time.perf_counter()
    try:
        record_ai_call("qwen_vl")
        response = _call_with_timeout(
            lambda: dashscope.MultiModalConversation.call(
                model=model or "qwen-vl-max",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"image": f"data:image/png;base64,{page_b64}"},
                            {"text": PAGE_PARSE_PROMPT},
                        ],
                    }
                ],
            ),
            timeout_seconds,
        )
        content = response.output.choices[0].message.content
        text = content[0].get("text") if isinstance(content, list) else str(content)
        raw = json.loads(_extract_json(text))
        normalized = _normalize_page_visual_result(raw)
        sdk_attempt = _vision_attempt_payload(
            provider="dashscope_sdk",
            model=model or "qwen-vl-max",
            timeout_seconds=timeout_seconds,
            started_at=sdk_started,
            status="failed" if _provider_failed(normalized) else "ok",
            error_type="model_result_failed" if _provider_failed(normalized) else None,
            error_message=normalized.get("error") if _provider_failed(normalized) else None,
            fallback_from="qwen_vl",
        )
        attempts.append(sdk_attempt)
        return _annotate_vision_result(
            normalized,
            provider="dashscope_sdk",
            model=model or "qwen-vl-max",
            timeout_seconds=timeout_seconds,
            elapsed_ms=sdk_attempt["elapsed_ms"],
            attempts=attempts,
            fallback_from="qwen_vl",
        )
    except Exception as exc:
        record_ai_call("qwen_vl", str(exc))
        message = str(exc)
        if sdk_fallback_error:
            message = f"OpenAI-compatible failed: {sdk_fallback_error}; DashScope SDK failed: {message}"
        sdk_attempt = _vision_attempt_payload(
            provider="dashscope_sdk",
            model=model or "qwen-vl-max",
            timeout_seconds=timeout_seconds,
            started_at=sdk_started,
            status="failed",
            error_type=type(exc).__name__,
            error_message=str(exc),
            fallback_from="qwen_vl",
        )
        attempts.append(sdk_attempt)
        return _annotate_vision_result(
            {
                "page_type": "unknown",
                "materials": [],
                "questions": [],
                "visuals": [],
                "warnings": ["visual_model_failed"],
                "error": message,
                "schema_validation": {"provider_attempts": attempts},
                "raw_model_result": {"error": message},
            },
            provider="qwen_vl",
            model=model or "qwen-vl-max",
            timeout_seconds=timeout_seconds,
            elapsed_ms=sum(int(item.get("elapsed_ms") or 0) for item in attempts),
            attempts=attempts,
        )


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
    page_analysis = _normalize_page_analysis(result.get("page_analysis"))
    semantic_questions = [_normalize_visual_question(item, include_semantic=True) for item in result.get("semantic_questions") or []]
    if not semantic_questions:
        fallback_questions = [
            _normalize_visual_question(item, include_semantic=True)
            for item in raw_questions
            if isinstance(item, dict)
        ]
        fallback_questions = [item for item in fallback_questions if item]
        if fallback_questions:
            semantic_questions = fallback_questions
            warnings.append("semantic_questions_missing_use_questions_fallback")
    visual_merge_candidates = _normalize_visual_merge_candidates(result.get("visual_merge_candidates"))
    page_level_risk_flags = _coerce_str_list(result.get("page_level_risk_flags")) or []
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
        "semantic_question_count": len(semantic_questions),
        "visual_merge_candidate_count": len(visual_merge_candidates),
        "page_analysis_questions_detected": (page_analysis.get("questions_detected") or 0),
    },
    "page_analysis": page_analysis,
    "semantic_questions": [item for item in semantic_questions if item],
    "visual_merge_candidates": visual_merge_candidates,
    "page_level_risk_flags": page_level_risk_flags,
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


def _normalize_visual_question(item: Any, *, include_semantic: bool = False) -> dict[str, Any] | None:
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
        "stem_complete": bool(item.get("stem_complete")) if item.get("stem_complete") is not None else None,
        "options_complete": bool(item.get("options_complete")) if item.get("options_complete") is not None else None,
    }
    if include_semantic:
        question.update(
            {
                "question_type": _normalize_text(item.get("question_type")) or "single",
                "pages": _coerce_pages(item.get("pages")) or [],
                "is_cross_page": bool(item.get("is_cross_page") or False),
                "options_bbox": _normalize_bbox(item.get("options_bbox")),
                "content_quality": _normalize_dict(item.get("content_quality"), "content_quality"),
                "question_quality": _normalize_dict(item.get("question_quality"), "question_quality"),
                "capture_plan": _normalize_dict(item.get("capture_plan"), "capture_plan"),
                "understanding": _normalize_dict(item.get("understanding"), "understanding"),
                "answer_suggestion": _normalize_dict(item.get("answer_suggestion"), "answer_suggestion"),
                "analysis_suggestion": _normalize_dict(item.get("analysis_suggestion"), "analysis_suggestion"),
                "ai_audit": _normalize_dict(item.get("ai_audit"), "ai_audit"),
                "visual_groups": _normalize_visual_groups(item.get("visual_groups") or []),
            }
        )
        visual_groups = question["visual_groups"]
        if visual_groups:
            question["visual_group_count"] = len(visual_groups)
    for option in options:
        key = f"option_{option['label'].lower()}"
        if not question.get(key):
            question[key] = option["text"]
    return question


def _normalize_page_analysis(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"page_no": None, "questions_detected": 0, "cross_page_needed": False, "page_level_risk_flags": []}
    return {
        "page_no": _safe_int(value.get("page_no")),
        "questions_detected": _safe_int(value.get("questions_detected")) or 0,
        "cross_page_needed": bool(value.get("cross_page_needed")),
        "page_level_risk_flags": _coerce_str_list(value.get("page_level_risk_flags")),
    }


def _normalize_visual_groups(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "group_id": str(item.get("group_id") or "").strip() or None,
                "type": str(item.get("type") or "image").strip() or "image",
                "member_blocks": _coerce_str_list(item.get("member_blocks")),
                "merged_bbox": _normalize_bbox(item.get("merged_bbox")),
                "title_bbox": _normalize_bbox(item.get("title_bbox")),
                "legend_bbox": _normalize_bbox(item.get("legend_bbox")),
                "table_header_bbox": _normalize_bbox(item.get("table_header_bbox")),
                "axis_bbox": _normalize_bbox(item.get("axis_bbox")),
                "notes_bbox": _normalize_bbox(item.get("notes_bbox")),
                "title_included": bool(item.get("title_included")),
                "legend_included": bool(item.get("legend_included")),
                "axis_included": bool(item.get("axis_included")),
                "table_header_included": bool(item.get("table_header_included")),
                "notes_included": bool(item.get("notes_included")),
                "is_fragmented_before_merge": bool(item.get("is_fragmented_before_merge")),
                "belongs_to_question": bool(item.get("belongs_to_question")),
                "link_reason": str(item.get("link_reason") or ""),
                "visual_summary": _normalize_text(item.get("visual_summary")),
                "key_values": _coerce_str_list(item.get("key_values")),
                "confidence": _safe_float(item.get("confidence")),
            }
        )
    return [item for item in normalized if item.get("merged_bbox")]


def _normalize_dict(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        if name == "capture_plan":
            return {
                "should_recrop": True,
                "crop_targets": [],
                "padding": 24,
                "must_include": ["chart_title", "axis_labels", "table_header"],
            }
        if name == "understanding":
            return {
                "question_intent": "",
                "required_visual_evidence": "",
                "can_answer_from_available_context": False,
                "missing_context": [],
            }
        if name == "ai_audit":
            return {"status": "skipped", "verdict": "需复核", "summary": "", "needs_review": True, "risk_flags": [], "review_reasons": []}
        return {
            "risk_flags": [],
            "review_reasons": [],
            "needs_review": True,
            "question_complete": False,
            "visual_context_complete": False,
            "stem_complete": False,
            "options_complete": False,
            "answer_derivable": False,
            "analysis_derivable": False,
            "duplicate_suspected": False,
        }
    return {str(k): v for k, v in value.items()}


def _normalize_visual_merge_candidates(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "group_id": str(item.get("group_id") or item.get("visual_group") or "").strip(),
                "candidate_blocks": _coerce_str_list(item.get("candidate_blocks") or item.get("members") or []),
                "reason": str(item.get("reason") or ""),
            }
        )
    return result


def _coerce_str_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        if value in (None, ""):
            return []
        return [str(value)]
    return [str(item).strip() for item in value if str(item).strip()]


def _coerce_pages(value: Any) -> list[int]:
    if not isinstance(value, (list, tuple)):
        return []
    pages: list[int] = []
    for item in value:
        page = _safe_int(item)
        if page:
            pages.append(page)
    return pages


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


def repair_question_structure(payload: dict[str, Any]) -> dict[str, Any]:
    fallback = _heuristic_repair_question(payload)
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
        prompt = REPAIR_QUESTION_PROMPT.replace(
            "{repair_json}",
            json.dumps(payload, ensure_ascii=False)[:16000],
        )
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=90.0)
        record_ai_call("question_repair")
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {"role": "system", "content": "你只返回 JSON，不返回 markdown 或解释。"},
                {"role": "user", "content": prompt},
            ],
        )
        result = json.loads(_extract_json(response.choices[0].message.content or "{}"))
        return _normalize_repair_question_result(result, fallback)
    except Exception as exc:
        record_ai_call("question_repair", str(exc))
        return {**fallback, "source": "heuristic_ai_failed", "warnings": fallback["warnings"] + [str(exc)]}


def _heuristic_repair_question(payload: dict[str, Any]) -> dict[str, Any]:
    question = payload.get("question") if isinstance(payload.get("question"), dict) else {}
    blacklist = _repair_blacklist(payload)
    content = str(question.get("content") or "")
    remove_texts: list[str] = []
    for text in blacklist:
        if text and text in content:
            content = content.replace(text, "")
            remove_texts.append(text)
    content = re.sub(r"资料分析题库[-—]夸夸刷", "", content).strip()
    options = question.get("options") if isinstance(question.get("options"), dict) else {}
    normalized_options = {
        key: str(options.get(key) or options.get(key.lower()) or "").strip()
        for key in ["A", "B", "C", "D"]
    }
    warnings = [str(item) for item in payload.get("warnings") or question.get("parse_warnings") or []]
    if any(not value for value in normalized_options.values()):
        warnings.append("options_missing")
    if re.search(r"资料分析题库|夸夸刷|第七章", content):
        warnings.append("header_footer_blacklist_hit")
    return {
        "content": content,
        "options": normalized_options,
        "visual_refs": question.get("image_refs") or [],
        "material_text": str(question.get("material") or ""),
        "remove_texts": remove_texts,
        "warnings": sorted(set(warnings)),
        "confidence": 0.55 if warnings else 0.78,
    }


def _repair_blacklist(payload: dict[str, Any]) -> list[str]:
    config = _AI_CONFIG.get()
    raw = config.get("header_footer_blacklist")
    values: list[str] = []
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                values.extend(str(item) for item in parsed)
        except json.JSONDecodeError:
            values.append(str(raw))
    values.extend(["资料分析题库-夸夸刷", "资料分析题库", "夸夸刷"])
    return list(dict.fromkeys(item.strip() for item in values if item.strip()))


def _normalize_repair_question_result(result: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return fallback
    raw_options = result.get("options") if isinstance(result.get("options"), dict) else {}
    confidence = result.get("confidence")
    try:
        numeric_confidence = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        numeric_confidence = float(fallback["confidence"])
    return {
        "content": str(result.get("content") or fallback["content"]),
        "options": {
            key: str(raw_options.get(key) or raw_options.get(key.lower()) or "")
            for key in ["A", "B", "C", "D"]
        },
        "visual_refs": result.get("visual_refs") if isinstance(result.get("visual_refs"), list) else [],
        "material_text": str(result.get("material_text") or ""),
        "remove_texts": [str(item) for item in result.get("remove_texts", []) if str(item).strip()],
        "warnings": [str(item) for item in result.get("warnings", []) if str(item).strip()],
        "confidence": numeric_confidence,
        "source": "ai_text_model",
    }


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
