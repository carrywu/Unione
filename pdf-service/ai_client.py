from __future__ import annotations

import json
import os
import hashlib
import queue
import re
import threading
import time
from datetime import datetime, timezone
import httpx
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

import dashscope
from openai import OpenAI
from monitor import record_ai_call, record_provider_attempt

_AI_CONFIG: ContextVar[dict[str, str]] = ContextVar("AI_CONFIG", default={})
_VISUAL_CALL_CONTEXT: ContextVar[dict[str, Any]] = ContextVar(
    "VISUAL_CALL_CONTEXT",
    default={},
)


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


@contextmanager
def use_visual_call_context(context: dict[str, Any] | None):
    token = _VISUAL_CALL_CONTEXT.set(context or {})
    try:
        yield
    finally:
        _VISUAL_CALL_CONTEXT.reset(token)


def _config_value(key: str, env_key: str | None = None, default: str | None = None) -> str | None:
    config = _AI_CONFIG.get()
    value = config.get(key)
    if value:
        return value
    if env_key:
        return os.getenv(env_key) or default
    return default


def current_config_value(
    key: str,
    env_key: str | None = None,
    default: str | None = None,
) -> str | None:
    return _config_value(key, env_key, default)


def current_config_present(key: str, env_key: str | None = None) -> bool:
    value = _config_value(key, env_key)
    return bool(str(value or "").strip())


def current_visual_call_context() -> dict[str, Any]:
    return _VISUAL_CALL_CONTEXT.get() or {}


DEFAULT_DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MIMO_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
DEFAULT_ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_ARK_RESPONSES_PATH = "/responses"
DEFAULT_QWEN_VISION_MODEL = "qwen3-vl-plus"
DEFAULT_MIMO_VISION_MODEL = "mimo-v2.5"
DEFAULT_ARK_VISION_MODEL = "doubao-seed-1-6-vision-250815"
VISION_PROVIDER_IDS = ("volcengine_ark_vl", "qwen_vl", "mimo_vl")
PREFERRED_VISION_PROVIDER_ORDER = ("qwen_vl", "volcengine_ark_vl", "mimo_vl")

DEFAULT_VISION_TIMEOUT_SECONDS = 180.0
DEFAULT_VISION_SOFT_TIMEOUT_SECONDS = 10.0
DEFAULT_VISION_PROVIDER_CACHE_TTL_SECONDS = 3600.0

_VISION_PROVIDER_RUNTIME_LOCK = threading.Lock()
_VISION_PROVIDER_STATE: dict[str, dict[str, Any]] = {
    provider: {
        "cooldown_until": 0.0,
        "last_error_type": None,
        "consecutive_timeouts": 0,
        "config_signature": None,
    }
    for provider in VISION_PROVIDER_IDS
}
_VISION_PROVIDER_CACHE: dict[str, dict[str, Any]] = {}


def _safe_positive_timeout(value: str | None, default: float) -> float:
    try:
        timeout = float(value or 0)
    except (TypeError, ValueError):
        return default
    return timeout if timeout > 0 else default


def _vision_timeout_seconds(default: float = DEFAULT_VISION_TIMEOUT_SECONDS) -> float:
    return _safe_positive_timeout(
        _config_value("vision_ai_timeout_seconds", "VISION_AI_TIMEOUT_SECONDS")
        or _config_value(
            "pdf_visual_openai_timeout_seconds",
            "PDF_VISUAL_OPENAI_TIMEOUT_SECONDS",
        )
        or _config_value(
            "pdf_visual_page_timeout_seconds",
            "PDF_VISUAL_PAGE_TIMEOUT_SECONDS",
        ),
        default,
    )


def _vision_provider_timeout_seconds(default: float = DEFAULT_VISION_TIMEOUT_SECONDS) -> float:
    return _safe_positive_timeout(
        _config_value(
            "vision_ai_provider_timeout_seconds",
            "VISION_AI_PROVIDER_TIMEOUT_SECONDS",
        )
        or _config_value(
            "pdf_visual_provider_timeout_seconds",
            "PDF_VISUAL_PROVIDER_TIMEOUT_SECONDS",
        ),
        default,
    )


def _vision_soft_timeout_seconds(default: float = DEFAULT_VISION_SOFT_TIMEOUT_SECONDS) -> float:
    raw = _config_value(
        "vision_ai_soft_timeout_seconds",
        "VISION_AI_SOFT_TIMEOUT_SECONDS",
    )
    if raw is None:
        derived = min(12.0, max(8.0, _vision_provider_timeout_seconds() * 0.06))
        return derived
    return _safe_positive_timeout(raw, default)


def _vision_provider_cache_ttl_seconds(default: float = DEFAULT_VISION_PROVIDER_CACHE_TTL_SECONDS) -> float:
    return _safe_positive_timeout(
        _config_value(
            "vision_ai_provider_cache_ttl_seconds",
            "VISION_AI_PROVIDER_CACHE_TTL_SECONDS",
        ),
        default,
    )


def _first_config_value(
    *pairs: tuple[str, str | None],
    default: str | None = None,
) -> str | None:
    for key, env_key in pairs:
        value = _config_value(key, env_key)
        if str(value or "").strip():
            return str(value).strip()
    return default


def _normalize_openai_base_url(
    *,
    base_url: str | None = None,
    chat_completions_url: str | None = None,
    default_base_url: str | None = None,
) -> str:
    candidate = str(chat_completions_url or base_url or default_base_url or "").strip()
    if not candidate:
        return ""
    normalized = candidate.rstrip("/")
    if normalized.lower().endswith("/chat/completions"):
        normalized = normalized[: -len("/chat/completions")]
    if normalized.lower().endswith("/responses"):
        normalized = normalized[: -len("/responses")]
    return normalized.rstrip("/")


def _normalize_path(path: str | None, default: str) -> str:
    value = str(path or "").strip()
    if not value:
        return default
    normalized = value if value.startswith("/") else f"/{value}"
    return normalized.rstrip("/") or default


def _mask_secret(secret: str | None) -> str | None:
    value = str(secret or "").strip()
    if not value:
        return None
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}***{value[-4:]}"


