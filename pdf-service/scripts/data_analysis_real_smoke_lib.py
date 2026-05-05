from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ai_client


DEFAULT_TEXT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def load_project_env() -> None:
    for env_path in [
        PROJECT_ROOT / ".env",
        PROJECT_ROOT / "backend" / ".env",
        ROOT / ".env",
    ]:
        if env_path.is_file():
            load_dotenv(env_path, override=False)


def timestamp_slug() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def project_relative_path(path: str | Path) -> str:
    target = Path(path).expanduser().resolve()
    try:
        return str(target.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(target)


def read_prompt(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8").strip()


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, payload: Any) -> None:
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_page_spec(spec: str | None, *, total_pages: int) -> list[int]:
    if not spec or str(spec).strip().lower() in {"all", "*"}:
        return list(range(1, total_pages + 1))
    pages: set[int] = set()
    for chunk in str(spec).split(","):
        part = chunk.strip()
        if not part:
            continue
        if "-" in part:
            start_raw, end_raw = part.split("-", 1)
            start = int(start_raw)
            end = int(end_raw)
            if end < start:
                start, end = end, start
            for page_no in range(start, end + 1):
                if 1 <= page_no <= total_pages:
                    pages.add(page_no)
            continue
        page_no = int(part)
        if 1 <= page_no <= total_pages:
            pages.add(page_no)
    return sorted(pages)


def extract_likely_question_range(text: str) -> list[int]:
    match = re.search(r"回答\s*(\d{1,3})\s*[-~—至到]\s*(\d{1,3})\s*题", text)
    if not match:
        return []
    start = int(match.group(1))
    end = int(match.group(2))
    return [start, end] if start <= end else [end, start]


def resolve_text_model_config() -> dict[str, Any]:
    api_key = (
        ai_client.current_config_value("text_api_key", "AI_TEXT_API_KEY")
        or ai_client.current_config_value("deepseek_api_key", "DEEPSEEK_API_KEY")
        or ai_client.current_config_value("dashscope_api_key", "DASHSCOPE_API_KEY")
    )
    base_url = (
        ai_client.current_config_value("text_base_url", "AI_TEXT_BASE_URL")
        or ai_client.current_config_value("deepseek_base_url", "DEEPSEEK_BASE_URL")
        or ai_client.current_config_value("dashscope_base_url", "DASHSCOPE_BASE_URL", DEFAULT_TEXT_BASE_URL)
        or DEFAULT_TEXT_BASE_URL
    )
    model = (
        ai_client.current_config_value("text_model", "AI_TEXT_MODEL")
        or ai_client.current_config_value("deepseek_model", "DEEPSEEK_MODEL")
        or "qwen-plus"
    )
    provider = "deepseek" if "deepseek" in str(base_url).lower() else "qwen_text"
    configured = bool(str(api_key or "").strip() and str(base_url or "").strip() and str(model or "").strip())
    return {
        "configured": configured,
        "provider": provider,
        "api_key": api_key,
        "base_url": str(base_url or "").strip(),
        "model": str(model or "").strip(),
    }


def text_key_presence() -> dict[str, bool]:
    return {
        "AI_TEXT_API_KEY": bool(ai_client.current_config_present("text_api_key", "AI_TEXT_API_KEY")),
        "DEEPSEEK_API_KEY": bool(ai_client.current_config_present("deepseek_api_key", "DEEPSEEK_API_KEY")),
        "DASHSCOPE_API_KEY": bool(ai_client.current_config_present("dashscope_api_key", "DASHSCOPE_API_KEY")),
    }


def call_text_json(
    *,
    prompt: str,
    timeout_seconds: float,
    model_config: dict[str, Any] | None = None,
) -> tuple[Any, dict[str, Any]]:
    config = model_config or resolve_text_model_config()
    if not config.get("configured"):
        raise RuntimeError("text_model_not_configured")
    messages = [
        {"role": "system", "content": "你只返回 JSON，不返回 markdown 或解释。"},
        {"role": "user", "content": prompt},
    ]
    started = time.perf_counter()
    result = ai_client._call_with_timeout(
        lambda: ai_client._chat_completion_json(
            api_key=str(config["api_key"]),
            base_url=str(config["base_url"]),
            model=str(config["model"]),
            messages=messages,
            temperature=0.0,
            timeout=timeout_seconds,
        ),
        timeout_seconds,
    )
    return result, {
        "provider": str(config["provider"]),
        "model": str(config["model"]),
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    }


def call_openai_vision_json(
    *,
    provider_config: dict[str, Any],
    prompt: str,
    image_b64: str,
    timeout_seconds: float,
) -> tuple[Any, dict[str, Any]]:
    if not provider_config.get("configured"):
        raise RuntimeError(f"{provider_config.get('provider')}_not_configured")
    started = time.perf_counter()
    result = ai_client._call_with_timeout(
        lambda: ai_client._chat_completion_json(
            api_key=str(provider_config["api_key"]),
            base_url=str(provider_config["base_url"]),
            model=str(provider_config["model"]),
            messages=ai_client._vision_call_messages(prompt, image_b64),
            temperature=0.0,
            timeout=timeout_seconds,
            default_headers=provider_config.get("default_headers"),
        ),
        timeout_seconds,
    )
    return result, {
        "provider": str(provider_config.get("provider") or ""),
        "model": str(provider_config.get("model") or ""),
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    }


def call_ark_vision_json(
    *,
    provider_config: dict[str, Any],
    prompt: str,
    image_b64: str,
    timeout_seconds: float,
) -> tuple[Any, dict[str, Any]]:
    if not provider_config.get("configured"):
        raise RuntimeError("volcengine_ark_vl_not_configured")
    image_url = ai_client._data_url_for_page_b64(image_b64)
    last_error: Exception | None = None
    for candidate in provider_config.get("model_candidates") or []:
        model = str(candidate.get("model") or "").strip()
        if not model:
            continue
        started = time.perf_counter()
        try:
            result, _summary = ai_client._call_with_timeout(
                lambda: ai_client._ark_responses_json(
                    api_key=str(provider_config["api_key"]),
                    base_url=str(provider_config["base_url"]),
                    model=model,
                    prompt=prompt,
                    image_url=image_url,
                    timeout=timeout_seconds,
                    responses_path=str(provider_config.get("endpoint") or ai_client.DEFAULT_ARK_RESPONSES_PATH),
                ),
                timeout_seconds,
            )
            return result, {
                "provider": str(provider_config.get("provider") or "volcengine_ark_vl"),
                "model": model,
                "model_type": str(candidate.get("type") or "model_name"),
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
            }
        except Exception as exc:  # pragma: no cover - runtime integration path
            last_error = exc
    if last_error is None:
        raise RuntimeError("volcengine_ark_vl_no_candidate_model")
    raise last_error


def keyword_lines(text: str, keywords: list[str], *, limit: int = 3) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        if any(keyword in line for keyword in keywords):
            lines.append(line)
        if len(lines) >= limit:
            break
    return lines
