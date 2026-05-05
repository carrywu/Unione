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
    "volcengine_ark_vl": {"enabled": False, "last_call_at": None, "last_error": None},
    "mimo_vl": {"enabled": False, "last_call_at": None, "last_error": None},
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
        "ai_calls": {"qwen_vl": 0, "volcengine_ark_vl": 0, "mimo_vl": 0, "deepseek": 0},
    },
}

runtime_config: dict[str, str] = {}
RECENT_PROVIDER_ATTEMPTS_LIMIT = 400
recent_provider_attempts: list[dict[str, Any]] = []


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


def record_provider_attempt(attempt: dict[str, Any]) -> None:
    reset_today_if_needed()
    provider = str(attempt.get("provider") or "").strip()
    if provider:
        ai_providers.setdefault(
            provider,
            {"enabled": True, "last_call_at": None, "last_error": None},
        )
        ai_providers[provider]["enabled"] = True
        ai_providers[provider]["last_call_at"] = attempt.get("finishedAt") or datetime.now(
            timezone.utc
        ).isoformat()
        ai_providers[provider]["last_error"] = attempt.get("errorType") or attempt.get("error_type")
    recent_provider_attempts.append(dict(attempt))
    if len(recent_provider_attempts) > RECENT_PROVIDER_ATTEMPTS_LIMIT:
        del recent_provider_attempts[:-RECENT_PROVIDER_ATTEMPTS_LIMIT]