def _vision_provider_error_type(message: str | None, raw_type: str | None = None) -> str:
    lowered = str(message or "").lower()
    if "response_parse_failed" in lowered:
        return "response_parse_failed"
    if raw_type == "TimeoutError" or "timeout" in lowered or "timed out" in lowered:
        return "timeout"
    if (
        "429" in lowered
        or "quota" in lowered
        or "rate limit" in lowered
        or "too many requests" in lowered
    ):
        return "quota_exhausted"
    if (
        "401" in lowered
        or "403" in lowered
        or "unauthorized" in lowered
        or "forbidden" in lowered
        or "authentication" in lowered
        or "invalid api key" in lowered
        or "permission" in lowered
    ):
        return "auth_error"
    if (
        "modelnotopen" in lowered
        or "not activated the model" in lowered
        or "activate the model service" in lowered
        or "model service" in lowered and "not open" in lowered
    ):
        return "model_not_open"
    if (
        "model_not_found" in lowered
        or "model not found" in lowered
        or "endpoint not found" in lowered
        or "does not exist" in lowered
    ):
        return "model_not_found"
    if (
        "modality" in lowered
        or "image input is not supported" in lowered
        or "image_url" in lowered and "unsupported" in lowered
        or "vision" in lowered and "not support" in lowered
    ):
        return "modality_not_supported"
    if "400" in lowered or "bad request" in lowered or "invalid_request_error" in lowered:
        return "bad_request"
    if any(code in lowered for code in ["500", "502", "503", "504", "server error", "upstream"]):
        return "server_error"
    if raw_type == "missing_api_key":
        return "auth_missing"
    if raw_type == "model_missing":
        return "model_missing"
    if raw_type == "base_url_missing":
        return "base_url_missing"
    return "unknown_error"


def _resolve_qwen_vl_config() -> dict[str, Any]:
    api_key = _first_config_value(("dashscope_api_key", "DASHSCOPE_API_KEY"))
    base_url = _normalize_openai_base_url(
        base_url=_first_config_value(
            ("dashscope_base_url", "DASHSCOPE_BASE_URL"),
            default=DEFAULT_DASHSCOPE_BASE_URL,
        ),
        chat_completions_url=_first_config_value(
            ("dashscope_chat_completions_url", "DASHSCOPE_CHAT_COMPLETIONS_URL"),
        ),
        default_base_url=DEFAULT_DASHSCOPE_BASE_URL,
    )
    model = _first_config_value(
        ("visual_model", "AI_VISUAL_MODEL"),
        default=DEFAULT_QWEN_VISION_MODEL,
    )
    missing: list[str] = []
    if not api_key:
        missing.append("missing_api_key")
    if not base_url:
        missing.append("base_url_missing")
    if not model:
        missing.append("model_missing")
    return {
        "provider": "qwen_vl",
        "api_key": api_key,
        "key_masked": _mask_secret(api_key),
        "base_url": base_url,
        "model": model or DEFAULT_QWEN_VISION_MODEL,
        "default_headers": None,
        "modalities": {"input": ["text", "image"], "output": ["text"]},
        "supports_chat_completions": True,
        "configured": not missing,
        "missing": missing,
    }


def _resolve_mimo_vl_config() -> dict[str, Any]:
    api_key = _first_config_value(("mimo_api_key", "MIMO_API_KEY"))
    base_url = _normalize_openai_base_url(
        base_url=_first_config_value(
            ("mimo_base_url", "MIMO_BASE_URL"),
            default=DEFAULT_MIMO_BASE_URL,
        ),
        chat_completions_url=_first_config_value(
            ("mimo_chat_completions_url", "MIMO_CHAT_COMPLETIONS_URL"),
        ),
        default_base_url=DEFAULT_MIMO_BASE_URL,
    )
    model = (
        _first_config_value(("mimo_vision_model", "MIMO_VISION_MODEL"))
        or _first_config_value(("mimo_model", "MIMO_MODEL"))
        or DEFAULT_MIMO_VISION_MODEL
    )
    missing: list[str] = []
    if not api_key:
        missing.append("missing_api_key")
    if not base_url:
        missing.append("base_url_missing")
    if not model:
        missing.append("model_missing")
    return {
        "provider": "mimo_vl",
        "api_key": api_key,
        "key_masked": _mask_secret(api_key),
        "base_url": base_url,
        "model": model or DEFAULT_MIMO_VISION_MODEL,
        "default_headers": {"api-key": api_key} if api_key else None,
        "modalities": {"input": ["text", "image"], "output": ["text"]},
        "supports_chat_completions": True,
        "configured": not missing,
        "missing": missing,
    }


def _resolve_ark_vl_config() -> dict[str, Any]:
    api_key = _first_config_value(
        ("ark_api_key", "ARK_API_KEY"),
        ("volcengine_ark_api_key", "VOLCENGINE_ARK_API_KEY"),
        ("volc_ark_api_key", "VOLC_ARK_API_KEY"),
    )
    base_url = _normalize_openai_base_url(
        base_url=_first_config_value(
            ("ark_base_url", "ARK_BASE_URL"),
            ("volcengine_ark_base_url", "VOLCENGINE_ARK_BASE_URL"),
        ),
        chat_completions_url=_first_config_value(
            ("ark_chat_completions_url", "ARK_CHAT_COMPLETIONS_URL"),
            ("volcengine_ark_chat_completions_url", "VOLCENGINE_ARK_CHAT_COMPLETIONS_URL"),
        ),
        default_base_url=DEFAULT_ARK_BASE_URL,
    )
    api_mode = (
        _first_config_value(
            ("ark_api_mode", "ARK_API_MODE"),
            ("volcengine_ark_api_mode", "VOLCENGINE_ARK_API_MODE"),
            default="responses",
        )
        or "responses"
    ).strip().lower()
    responses_path = _normalize_path(
        _first_config_value(
            ("ark_responses_path", "ARK_RESPONSES_PATH"),
            ("volcengine_ark_responses_path", "VOLCENGINE_ARK_RESPONSES_PATH"),
            default=DEFAULT_ARK_RESPONSES_PATH,
        ),
        DEFAULT_ARK_RESPONSES_PATH,
    )
    candidate_pairs = [
        ("ark_endpoint_id", "ARK_ENDPOINT_ID"),
        ("volcengine_ark_endpoint_id", "VOLCENGINE_ARK_ENDPOINT_ID"),
        ("ark_vision_model", "ARK_VISION_MODEL"),
        ("volcengine_ark_vision_model", "VOLCENGINE_ARK_VISION_MODEL"),
    ]
    candidate_models: list[dict[str, str]] = []
    seen_models: set[str] = set()
    for key, env_key in candidate_pairs:
        value = str(_config_value(key, env_key) or "").strip()
        if not value or value in seen_models:
            continue
        candidate_models.append(
            {
                "model": value,
                "type": "endpoint_id" if "endpoint_id" in key else "model_name",
                "source": env_key or key,
            }
        )
        seen_models.add(value)
    if not candidate_models and DEFAULT_ARK_VISION_MODEL not in seen_models:
        candidate_models.append(
            {
                "model": DEFAULT_ARK_VISION_MODEL,
                "type": "model_name",
                "source": "DEFAULT_ARK_VISION_MODEL",
            }
        )
    model = candidate_models[0]["model"] if candidate_models else None
    missing: list[str] = []
    if not api_key:
        missing.append("missing_api_key")
    if not base_url:
        missing.append("base_url_missing")
    if not candidate_models:
        missing.append("model_missing")
    return {
        "provider": "volcengine_ark_vl",
        "api_key": api_key,
        "key_masked": _mask_secret(api_key),
        "base_url": base_url,
        "model": model,
        "model_candidates": candidate_models,
        "successful_model": None,
        "api_mode": api_mode,
        "endpoint": responses_path,
        "default_headers": None,
        "modalities": {"input": ["text", "image"], "output": ["text"]},
        "supports_chat_completions": False,
        "supports_responses": api_mode == "responses",
        "configured": not missing,
        "missing": missing,
    }


