from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Any

try:
    import psutil
except Exception:  # pragma: no cover - optional dependency fallback
    psutil = None


VERSION = "1.0.0"
STARTED_AT = datetime.now(timezone.utc)
_today_date = date.today()

queue = {
    "pending": 0,
    "processing": 0,
    "completed_today": 0,
}

ai_providers: dict[str, dict[str, Any]] = {
    "qwen_vl": {"enabled": False, "last_call_at": None, "last_error": None},
    "deepseek": {"enabled": False, "last_call_at": None, "last_error": None},
}

stats = {
    "today": {
        "total_parsed": 0,
        "total_questions": 0,
        "success_count": 0,
        "fail_count": 0,
        "total_parse_seconds": 0.0,
    },
    "session": {
        "total_parsed": 0,
        "total_questions": 0,
        "ai_calls": {"qwen_vl": 0, "deepseek": 0},
    },
}

runtime_config: dict[str, str] = {}


def reset_today_if_needed() -> None:
    global _today_date
    current = date.today()
    if current == _today_date:
        return
    _today_date = current
    stats["today"] = {
        "total_parsed": 0,
        "total_questions": 0,
        "success_count": 0,
        "fail_count": 0,
        "total_parse_seconds": 0.0,
    }
    queue["completed_today"] = 0


def mark_parse_start() -> None:
    reset_today_if_needed()
    queue["pending"] = max(0, queue["pending"] - 1)
    queue["processing"] += 1


def mark_parse_finish(success: bool, question_count: int, elapsed_seconds: float) -> None:
    reset_today_if_needed()
    queue["processing"] = max(0, queue["processing"] - 1)
    stats["today"]["total_parsed"] += 1
    stats["today"]["total_questions"] += question_count
    stats["today"]["total_parse_seconds"] += elapsed_seconds
    stats["session"]["total_parsed"] += 1
    stats["session"]["total_questions"] += question_count
    if success:
        stats["today"]["success_count"] += 1
        queue["completed_today"] += 1
    else:
        stats["today"]["fail_count"] += 1


def record_ai_call(provider: str, error: str | None = None) -> None:
    reset_today_if_needed()
    if provider not in ai_providers:
        ai_providers[provider] = {"enabled": True, "last_call_at": None, "last_error": None}
    ai_providers[provider]["enabled"] = True
    ai_providers[provider]["last_call_at"] = datetime.now(timezone.utc).isoformat()
    ai_providers[provider]["last_error"] = error
    stats["session"]["ai_calls"][provider] = stats["session"]["ai_calls"].get(provider, 0) + 1


def memory_mb() -> int:
    if not psutil:
        return 0
    return int(psutil.Process().memory_info().rss // 1024**2)


def status_payload() -> dict[str, Any]:
    reset_today_if_needed()
    return {
        "status": "ok",
        "uptime_seconds": int((datetime.now(timezone.utc) - STARTED_AT).total_seconds()),
        "version": VERSION,
        "queue": dict(queue),
        "memory_mb": memory_mb(),
        "ai_providers": ai_providers,
    }


def stats_payload() -> dict[str, Any]:
    reset_today_if_needed()
    today = dict(stats["today"])
    total = today["total_parsed"]
    today["avg_questions_per_pdf"] = round(today["total_questions"] / total, 1) if total else 0
    today["avg_parse_seconds"] = round(today["total_parse_seconds"] / total, 1) if total else 0
    today.pop("total_parse_seconds", None)
    return {"today": today, "session": stats["session"]}


def effective_config() -> dict[str, str]:
    merged = {
        "ai_provider_vision": os.getenv("AI_PROVIDER_VISION", "qwen_vl"),
        "ai_provider_text": os.getenv("AI_PROVIDER_TEXT", "qwen"),
        "dashscope_api_key": os.getenv("DASHSCOPE_API_KEY", ""),
        "deepseek_api_key": os.getenv("DEEPSEEK_API_KEY", ""),
        "dashscope_base_url": os.getenv(
            "DASHSCOPE_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
        "backend_url": os.getenv("BACKEND_URL", "http://localhost:3010"),
        "prompt_source": os.getenv("PROMPT_SOURCE", "hardcoded"),
        "cache_ttl": os.getenv("PROMPT_CACHE_TTL", "300"),
    }
    merged.update(runtime_config)
    return merged


def update_runtime_config(data: dict[str, Any]) -> list[str]:
    mapping = {
        "ai_provider_vision": "AI_PROVIDER_VISION",
        "ai_provider_text": "AI_PROVIDER_TEXT",
        "qwen_api_key": "DASHSCOPE_API_KEY",
        "deepseek_api_key": "DEEPSEEK_API_KEY",
        "cache_ttl": "PROMPT_CACHE_TTL",
    }
    updated: list[str] = []
    for key, env_key in mapping.items():
        value = data.get(key)
        if value in (None, ""):
            continue
        os.environ[env_key] = str(value)
        runtime_config[_runtime_key(env_key)] = str(value)
        updated.append(key)
    return updated


def masked_config_payload() -> dict[str, Any]:
    config = effective_config()
    return {
        "ai_provider_vision": config.get("ai_provider_vision") or "qwen_vl",
        "ai_provider_text": config.get("ai_provider_text") or "qwen",
        "qwen_api_key_set": bool(config.get("dashscope_api_key")),
        "deepseek_api_key_set": bool(config.get("deepseek_api_key")),
        "backend_url": config.get("backend_url"),
        "prompt_source": config.get("prompt_source") or "hardcoded",
        "cache_ttl": int(config.get("cache_ttl") or 300),
    }


def _runtime_key(env_key: str) -> str:
    return {
        "AI_PROVIDER_VISION": "ai_provider_vision",
        "AI_PROVIDER_TEXT": "ai_provider_text",
        "DASHSCOPE_API_KEY": "dashscope_api_key",
        "DEEPSEEK_API_KEY": "deepseek_api_key",
        "PROMPT_CACHE_TTL": "cache_ttl",
    }.get(env_key, env_key.lower())