def memory_mb() -> int:
    if not psutil:
        return 0
    return int(psutil.Process().memory_info().rss // 1024**2)


def status_payload() -> dict[str, Any]:
    reset_today_if_needed()
    config = effective_config()
    return {
        "status": "ok",
        "uptime_seconds": int((datetime.now(timezone.utc) - STARTED_AT).total_seconds()),
        "version": VERSION,
        "queue": dict(queue),
        "memory_mb": memory_mb(),
        "ai_providers": ai_providers,
        "runtime": {
            "ai_provider_vision": config.get("ai_provider_vision") or "qwen_vl",
            "vision_ai_provider_order": config.get("vision_ai_provider_order")
            or "volcengine_ark_vl,qwen_vl,mimo_vl",
            "commercial_ocr_enabled": str(config.get("commercial_ocr_enabled") or "false").lower()
            in {"1", "true", "yes", "on"},
            "commercial_ocr_real_smoke": str(config.get("commercial_ocr_real_smoke") or "false").lower()
            in {"1", "true", "yes", "on"},
            "pdf_parse_primary_provider": config.get("pdf_parse_primary_provider") or "mock_commercial_ocr",
            "pdf_parse_fallback_providers": config.get("pdf_parse_fallback_providers") or "local_parser,mock_commercial_ocr",
            "ocr_provider_trace_enabled": str(config.get("ocr_provider_trace_enabled") or "false").lower()
            in {"1", "true", "yes", "on"},
            "vision_ai_timeout_seconds": float(config.get("vision_ai_timeout_seconds") or 120),
            "vision_ai_provider_timeout_seconds": float(
                config.get("vision_ai_provider_timeout_seconds") or 120
            ),
            "pdf_visual_page_timeout_seconds": float(
                config.get("pdf_visual_page_timeout_seconds")
                or config.get("vision_ai_timeout_seconds")
                or 120
            ),
            "pdf_visual_provider_timeout_seconds": float(
                config.get("pdf_visual_provider_timeout_seconds")
                or config.get("vision_ai_provider_timeout_seconds")
                or 120
            ),
        },
        "recent_provider_attempts": recent_provider_attempts[-80:],
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
        "mimo_api_key": os.getenv("MIMO_API_KEY", ""),
        "dashscope_base_url": os.getenv(
            "DASHSCOPE_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
        "mimo_base_url": os.getenv(
            "MIMO_BASE_URL",
            "https://token-plan-cn.xiaomimimo.com/v1",
        ),
        "mimo_model": os.getenv("MIMO_MODEL", "mimo-v2.5"),
        "mimo_vision_model": os.getenv("MIMO_VISION_MODEL", os.getenv("MIMO_MODEL", "mimo-v2.5")),
        "ark_api_key": os.getenv("ARK_API_KEY", "")
        or os.getenv("VOLCENGINE_ARK_API_KEY", "")
        or os.getenv("VOLC_ARK_API_KEY", ""),
        "ark_base_url": os.getenv("ARK_BASE_URL", "")
        or os.getenv("VOLCENGINE_ARK_BASE_URL", "")
        or os.getenv("ARK_CHAT_COMPLETIONS_URL", "")
        or os.getenv("VOLCENGINE_ARK_CHAT_COMPLETIONS_URL", "")
        or "https://ark.cn-beijing.volces.com/api/v3",
        "ark_vision_model": os.getenv("ARK_VISION_MODEL", "")
        or os.getenv("VOLCENGINE_ARK_VISION_MODEL", "")
        or os.getenv("ARK_MODEL", "")
        or os.getenv("VOLCENGINE_ARK_MODEL", ""),
        "ark_endpoint_id": os.getenv("ARK_ENDPOINT_ID", "")
        or os.getenv("VOLCENGINE_ARK_ENDPOINT_ID", ""),
        "ark_api_mode": os.getenv("ARK_API_MODE", "")
        or os.getenv("VOLCENGINE_ARK_API_MODE", "")
        or "responses",
        "ark_responses_path": os.getenv("ARK_RESPONSES_PATH", "")
        or os.getenv("VOLCENGINE_ARK_RESPONSES_PATH", "")
        or "/responses",
        "vision_ai_provider_order": os.getenv(
            "VISION_AI_PROVIDER_ORDER",
            "volcengine_ark_vl,qwen_vl,mimo_vl",
        ),
        "commercial_ocr_enabled": os.getenv("COMMERCIAL_OCR_ENABLED", "false"),
        "commercial_ocr_real_smoke": os.getenv("COMMERCIAL_OCR_REAL_SMOKE", "false"),
        "pdf_parse_primary_provider": os.getenv("PDF_PARSE_PRIMARY_PROVIDER", "mock_commercial_ocr"),
        "pdf_parse_fallback_providers": os.getenv(
            "PDF_PARSE_FALLBACK_PROVIDERS",
            "local_parser,mock_commercial_ocr",
        ),
        "ocr_provider_trace_enabled": os.getenv("OCR_PROVIDER_TRACE_ENABLED", "false"),
        "baidu_api_key": os.getenv("BAIDU_API_KEY", ""),
        "baidu_secret_key": os.getenv("BAIDU_SECRET_KEY", ""),
        "baidu_access_token": os.getenv("BAIDU_ACCESS_TOKEN", ""),
        "baidu_ocr_endpoint": os.getenv("BAIDU_OCR_ENDPOINT", ""),
        "baidu_ocr_timeout_ms": os.getenv("BAIDU_OCR_TIMEOUT_MS", "30000"),
        "tencent_secret_id": os.getenv("TENCENT_SECRET_ID", ""),
        "tencent_secret_key": os.getenv("TENCENT_SECRET_KEY", ""),
        "tencent_region": os.getenv("TENCENT_REGION", "ap-guangzhou"),
        "tencent_ocr_endpoint": os.getenv("TENCENT_OCR_ENDPOINT", "https://ocr.tencentcloudapi.com"),
        "tencent_ocr_version": os.getenv("TENCENT_OCR_VERSION", "2018-11-19"),
        "tencent_ocr_timeout_ms": os.getenv("TENCENT_OCR_TIMEOUT_MS", "60000"),
        "tencent_ocr_use_new_model": os.getenv("TENCENT_OCR_USE_NEW_MODEL", "false"),
        "tencent_ocr_enable_image_crop": os.getenv("TENCENT_OCR_ENABLE_IMAGE_CROP", "false"),
        "tencent_ocr_enable_only_detect_border": os.getenv("TENCENT_OCR_ENABLE_ONLY_DETECT_BORDER", "false"),
        "tencent_ocr_real_smoke": os.getenv("TENCENT_OCR_REAL_SMOKE", "false"),
        "backend_url": os.getenv("BACKEND_URL", "http://localhost:3010"),
        "prompt_source": os.getenv("PROMPT_SOURCE", "hardcoded"),
        "cache_ttl": os.getenv("PROMPT_CACHE_TTL", "300"),
        "vision_ai_timeout_seconds": os.getenv("VISION_AI_TIMEOUT_SECONDS", "120"),
        "vision_ai_provider_timeout_seconds": os.getenv("VISION_AI_PROVIDER_TIMEOUT_SECONDS", "120"),
        "pdf_visual_page_timeout_seconds": os.getenv("PDF_VISUAL_PAGE_TIMEOUT_SECONDS", ""),
        "pdf_visual_provider_timeout_seconds": os.getenv("PDF_VISUAL_PROVIDER_TIMEOUT_SECONDS", ""),
    }
    merged.update(runtime_config)
    return merged


def update_runtime_config(data: dict[str, Any]) -> list[str]:
    mapping = {
        "ai_provider_vision": "AI_PROVIDER_VISION",
        "ai_provider_text": "AI_PROVIDER_TEXT",
        "qwen_api_key": "DASHSCOPE_API_KEY",
        "deepseek_api_key": "DEEPSEEK_API_KEY",
        "mimo_api_key": "MIMO_API_KEY",
        "mimo_base_url": "MIMO_BASE_URL",
        "mimo_model": "MIMO_MODEL",
        "mimo_vision_model": "MIMO_VISION_MODEL",
        "ark_api_key": "ARK_API_KEY",
        "ark_base_url": "ARK_BASE_URL",
        "ark_vision_model": "ARK_VISION_MODEL",
        "ark_endpoint_id": "ARK_ENDPOINT_ID",
        "ark_api_mode": "ARK_API_MODE",
        "ark_responses_path": "ARK_RESPONSES_PATH",
        "vision_ai_provider_order": "VISION_AI_PROVIDER_ORDER",
        "commercial_ocr_enabled": "COMMERCIAL_OCR_ENABLED",
        "commercial_ocr_real_smoke": "COMMERCIAL_OCR_REAL_SMOKE",
        "pdf_parse_primary_provider": "PDF_PARSE_PRIMARY_PROVIDER",
        "pdf_parse_fallback_providers": "PDF_PARSE_FALLBACK_PROVIDERS",
        "mock_commercial_ocr_fixture_name": "MOCK_COMMERCIAL_OCR_FIXTURE_NAME",
        "commercial_ocr_fixture_root": "COMMERCIAL_OCR_FIXTURE_ROOT",
        "ocr_provider_trace_enabled": "OCR_PROVIDER_TRACE_ENABLED",
        "baidu_api_key": "BAIDU_API_KEY",
        "baidu_secret_key": "BAIDU_SECRET_KEY",
        "baidu_access_token": "BAIDU_ACCESS_TOKEN",
        "baidu_ocr_endpoint": "BAIDU_OCR_ENDPOINT",
        "baidu_ocr_timeout_ms": "BAIDU_OCR_TIMEOUT_MS",
        "tencent_secret_id": "TENCENT_SECRET_ID",
        "tencent_secret_key": "TENCENT_SECRET_KEY",
        "tencent_region": "TENCENT_REGION",
        "tencent_ocr_endpoint": "TENCENT_OCR_ENDPOINT",
        "tencent_ocr_version": "TENCENT_OCR_VERSION",
        "tencent_ocr_timeout_ms": "TENCENT_OCR_TIMEOUT_MS",
        "tencent_ocr_use_new_model": "TENCENT_OCR_USE_NEW_MODEL",
        "tencent_ocr_enable_image_crop": "TENCENT_OCR_ENABLE_IMAGE_CROP",
        "tencent_ocr_enable_only_detect_border": "TENCENT_OCR_ENABLE_ONLY_DETECT_BORDER",
        "tencent_ocr_real_smoke": "TENCENT_OCR_REAL_SMOKE",
        "vision_ai_timeout_seconds": "VISION_AI_TIMEOUT_SECONDS",
        "vision_ai_provider_timeout_seconds": "VISION_AI_PROVIDER_TIMEOUT_SECONDS",
        "pdf_visual_page_timeout_seconds": "PDF_VISUAL_PAGE_TIMEOUT_SECONDS",
        "pdf_visual_provider_timeout_seconds": "PDF_VISUAL_PROVIDER_TIMEOUT_SECONDS",
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
        "mimo_api_key_set": bool(config.get("mimo_api_key")),
        "ark_api_key_set": bool(config.get("ark_api_key")),
        "dashscope_base_url": config.get("dashscope_base_url"),
        "mimo_base_url": config.get("mimo_base_url") or "https://token-plan-cn.xiaomimimo.com/v1",
        "mimo_model": config.get("mimo_model") or "mimo-v2.5",
        "mimo_vision_model": config.get("mimo_vision_model") or config.get("mimo_model") or "mimo-v2.5",
        "ark_base_url": config.get("ark_base_url") or "https://ark.cn-beijing.volces.com/api/v3",
        "ark_vision_model": config.get("ark_vision_model") or "",
        "ark_endpoint_id": config.get("ark_endpoint_id") or "",
        "ark_api_mode": config.get("ark_api_mode") or "responses",
        "ark_responses_path": config.get("ark_responses_path") or "/responses",
        "vision_ai_provider_order": config.get("vision_ai_provider_order") or "volcengine_ark_vl,qwen_vl,mimo_vl",
        "commercial_ocr_enabled": str(config.get("commercial_ocr_enabled") or "false").lower()
        in {"1", "true", "yes", "on"},
        "commercial_ocr_real_smoke": str(config.get("commercial_ocr_real_smoke") or "false").lower()
        in {"1", "true", "yes", "on"},
        "pdf_parse_primary_provider": config.get("pdf_parse_primary_provider") or "mock_commercial_ocr",
        "pdf_parse_fallback_providers": config.get("pdf_parse_fallback_providers") or "local_parser,mock_commercial_ocr",
        "mock_commercial_ocr_fixture_name": config.get("mock_commercial_ocr_fixture_name") or "",
        "commercial_ocr_fixture_root": config.get("commercial_ocr_fixture_root") or "",
        "ocr_provider_trace_enabled": str(config.get("ocr_provider_trace_enabled") or "false").lower()
        in {"1", "true", "yes", "on"},
        "baidu_api_key_set": bool(config.get("baidu_api_key")),
        "baidu_secret_key_set": bool(config.get("baidu_secret_key")),
        "baidu_access_token_set": bool(config.get("baidu_access_token")),
        "baidu_ocr_endpoint": config.get("baidu_ocr_endpoint") or "https://aip.baidubce.com/rest/2.0/ocr/v1/paper_cut_edu",
        "baidu_ocr_timeout_ms": int(config.get("baidu_ocr_timeout_ms") or 30000),
        "tencent_secret_id_set": bool(config.get("tencent_secret_id")),
        "tencent_secret_key_set": bool(config.get("tencent_secret_key")),
        "tencent_region": config.get("tencent_region") or "ap-guangzhou",
        "tencent_ocr_endpoint": config.get("tencent_ocr_endpoint") or "https://ocr.tencentcloudapi.com",
        "tencent_ocr_version": config.get("tencent_ocr_version") or "2018-11-19",
        "tencent_ocr_timeout_ms": int(config.get("tencent_ocr_timeout_ms") or 60000),
        "tencent_ocr_use_new_model": str(config.get("tencent_ocr_use_new_model") or "false").lower()
        in {"1", "true", "yes", "on"},
        "tencent_ocr_enable_image_crop": str(config.get("tencent_ocr_enable_image_crop") or "false").lower()
        in {"1", "true", "yes", "on"},
        "tencent_ocr_enable_only_detect_border": str(config.get("tencent_ocr_enable_only_detect_border") or "false").lower()
        in {"1", "true", "yes", "on"},
        "tencent_ocr_real_smoke": str(config.get("tencent_ocr_real_smoke") or "false").lower()
        in {"1", "true", "yes", "on"},
        "backend_url": config.get("backend_url"),
        "prompt_source": config.get("prompt_source") or "hardcoded",
        "cache_ttl": int(config.get("cache_ttl") or 300),
        "vision_ai_timeout_seconds": float(config.get("vision_ai_timeout_seconds") or 120),
        "vision_ai_provider_timeout_seconds": float(config.get("vision_ai_provider_timeout_seconds") or 120),
        "pdf_visual_page_timeout_seconds": float(
            config.get("pdf_visual_page_timeout_seconds") or config.get("vision_ai_timeout_seconds") or 120
        ),
        "pdf_visual_provider_timeout_seconds": float(
            config.get("pdf_visual_provider_timeout_seconds") or config.get("vision_ai_provider_timeout_seconds") or 120
        ),
    }


def _runtime_key(env_key: str) -> str:
    return {
        "AI_PROVIDER_VISION": "ai_provider_vision",
        "AI_PROVIDER_TEXT": "ai_provider_text",
        "DASHSCOPE_API_KEY": "dashscope_api_key",
        "DEEPSEEK_API_KEY": "deepseek_api_key",
        "MIMO_API_KEY": "mimo_api_key",
        "MIMO_BASE_URL": "mimo_base_url",
        "MIMO_MODEL": "mimo_model",
        "MIMO_VISION_MODEL": "mimo_vision_model",
        "ARK_API_KEY": "ark_api_key",
        "ARK_BASE_URL": "ark_base_url",
        "ARK_VISION_MODEL": "ark_vision_model",
        "ARK_ENDPOINT_ID": "ark_endpoint_id",
        "ARK_API_MODE": "ark_api_mode",
        "ARK_RESPONSES_PATH": "ark_responses_path",
        "VISION_AI_PROVIDER_ORDER": "vision_ai_provider_order",
        "COMMERCIAL_OCR_ENABLED": "commercial_ocr_enabled",
        "COMMERCIAL_OCR_REAL_SMOKE": "commercial_ocr_real_smoke",
        "PDF_PARSE_PRIMARY_PROVIDER": "pdf_parse_primary_provider",
        "PDF_PARSE_FALLBACK_PROVIDERS": "pdf_parse_fallback_providers",
        "MOCK_COMMERCIAL_OCR_FIXTURE_NAME": "mock_commercial_ocr_fixture_name",
        "COMMERCIAL_OCR_FIXTURE_ROOT": "commercial_ocr_fixture_root",
        "OCR_PROVIDER_TRACE_ENABLED": "ocr_provider_trace_enabled",
        "BAIDU_API_KEY": "baidu_api_key",
        "BAIDU_SECRET_KEY": "baidu_secret_key",
        "BAIDU_ACCESS_TOKEN": "baidu_access_token",
        "BAIDU_OCR_ENDPOINT": "baidu_ocr_endpoint",
        "BAIDU_OCR_TIMEOUT_MS": "baidu_ocr_timeout_ms",
        "TENCENT_SECRET_ID": "tencent_secret_id",
        "TENCENT_SECRET_KEY": "tencent_secret_key",
        "TENCENT_REGION": "tencent_region",
        "TENCENT_OCR_ENDPOINT": "tencent_ocr_endpoint",
        "TENCENT_OCR_VERSION": "tencent_ocr_version",
        "TENCENT_OCR_TIMEOUT_MS": "tencent_ocr_timeout_ms",
        "TENCENT_OCR_USE_NEW_MODEL": "tencent_ocr_use_new_model",
        "TENCENT_OCR_ENABLE_IMAGE_CROP": "tencent_ocr_enable_image_crop",
        "TENCENT_OCR_ENABLE_ONLY_DETECT_BORDER": "tencent_ocr_enable_only_detect_border",
        "TENCENT_OCR_REAL_SMOKE": "tencent_ocr_real_smoke",
        "VISION_AI_TIMEOUT_SECONDS": "vision_ai_timeout_seconds",
        "VISION_AI_PROVIDER_TIMEOUT_SECONDS": "vision_ai_provider_timeout_seconds",
        "PDF_VISUAL_PAGE_TIMEOUT_SECONDS": "pdf_visual_page_timeout_seconds",
        "PDF_VISUAL_PROVIDER_TIMEOUT_SECONDS": "pdf_visual_provider_timeout_seconds",
        "PROMPT_CACHE_TTL": "cache_ttl",
    }.get(env_key, env_key.lower())