def resolve_vision_provider_config(provider: str) -> dict[str, Any]:
    if provider == "qwen_vl":
        return _resolve_qwen_vl_config()
    if provider == "mimo_vl":
        return _resolve_mimo_vl_config()
    if provider == "volcengine_ark_vl":
        return _resolve_ark_vl_config()
    raise KeyError(f"unknown vision provider: {provider}")


def vision_provider_configs() -> dict[str, dict[str, Any]]:
    return {
        provider: resolve_vision_provider_config(provider)
        for provider in VISION_PROVIDER_IDS
    }


def vision_provider_order() -> list[str]:
    raw = (
        _first_config_value(("vision_ai_provider_order", "VISION_AI_PROVIDER_ORDER"))
        or _first_config_value(("pdf_visual_provider_order", "PDF_VISUAL_PROVIDER_ORDER"))
    )
    if raw:
        ordered = [
            item.strip()
            for item in str(raw).split(",")
            if item.strip() in VISION_PROVIDER_IDS
        ]
        if ordered:
            return list(dict.fromkeys(ordered))
    return list(VISION_PROVIDER_IDS)


def configured_vision_provider_order() -> list[str]:
    configs = vision_provider_configs()
    return [
        provider
        for provider in vision_provider_order()
        if configs.get(provider, {}).get("configured")
    ]


def ranked_vision_provider_order() -> list[str]:
    return vision_provider_order()


def reset_vision_runtime_state() -> None:
    with _VISION_PROVIDER_RUNTIME_LOCK:
        for provider in VISION_PROVIDER_IDS:
            state = _VISION_PROVIDER_STATE.setdefault(
                provider,
                {
                    "cooldown_until": 0.0,
                    "last_error_type": None,
                    "consecutive_timeouts": 0,
                    "config_signature": None,
                },
            )
            state["cooldown_until"] = 0.0
            state["last_error_type"] = None
            state["consecutive_timeouts"] = 0
            state["config_signature"] = None
        _VISION_PROVIDER_CACHE.clear()


def _provider_config_signature(provider_config: dict[str, Any]) -> str:
    payload = {
        "provider": provider_config.get("provider"),
        "base_url": provider_config.get("base_url"),
        "model": provider_config.get("model"),
        "model_candidates": provider_config.get("model_candidates"),
        "api_mode": provider_config.get("api_mode"),
        "endpoint": provider_config.get("endpoint"),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _refresh_provider_runtime_state(configs: dict[str, dict[str, Any]]) -> None:
    with _VISION_PROVIDER_RUNTIME_LOCK:
        for provider, provider_config in configs.items():
            state = _VISION_PROVIDER_STATE.setdefault(
                provider,
                {
                    "cooldown_until": 0.0,
                    "last_error_type": None,
                    "consecutive_timeouts": 0,
                    "config_signature": None,
                },
            )
            signature = _provider_config_signature(provider_config)
            if state.get("config_signature") != signature:
                state["cooldown_until"] = 0.0
                state["last_error_type"] = None
                state["consecutive_timeouts"] = 0
                state["config_signature"] = signature


def _provider_in_cooldown(provider: str) -> bool:
    with _VISION_PROVIDER_RUNTIME_LOCK:
        state = _VISION_PROVIDER_STATE.setdefault(provider, {})
        return float(state.get("cooldown_until") or 0.0) > time.time()


def _provider_cooldown_attempt(
    *,
    provider_config: dict[str, Any],
    timeout_seconds: float,
    fallback_from: str | None = None,
) -> dict[str, Any]:
    return _vision_attempt_payload(
        provider=provider_config["provider"],
        model=str(provider_config.get("model") or ""),
        timeout_seconds=timeout_seconds,
        started_at=time.perf_counter(),
        status="failed",
        error_type="cooldown_active",
        error_message=f"{provider_config['provider']} cooldown_active",
        fallback_from=fallback_from,
        fallback_reason="provider_in_cooldown",
    )


def _provider_cache_key(provider: str, provider_config: dict[str, Any], page_b64: str) -> str:
    input_sha = hashlib.sha256(page_b64.encode("utf-8")).hexdigest()
    prompt_sha = hashlib.sha256(PAGE_PARSE_PROMPT.encode("utf-8")).hexdigest()
    model_key = provider_config.get("model") or provider_config.get("model_candidates") or ""
    payload = {
        "provider": provider,
        "model": model_key,
        "input_sha": input_sha,
        "prompt_sha": prompt_sha,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _provider_cache_get(provider: str, provider_config: dict[str, Any], page_b64: str) -> dict[str, Any] | None:
    key = _provider_cache_key(provider, provider_config, page_b64)
    with _VISION_PROVIDER_RUNTIME_LOCK:
        entry = _VISION_PROVIDER_CACHE.get(key)
        if not entry:
            return None
        if float(entry.get("expires_at") or 0.0) <= time.time():
            _VISION_PROVIDER_CACHE.pop(key, None)
            return None
        value = entry.get("result")
    return json.loads(json.dumps(value)) if isinstance(value, dict) else None


def _provider_cache_put(provider: str, provider_config: dict[str, Any], page_b64: str, result: dict[str, Any]) -> None:
    key = _provider_cache_key(provider, provider_config, page_b64)
    with _VISION_PROVIDER_RUNTIME_LOCK:
        _VISION_PROVIDER_CACHE[key] = {
            "expires_at": time.time() + _vision_provider_cache_ttl_seconds(),
            "result": json.loads(json.dumps(result)),
        }


def _record_provider_outcome(provider: str, attempt: dict[str, Any]) -> None:
    error_type = str(attempt.get("error_type") or "").strip()
    status = str(attempt.get("status") or "").strip().lower()
    with _VISION_PROVIDER_RUNTIME_LOCK:
        state = _VISION_PROVIDER_STATE.setdefault(
            provider,
            {
                "cooldown_until": 0.0,
                "last_error_type": None,
                "consecutive_timeouts": 0,
                "config_signature": None,
            },
        )
        if status == "ok":
            state["last_error_type"] = None
            state["consecutive_timeouts"] = 0
            if provider != "volcengine_ark_vl":
                state["cooldown_until"] = 0.0
            return
        state["last_error_type"] = error_type or None
        if error_type == "timeout":
            state["consecutive_timeouts"] = int(state.get("consecutive_timeouts") or 0) + 1
            if provider == "qwen_vl" and state["consecutive_timeouts"] >= 3:
                state["cooldown_until"] = time.time() + 600.0
        else:
            state["consecutive_timeouts"] = 0
        if provider == "mimo_vl" and error_type == "quota_exhausted":
            state["cooldown_until"] = time.time() + 3600.0
        elif provider == "volcengine_ark_vl" and error_type in {"auth_error", "model_not_open"}:
            state["cooldown_until"] = time.time() + 86400.0
        elif provider == "volcengine_ark_vl" and error_type == "quota_exhausted":
            state["cooldown_until"] = time.time() + 1800.0


def _dashscope_sdk_fallback_enabled() -> bool:
    raw = (os.getenv("VISION_AI_ENABLE_DASHSCOPE_SDK_FALLBACK") or "").strip().lower()
    if not raw:
        return True
    return raw not in {"0", "false", "no", "off"}


def dashscope_sdk_page_fallback_enabled(base_url: str | None = None) -> bool:
    if not _dashscope_sdk_fallback_enabled():
        return False
    resolved = base_url
    if resolved is None:
        resolved = _config_value(
            "dashscope_base_url",
            "DASHSCOPE_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
    normalized = str(resolved or "").strip().lower()
    if not normalized:
        return True
    return "dashscope.aliyuncs.com/compatible-mode" not in normalized


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


def _data_url_for_page_b64(page_b64: str, mime_type: str = "image/png") -> str:
    return f"data:{mime_type};base64,{page_b64}"


def _ark_responses_input(prompt: str, image_url: str) -> list[dict[str, Any]]:
    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "input_image",
                    "image_url": image_url,
                },
                {
                    "type": "input_text",
                    "text": prompt,
                },
            ],
        }
    ]


