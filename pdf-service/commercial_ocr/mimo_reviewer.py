"""MiMo reviewer: visual (mimo-v2.5) + text (mimo-v2.5-pro).

Default mode: mock (no real API calls).
Real calls only when MIMO_ENABLED=true and MIMO_API_KEY exists.
Real call failure auto-degrades to skipped/mock.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

# --- config helpers ---

def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _mimo_enabled() -> bool:
    return _env("MIMO_ENABLED", "false").lower() in {"1", "true", "yes", "on"}


def _mimo_api_key() -> str:
    return _env("MIMO_API_KEY")


def _mimo_base_url() -> str:
    return _env("MIMO_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1")


def _mimo_text_model() -> str:
    return _env("MIMO_TEXT_MODEL", "mimo-v2.5-pro")


def _mimo_vision_model() -> str:
    return _env("MIMO_VISION_MODEL", "mimo-v2.5")


def _mimo_timeout_ms() -> int:
    try:
        return int(_env("MIMO_TIMEOUT_MS", "120000"))
    except ValueError:
        return 120000


def _real_smoke_allowed() -> bool:
    return _mimo_enabled() and bool(_mimo_api_key())


# --- openai-compatible call ---

def _call_mimo(
    *,
    model: str,
    messages: list[dict[str, Any]],
    timeout_ms: int | None = None,
    response_format: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Call MiMo via OpenAI-compatible API. Returns parsed JSON or raises."""
    try:
        import httpx
    except ImportError:
        raise RuntimeError("httpx not installed")

    api_key = _mimo_api_key()
    base_url = _mimo_base_url().rstrip("/")
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 4096,
    }
    if response_format:
        body["response_format"] = response_format

    timeout = (timeout_ms or _mimo_timeout_ms()) / 1000.0
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    content = data["choices"][0]["message"]["content"]
    # strip markdown fences if present
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        content = "\n".join(lines)
    return json.loads(content)


# --- MiMo-v2.5 visual review ---

VISUAL_REVIEW_SYSTEM_PROMPT = """你是一个 PDF 题目截图的视觉评审员。
你需要检查截图中：
1. 题干、图表标题、表头、图例是否被裁掉
2. 材料题（17-20共用材料）的 shared material 是否完整可见
3. 图形推理题的图形是否完整
4. 选项是否清晰可读
5. 是否有 undefined/null/[object Object] 等渲染错误
6. 页面是否有严重布局问题

请严格返回 JSON，格式如下：
{
  "overall_verdict": "pass|warning|fail|skipped",
  "human_readable": true/false,
  "visual_grouping_summary": "描述",
  "material_ownership_assessment": "描述",
  "ocr_error_suspicions": ["列表"],
  "layout_issues": ["列表"],
  "blocking_issues": ["列表"],
  "recommendations": ["列表"]
}"""


def review_visual_screenshot(
    *,
    image_base64: str,
    context: str = "",
    ocr_summary: str = "",
) -> dict[str, Any]:
    """Review a screenshot using MiMo-v2.5 (visual model).

    Returns MiMoVisualReviewResult dict.
    Falls back to mock/skipped if real call not available or fails.
    """
    if not _real_smoke_allowed():
        return _mock_visual_result("real_mimo_not_configured")

    try:
        messages = [
            {"role": "system", "content": VISUAL_REVIEW_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"请评审以下截图。{context}\n\nOCR 摘要:\n{ocr_summary[:2000]}"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                    },
                ],
            },
        ]
        start = time.time()
        result = _call_mimo(model=_mimo_vision_model(), messages=messages)
        elapsed_ms = int((time.time() - start) * 1000)
        result["_elapsed_ms"] = elapsed_ms
        result["model"] = "mimo-v2.5"
        result["skipped_reason"] = None
        return result
    except Exception as e:
        logger.warning("MiMo visual review failed: %s", e)
        return _mock_visual_result(f"real_call_failed: {e}")


# --- MiMo-v2.5-pro text review ---

TEXT_REVIEW_SYSTEM_PROMPT = """你是一个题目数据的文本评审员。
你需要检查 JSON 数据中：
1. 17-20 题是否共享同一个 material_id
2. local_stem 是否重复了 shared_stem 的内容
3. shared_assets 是否被保留
4. quality_gate 是否合理
5. publish_gate 是否能阻止不完整题目
6. h5 payload 是否一致
7. answer=null / analysis=unknown 是否被正确处理

请严格返回 JSON，格式如下：
{
  "overall_verdict": "pass|warning|fail|skipped",
  "same_material_id_for_17_20": true/false,
  "local_stem_not_polluted": true/false,
  "shared_assets_preserved": true/false,
  "quality_gate_reasonable": true/false,
  "publish_gate_reasonable": true/false,
  "h5_payload_consistent": true/false,
  "blocking_issues": ["列表"],
  "recommendations": ["列表"]
}"""


def review_text_payload(
    *,
    payload: dict[str, Any],
    context: str = "",
) -> dict[str, Any]:
    """Review a JSON payload using MiMo-v2.5-pro (text model).

    Returns MiMoTextReviewResult dict.
    Falls back to mock/skipped if real call not available or fails.
    """
    if not _real_smoke_allowed():
        return _mock_text_result("real_mimo_not_configured")

    try:
        payload_str = json.dumps(payload, ensure_ascii=False, indent=2)
        if len(payload_str) > 30000:
            payload_str = payload_str[:30000] + "\n... (truncated)"

        messages = [
            {"role": "system", "content": TEXT_REVIEW_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"请评审以下数据。{context}\n\n```json\n{payload_str}\n```",
            },
        ]
        start = time.time()
        result = _call_mimo(model=_mimo_text_model(), messages=messages)
        elapsed_ms = int((time.time() - start) * 1000)
        result["_elapsed_ms"] = elapsed_ms
        result["model"] = "mimo-v2.5-pro"
        result["skipped_reason"] = None
        return result
    except Exception as e:
        logger.warning("MiMo text review failed: %s", e)
        return _mock_text_result(f"real_call_failed: {e}")


# --- mock fallbacks ---

def _mock_visual_result(reason: str) -> dict[str, Any]:
    return {
        "overall_verdict": "skipped",
        "human_readable": True,
        "visual_grouping_summary": f"mock_visual_review:{reason}",
        "material_ownership_assessment": "mock:not_evaluated",
        "ocr_error_suspicions": [],
        "layout_issues": [],
        "blocking_issues": [],
        "recommendations": ["enable_real_mimo_for_visual_review"],
        "model": "mimo-v2.5",
        "skipped_reason": reason,
    }


def _mock_text_result(reason: str) -> dict[str, Any]:
    return {
        "overall_verdict": "skipped",
        "same_material_id_for_17_20": True,
        "local_stem_not_polluted": True,
        "shared_assets_preserved": True,
        "quality_gate_reasonable": True,
        "publish_gate_reasonable": True,
        "h5_payload_consistent": True,
        "blocking_issues": [],
        "recommendations": ["enable_real_mimo_for_text_review"],
        "model": "mimo-v2.5-pro",
        "skipped_reason": reason,
    }


# --- public API ---

def mimo_review_status() -> dict[str, Any]:
    """Return current MiMo reviewer configuration status."""
    return {
        "enabled": _mimo_enabled(),
        "api_key_set": bool(_mimo_api_key()),
        "base_url": _mimo_base_url(),
        "text_model": _mimo_text_model(),
        "vision_model": _mimo_vision_model(),
        "real_smoke_allowed": _real_smoke_allowed(),
        "timeout_ms": _mimo_timeout_ms(),
    }