def _object_get(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _response_to_jsonable(response: Any) -> Any:
    if isinstance(response, (dict, list, str, int, float, bool)) or response is None:
        return response
    for method_name in ("model_dump", "to_dict", "dict"):
        method = getattr(response, method_name, None)
        if callable(method):
            try:
                return method(mode="json") if method_name == "model_dump" else method()
            except TypeError:
                return method()
    return {"repr": repr(response)}


def _response_summary(response: Any, limit: int = 400) -> dict[str, Any]:
    jsonable = _response_to_jsonable(response)
    text = json.dumps(jsonable, ensure_ascii=False) if not isinstance(jsonable, str) else jsonable
    output_text = _responses_output_text(response)
    return {
        "output_text_preview": (output_text or "")[:limit],
        "response_preview": text if len(text) <= limit else text[:limit] + "...",
    }


def _responses_output_text(response: Any) -> str | None:
    direct_text = _object_get(response, "output_text")
    if isinstance(direct_text, str) and direct_text.strip():
        return direct_text.strip()

    output = _object_get(response, "output") or []
    texts: list[str] = []
    for item in output if isinstance(output, list) else []:
        contents = _object_get(item, "content") or []
        for content in contents if isinstance(contents, list) else []:
            text_value = _object_get(content, "text")
            if isinstance(text_value, str) and text_value.strip():
                texts.append(text_value.strip())
                continue
            nested_value = _object_get(text_value, "value")
            if isinstance(nested_value, str) and nested_value.strip():
                texts.append(nested_value.strip())
    if texts:
        return "\n".join(texts)
    return None


def _ark_responses_request(
    *,
    api_key: str,
    base_url: str,
    model: str,
    input_payload: list[dict[str, Any]],
    timeout: float | None = None,
    responses_path: str = DEFAULT_ARK_RESPONSES_PATH,
) -> Any:
    url = f"{base_url.rstrip('/')}{_normalize_path(responses_path, DEFAULT_ARK_RESPONSES_PATH)}"
    visual_timeout = _safe_positive_timeout(
        os.getenv("PDF_VISUAL_OPENAI_TIMEOUT_SECONDS")
        or os.getenv("VISION_AI_TIMEOUT_SECONDS")
        or os.getenv("PDF_VISUAL_PAGE_TIMEOUT_SECONDS"),
        float(timeout or DEFAULT_VISION_TIMEOUT_SECONDS),
    )
    try:
        with httpx.Client(timeout=httpx.Timeout(visual_timeout), trust_env=False) as client:
            response = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "input": input_payload,
                },
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        message = exc.response.text if exc.response is not None else str(exc)
        raise RuntimeError(f"http_status_{exc.response.status_code if exc.response else 'unknown'}: {message}") from exc


def _ark_responses_text(
    *,
    api_key: str,
    base_url: str,
    model: str,
    prompt: str,
    image_url: str,
    timeout: float | None = None,
    responses_path: str = DEFAULT_ARK_RESPONSES_PATH,
) -> tuple[str, dict[str, Any]]:
    response = _ark_responses_request(
        api_key=api_key,
        base_url=base_url,
        model=model,
        input_payload=_ark_responses_input(prompt, image_url),
        timeout=timeout,
        responses_path=responses_path,
    )
    output_text = _responses_output_text(response)
    summary = _response_summary(response)
    if not output_text:
        raise RuntimeError(f"response_parse_failed: no output_text; {summary.get('response_preview') or 'empty_response'}")
    return output_text, summary


def _ark_responses_json(
    *,
    api_key: str,
    base_url: str,
    model: str,
    prompt: str,
    image_url: str,
    timeout: float | None = None,
    responses_path: str = DEFAULT_ARK_RESPONSES_PATH,
) -> tuple[Any, dict[str, Any]]:
    output_text, summary = _ark_responses_text(
        api_key=api_key,
        base_url=base_url,
        model=model,
        prompt=prompt,
        image_url=image_url,
        timeout=timeout,
        responses_path=responses_path,
    )
    try:
        return json.loads(_extract_json(output_text)), summary
    except Exception as exc:
        raise RuntimeError(
            f"response_parse_failed: invalid_json: {exc}; output_text={output_text[:240]}"
        ) from exc


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
    fallback_reason: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    visual_context = current_visual_call_context()
    finished_at = datetime.now(timezone.utc)
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    payload = {
        "taskId": str(
            visual_context.get("task_id")
            or current_config_value("parse_task_id")
            or ""
        )
        or None,
        "pageNo": visual_context.get("page_no"),
        "provider": provider,
        "model": model,
        "timeout_seconds": timeout_seconds,
        "elapsed_ms": elapsed_ms,
        "durationMs": elapsed_ms,
        "status": status,
        "error_type": error_type,
        "errorType": error_type,
        "error_message": error_message,
        "startedAt": datetime.fromtimestamp(
            finished_at.timestamp() - (elapsed_ms / 1000),
            timezone.utc,
        ).isoformat(),
        "finishedAt": finished_at.isoformat(),
        "fallback_from": fallback_from,
        "fallbackReason": fallback_reason
        or (error_type if fallback_from else None)
        or ("fallback_from_previous_provider" if fallback_from else None),
    }
    if extra:
        payload.update(extra)
    record_provider_attempt(payload)
    return payload


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


def _page_timeout_result_with_attempts(
    *,
    page_started: float,
    page_timeout_seconds: float,
    attempts: list[dict[str, Any]],
    fallback_provider: str,
    fallback_model: str,
    fallback_from: str | None = None,
) -> dict[str, Any]:
    timeout_message = f"page_visual_timeout_after_{page_timeout_seconds:.1f}s"
    provider = attempts[-1]["provider"] if attempts else fallback_provider
    model = attempts[-1]["model"] if attempts else fallback_model
    return _annotate_vision_result(
        {
            "page_type": "unknown",
            "materials": [],
            "questions": [],
            "visuals": [],
            "warnings": ["vision_page_timeout"],
            "error": timeout_message,
            "schema_validation": {
                "timeout_seconds": page_timeout_seconds,
                "provider_attempts": attempts,
            },
            "raw_model_result": {"error": "vision_page_timeout"},
        },
        provider=provider,
        model=model,
        timeout_seconds=page_timeout_seconds,
        elapsed_ms=int((time.perf_counter() - page_started) * 1000),
        attempts=attempts,
        fallback_from=fallback_from,
    )


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
        error_message = str(exc)
        attempt = _vision_attempt_payload(
            provider=provider,
            model=model,
            timeout_seconds=timeout_seconds,
            started_at=started,
            status="failed",
            error_type=_vision_provider_error_type(error_message, type(exc).__name__),
            error_message=error_message,
            fallback_from=fallback_from,
        )
        return {
            "page_type": "unknown",
            "materials": [],
            "questions": [],
            "visuals": [],
            "warnings": ["visual_model_failed"],
            "error": error_message,
            "schema_validation": {"exception": error_message},
            "raw_model_result": {"error": error_message, "provider": provider, "model": model},
        }, attempt


def _call_ark_vision_provider(
    *,
    provider: str,
    api_key: str,
    base_url: str,
    model_candidates: list[dict[str, str]],
    page_b64: str,
    timeout_seconds: float,
    responses_path: str,
    fallback_from: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    started = time.perf_counter()
    image_url = _data_url_for_page_b64(page_b64)
    candidate_attempts: list[dict[str, Any]] = []
    last_failure_result: dict[str, Any] | None = None
    last_error_type: str | None = None
    last_error_message: str | None = None

    for candidate in model_candidates:
        model = candidate.get("model") or ""
        model_type = candidate.get("type") or "model_name"
        if not model:
            continue
        record_ai_call(provider)
        candidate_started = time.perf_counter()
        try:
            raw, response_summary = _call_with_timeout(
                lambda: _ark_responses_json(
                    api_key=api_key,
                    base_url=base_url,
                    model=model,
                    prompt=PAGE_PARSE_PROMPT,
                    image_url=image_url,
                    timeout=timeout_seconds,
                    responses_path=responses_path,
                ),
                timeout_seconds,
            )
            normalized = _normalize_page_visual_result(raw)
            status = "failed" if _provider_failed(normalized) else "ok"
            candidate_attempts.append(
                {
                    "model": model,
                    "type": model_type,
                    "status": status,
                    "elapsed_ms": int((time.perf_counter() - candidate_started) * 1000),
                    "error_type": "model_result_failed" if status == "failed" else None,
                    "error_message": normalized.get("error") if status == "failed" else None,
                    "response_summary": response_summary,
                }
            )
            if status == "ok":
                attempt = _vision_attempt_payload(
                    provider=provider,
                    model=model,
                    timeout_seconds=timeout_seconds,
                    started_at=started,
                    status="ok",
                    fallback_from=fallback_from,
                    extra={
                        "api_mode": "responses",
                        "endpoint": responses_path,
                        "model_type": model_type,
                        "candidate_attempts": candidate_attempts,
                        "response_summary": response_summary,
                    },
                )
                return normalized, attempt
            record_ai_call(provider, str(normalized.get("error") or "model_result_failed"))
            last_failure_result = normalized
            last_error_type = "model_result_failed"
            last_error_message = str(normalized.get("error") or "model_result_failed")
        except Exception as exc:
            record_ai_call(provider, str(exc))
            last_error_message = str(exc)
            last_error_type = _vision_provider_error_type(last_error_message, type(exc).__name__)
            candidate_attempts.append(
                {
                    "model": model,
                    "type": model_type,
                    "status": "failed",
                    "elapsed_ms": int((time.perf_counter() - candidate_started) * 1000),
                    "error_type": last_error_type,
                    "error_message": last_error_message,
                }
            )

    final_model = candidate_attempts[-1]["model"] if candidate_attempts else ""
    attempt = _vision_attempt_payload(
        provider=provider,
        model=final_model,
        timeout_seconds=timeout_seconds,
        started_at=started,
        status="failed",
        error_type=last_error_type or "provider_not_configured",
        error_message=last_error_message or "volcengine_ark_vl failed",
        fallback_from=fallback_from,
        extra={
            "api_mode": "responses",
            "endpoint": responses_path,
            "candidate_attempts": candidate_attempts,
        },
    )
    if last_failure_result is not None:
        return last_failure_result, attempt
    return {
        "page_type": "unknown",
        "materials": [],
        "questions": [],
        "visuals": [],
        "warnings": ["visual_model_failed"],
        "error": last_error_message or "volcengine_ark_vl failed",
        "schema_validation": {"exception": last_error_message or "volcengine_ark_vl failed"},
        "raw_model_result": {
            "error": last_error_message or "volcengine_ark_vl failed",
            "provider": provider,
            "model": final_model,
            "candidate_attempts": candidate_attempts,
        },
    }, attempt


def _provider_missing_attempt(
    *,
    provider_config: dict[str, Any],
    timeout_seconds: float,
    fallback_from: str | None = None,
) -> dict[str, Any]:
    missing = list(provider_config.get("missing") or [])
    error_type = missing[0] if missing else "provider_not_configured"
    message_map = {
        "missing_api_key": f"{provider_config['provider']} API key not configured",
        "base_url_missing": f"{provider_config['provider']} base_url not configured",
        "model_missing": f"{provider_config['provider']} model_or_endpoint not configured",
    }
    return _vision_attempt_payload(
        provider=provider_config["provider"],
        model=str(provider_config.get("model") or ""),
        timeout_seconds=timeout_seconds,
        started_at=time.perf_counter(),
        status="failed",
        error_type=_vision_provider_error_type(message_map.get(error_type), error_type),
        error_message=message_map.get(
            error_type, f"{provider_config['provider']} not configured"
        ),
        fallback_from=fallback_from,
        fallback_reason="provider_not_configured",
    )


def _provider_attempt_failure_summary(attempts: list[dict[str, Any]]) -> str:
    failures = []
    for attempt in attempts:
        if str(attempt.get("status") or "").lower() == "ok":
            continue
        provider = str(attempt.get("provider") or "provider")
        message = str(attempt.get("error_message") or attempt.get("error_type") or "failed").strip()
        failures.append(f"{provider}: {message}")
    return "; ".join(failures)


def _call_vision_provider_with_cache(
    *,
    provider: str,
    provider_config: dict[str, Any],
    page_b64: str,
    timeout_seconds: float,
    fallback_from: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    cached = _provider_cache_get(provider, provider_config, page_b64)
    if isinstance(cached, dict):
        model = str(
            cached.get("_vision_model")
            or provider_config.get("model")
            or provider
        )
        attempt = _vision_attempt_payload(
            provider=provider,
            model=model,
            timeout_seconds=timeout_seconds,
            started_at=time.perf_counter(),
            status="ok" if not _provider_failed(cached) else "failed",
            error_type="cache_hit_failed" if _provider_failed(cached) else None,
            error_message=cached.get("error") if _provider_failed(cached) else None,
            fallback_from=fallback_from,
            extra={"cache_hit": True},
        )
        return cached, attempt

    if provider == "volcengine_ark_vl":
        result, attempt = _call_ark_vision_provider(
            provider=provider,
            api_key=provider_config["api_key"],
            base_url=provider_config["base_url"],
            model_candidates=list(provider_config.get("model_candidates") or []),
            page_b64=page_b64,
            timeout_seconds=timeout_seconds,
            responses_path=str(provider_config.get("endpoint") or DEFAULT_ARK_RESPONSES_PATH),
            fallback_from=fallback_from,
        )
    else:
        result, attempt = _call_openai_vision_provider(
            provider=provider,
            api_key=provider_config["api_key"],
            base_url=provider_config["base_url"],
            model=provider_config["model"],
            page_b64=page_b64,
            timeout_seconds=timeout_seconds,
            default_headers=provider_config.get("default_headers"),
            fallback_from=fallback_from,
        )
    _record_provider_outcome(provider, attempt)
    if not _provider_failed(result):
        _provider_cache_put(provider, provider_config, page_b64, result)
    return result, attempt


def _start_provider_call(
    *,
    provider: str,
    provider_config: dict[str, Any],
    page_b64: str,
    timeout_seconds: float,
    fallback_from: str | None = None,
) -> tuple[threading.Thread, queue.Queue[Any]]:
    result_queue: queue.Queue[Any] = queue.Queue(maxsize=1)

    def _runner() -> None:
        try:
            result_queue.put(
                _call_vision_provider_with_cache(
                    provider=provider,
                    provider_config=provider_config,
                    page_b64=page_b64,
                    timeout_seconds=timeout_seconds,
                    fallback_from=fallback_from,
                )
            )
        except BaseException as exc:  # pragma: no cover - defensive wrapper
            result_queue.put(
                (
                    failed_result := {
                        "page_type": "unknown",
                        "materials": [],
                        "questions": [],
                        "visuals": [],
                        "warnings": ["visual_model_failed"],
                        "error": str(exc),
                        "schema_validation": {"exception": str(exc)},
                        "raw_model_result": {"error": str(exc)},
                    },
                    _vision_attempt_payload(
                        provider=provider,
                        model=str(provider_config.get("model") or provider),
                        timeout_seconds=timeout_seconds,
                        started_at=time.perf_counter(),
                        status="failed",
                        error_type=_vision_provider_error_type(str(exc), type(exc).__name__),
                        error_message=str(exc),
                        fallback_from=fallback_from,
                    ),
                )
            )

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    return thread, result_queue


def parse_page_visual(page_b64: str) -> dict[str, Any]:
    """Full-page screenshot -> structured question JSON via Qwen-VL."""
    page_started = time.perf_counter()
    page_timeout_seconds = _vision_timeout_seconds()
    page_deadline = page_started + page_timeout_seconds
    timeout_seconds = min(
        _vision_provider_timeout_seconds(page_timeout_seconds),
        page_timeout_seconds,
    )
    soft_timeout_seconds = min(timeout_seconds, _vision_soft_timeout_seconds())
    attempts: list[dict[str, Any]] = []
    configs = vision_provider_configs()
    _refresh_provider_runtime_state(configs)
    provider_order = ranked_vision_provider_order()
    last_fallback_from: str | None = None
    qwen_attempted = False
    qwen_config = configs["qwen_vl"]
    available_providers: list[str] = []

    for provider in provider_order:
        provider_config = configs.get(provider)
        if not provider_config:
            continue
        if not provider_config.get("configured"):
            attempts.append(
                _provider_missing_attempt(
                    provider_config=provider_config,
                    timeout_seconds=timeout_seconds,
                    fallback_from=last_fallback_from,
                )
            )
            last_fallback_from = provider
            continue
        if _provider_in_cooldown(provider):
            attempts.append(
                _provider_cooldown_attempt(
                    provider_config=provider_config,
                    timeout_seconds=timeout_seconds,
                    fallback_from=last_fallback_from,
                )
            )
            last_fallback_from = provider
            continue
        available_providers.append(provider)

    if available_providers:
        primary = available_providers[0]
        primary_config = configs[primary]
        backup = available_providers[1] if len(available_providers) > 1 else None
        used_providers: set[str] = set()

        if primary == "qwen_vl":
            qwen_attempted = True

        if primary == "qwen_vl" and backup == "volcengine_ark_vl":
            primary_budget = min(timeout_seconds, max(0.0, page_deadline - time.perf_counter()))
            if primary_budget <= 0:
                return _page_timeout_result_with_attempts(
                    page_started=page_started,
                    page_timeout_seconds=page_timeout_seconds,
                    attempts=attempts,
                    fallback_provider=primary,
                    fallback_model=str(primary_config.get("model") or DEFAULT_QWEN_VISION_MODEL),
                    fallback_from=last_fallback_from,
                )
            primary_thread, primary_queue = _start_provider_call(
                provider=primary,
                provider_config=primary_config,
                page_b64=page_b64,
                timeout_seconds=primary_budget,
                fallback_from=last_fallback_from,
            )
            used_providers.add(primary)
            primary_placeholder_index: int | None = None
            primary_result: dict[str, Any] | None = None
            primary_attempt: dict[str, Any] | None = None
            try:
                primary_result, primary_attempt = primary_queue.get(
                    timeout=min(soft_timeout_seconds, max(0.01, page_deadline - time.perf_counter()))
                )
            except queue.Empty:
                primary_placeholder_index = len(attempts)
                attempts.append(
                    _vision_attempt_payload(
                        provider=primary,
                        model=str(primary_config.get("model") or DEFAULT_QWEN_VISION_MODEL),
                        timeout_seconds=primary_budget,
                        started_at=time.perf_counter() - soft_timeout_seconds,
                        status="failed",
                        error_type="soft_timeout_hedged",
                        error_message=f"soft timeout exceeded after {soft_timeout_seconds:.1f}s; backup launched",
                        fallback_from=last_fallback_from,
                        fallback_reason="qwen_soft_timeout_hedge",
                    )
                )
                backup_budget = min(timeout_seconds, max(0.0, page_deadline - time.perf_counter()))
                if backup_budget <= 0:
                    return _page_timeout_result_with_attempts(
                        page_started=page_started,
                        page_timeout_seconds=page_timeout_seconds,
                        attempts=attempts,
                        fallback_provider=primary,
                        fallback_model=str(primary_config.get("model") or DEFAULT_QWEN_VISION_MODEL),
                        fallback_from=last_fallback_from,
                    )
                backup_thread, backup_queue = _start_provider_call(
                    provider=backup,
                    provider_config=configs[backup],
                    page_b64=page_b64,
                    timeout_seconds=backup_budget,
                    fallback_from=primary,
                )
                used_providers.add(backup)
                primary_done = False
                backup_done = False
                backup_result: dict[str, Any] | None = None
                backup_attempt: dict[str, Any] | None = None
                while time.perf_counter() < page_deadline and not (primary_done and backup_done):
                    if not primary_done:
                        try:
                            primary_result, primary_attempt = primary_queue.get_nowait()
                            primary_done = True
                            if primary_placeholder_index is not None and primary_attempt is not None:
                                attempts[primary_placeholder_index] = primary_attempt
                            if primary_result is not None and primary_attempt is not None and not _provider_failed(primary_result):
                                return _annotate_vision_result(
                                    primary_result,
                                    provider=primary,
                                    model=str(primary_attempt.get("model") or primary_config["model"]),
                                    timeout_seconds=timeout_seconds,
                                    elapsed_ms=primary_attempt["elapsed_ms"],
                                    attempts=attempts,
                                    fallback_from=last_fallback_from,
                                )
                        except queue.Empty:
                            pass
                    if not backup_done:
                        try:
                            backup_result, backup_attempt = backup_queue.get_nowait()
                            backup_done = True
                            attempts.append(backup_attempt)
                            if backup_result is not None and not _provider_failed(backup_result):
                                return _annotate_vision_result(
                                    backup_result,
                                    provider=backup,
                                    model=str(backup_attempt.get("model") or configs[backup]["model"]),
                                    timeout_seconds=timeout_seconds,
                                    elapsed_ms=backup_attempt["elapsed_ms"],
                                    attempts=attempts,
                                    fallback_from=primary,
                                )
                        except queue.Empty:
                            pass
                    time.sleep(0.01)
                if primary_done and primary_result is not None and primary_attempt is not None and _provider_failed(primary_result):
                    last_fallback_from = primary
                if backup_done and backup_result is not None and backup_attempt is not None and _provider_failed(backup_result):
                    last_fallback_from = backup
            else:
                attempts.append(primary_attempt)
                if not _provider_failed(primary_result):
                    return _annotate_vision_result(
                        primary_result,
                        provider=primary,
                        model=str(primary_attempt.get("model") or primary_config["model"]),
                        timeout_seconds=timeout_seconds,
                        elapsed_ms=primary_attempt["elapsed_ms"],
                        attempts=attempts,
                        fallback_from=last_fallback_from,
                    )
                last_fallback_from = primary
            if time.perf_counter() >= page_deadline:
                return _page_timeout_result_with_attempts(
                    page_started=page_started,
                    page_timeout_seconds=page_timeout_seconds,
                    attempts=attempts,
                    fallback_provider=primary,
                    fallback_model=str(primary_config.get("model") or DEFAULT_QWEN_VISION_MODEL),
                    fallback_from=last_fallback_from,
                )

        for provider in available_providers:
            if provider in used_providers:
                continue
            provider_config = configs.get(provider)
            if not provider_config:
                continue
            remaining_timeout = min(timeout_seconds, max(0.0, page_deadline - time.perf_counter()))
            if remaining_timeout <= 0:
                return _page_timeout_result_with_attempts(
                    page_started=page_started,
                    page_timeout_seconds=page_timeout_seconds,
                    attempts=attempts,
                    fallback_provider=provider,
                    fallback_model=str(provider_config.get("model") or provider),
                    fallback_from=last_fallback_from,
                )
            result, attempt = _call_vision_provider_with_cache(
                provider=provider,
                provider_config=provider_config,
                page_b64=page_b64,
                timeout_seconds=remaining_timeout,
                fallback_from=last_fallback_from,
            )
            attempts.append(attempt)
            if provider == "qwen_vl":
                qwen_attempted = True
            if not _provider_failed(result):
                return _annotate_vision_result(
                    result,
                    provider=provider,
                    model=str(attempt.get("model") or provider_config["model"]),
                    timeout_seconds=timeout_seconds,
                    elapsed_ms=attempt["elapsed_ms"],
                    attempts=attempts,
                    fallback_from=last_fallback_from,
                )
            last_fallback_from = provider
            if time.perf_counter() >= page_deadline:
                return _page_timeout_result_with_attempts(
                    page_started=page_started,
                    page_timeout_seconds=page_timeout_seconds,
                    attempts=attempts,
                    fallback_provider=provider,
                    fallback_model=str(attempt.get("model") or provider_config.get("model") or provider),
                    fallback_from=last_fallback_from,
                )

    provider_failure_summary = _provider_attempt_failure_summary(attempts)

    if not qwen_attempted or not qwen_config.get("configured"):
        return _annotate_vision_result(
            {
                "page_type": "unknown",
                "materials": [],
                "questions": [],
                "visuals": [],
                "warnings": ["visual_model_failed"],
                "error": provider_failure_summary or "vision providers failed",
                "schema_validation": {"provider_attempts": attempts},
                "raw_model_result": {"error": provider_failure_summary or "vision providers failed"},
            },
            provider=attempts[-1]["provider"] if attempts else "qwen_vl",
            model=attempts[-1]["model"] if attempts else qwen_config.get("model") or DEFAULT_QWEN_VISION_MODEL,
            timeout_seconds=timeout_seconds,
            elapsed_ms=sum(int(item.get("elapsed_ms") or 0) for item in attempts),
            attempts=attempts,
            fallback_from=attempts[-1].get("fallback_from") if attempts else None,
        )

    qwen_base_url = str(qwen_config.get("base_url") or "")
    if time.perf_counter() >= page_deadline:
        return _page_timeout_result_with_attempts(
            page_started=page_started,
            page_timeout_seconds=page_timeout_seconds,
            attempts=attempts,
            fallback_provider="qwen_vl",
            fallback_model=str(qwen_config.get("model") or DEFAULT_QWEN_VISION_MODEL),
            fallback_from=attempts[-1].get("fallback_from") if attempts else None,
        )
    if not dashscope_sdk_page_fallback_enabled(qwen_base_url):
        return _annotate_vision_result(
            {
                "page_type": "unknown",
                "materials": [],
                "questions": [],
                "visuals": [],
                "warnings": ["visual_model_failed"],
                "error": provider_failure_summary or "vision providers failed",
                "schema_validation": {"provider_attempts": attempts},
                "raw_model_result": {"error": provider_failure_summary or "vision providers failed"},
            },
            provider=attempts[-1]["provider"] if attempts else "qwen_vl",
            model=attempts[-1]["model"] if attempts else qwen_config.get("model") or DEFAULT_QWEN_VISION_MODEL,
            timeout_seconds=timeout_seconds,
            elapsed_ms=sum(int(item.get("elapsed_ms") or 0) for item in attempts),
            attempts=attempts,
            fallback_from=attempts[-1].get("fallback_from") if attempts else None,
        )

    dashscope.api_key = qwen_config["api_key"]
    sdk_started = time.perf_counter()
    try:
        record_ai_call("qwen_vl")
        response = _call_with_timeout(
            lambda: dashscope.MultiModalConversation.call(
                model=qwen_config.get("model") or DEFAULT_QWEN_VISION_MODEL,
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
            model=qwen_config.get("model") or DEFAULT_QWEN_VISION_MODEL,
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
            model=qwen_config.get("model") or DEFAULT_QWEN_VISION_MODEL,
            timeout_seconds=timeout_seconds,
            elapsed_ms=sdk_attempt["elapsed_ms"],
            attempts=attempts,
            fallback_from="qwen_vl",
        )
    except Exception as exc:
        record_ai_call("qwen_vl", str(exc))
        message = str(exc)
        if provider_failure_summary:
            message = f"{provider_failure_summary}; DashScope SDK failed: {message}"
        sdk_attempt = _vision_attempt_payload(
            provider="dashscope_sdk",
            model=qwen_config.get("model") or DEFAULT_QWEN_VISION_MODEL,
            timeout_seconds=timeout_seconds,
            started_at=sdk_started,
            status="failed",
            error_type=_vision_provider_error_type(message, type(exc).__name__),
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
            model=qwen_config.get("model") or DEFAULT_QWEN_VISION_MODEL,
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
    model = _config_value("visual_model", "AI_VISUAL_MODEL", DEFAULT_QWEN_VISION_MODEL)

    if base_url:
        try:
            record_ai_call("qwen_vl")
            result = _chat_completion_json(
                api_key=api_key,
                base_url=base_url,
                model=model or DEFAULT_QWEN_VISION_MODEL,
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
            model=model or DEFAULT_QWEN_VISION_MODEL,
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
    model = _config_value("visual_model", "AI_VISUAL_MODEL", DEFAULT_QWEN_VISION_MODEL)
    prompt = OCR_REGION_PROMPT.replace("{mode}", mode)

    if base_url:
        try:
            record_ai_call("qwen_vl")
            result = _chat_completion_json(
                api_key=api_key,
                base_url=base_url,
                model=model or DEFAULT_QWEN_VISION_MODEL,
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
            model=model or DEFAULT_QWEN_VISION_MODEL,
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
    model = _config_value("visual_model", "AI_VISUAL_MODEL", DEFAULT_QWEN_VISION_MODEL)
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
                model=model or DEFAULT_QWEN_VISION_MODEL,
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
            model=DEFAULT_QWEN_VISION_MODEL,
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
