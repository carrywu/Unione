from __future__ import annotations

import base64
import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

import ai_client


SMOKE_PROMPT = (
    '请只输出 JSON，不要解释：'
    '{"image_received":true,"has_text_or_shape":true,"summary":"不超过12个字"}'
)
ARK_REMOTE_SMOKE_PROMPT = '你看见了什么？请用 JSON 输出：{"ok":true,"summary":"..."}'
ARK_REMOTE_SMOKE_IMAGE_URL = "https://ark-project.tos-cn-beijing.volces.com/doc_image/ark_demo_img_1.png"
EMBEDDED_SMOKE_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+cR1EAAAAASUVORK5CYII="
)
DEFAULT_PROVIDER_ORDER = ["volcengine_ark_vl", "qwen_vl", "mimo_vl"]


def load_project_env() -> None:
    for env_path in [
        PROJECT_ROOT / ".env",
        PROJECT_ROOT / "backend" / ".env",
        PROJECT_ROOT / "pdf-service" / ".env",
    ]:
        if env_path.is_file():
            load_dotenv(env_path, override=False)


def smoke_image_b64() -> str:
    try:
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (48, 32), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((6, 6, 42, 26), outline="black", width=2)
        draw.line((6, 26, 42, 6), fill="black", width=2)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("ascii")
    except Exception:
        return EMBEDDED_SMOKE_PNG_B64


def _truncate_jsonable(value: Any, limit: int = 240) -> str:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    return text if len(text) <= limit else text[:limit] + "..."


def _truncate_text(value: str | None, limit: int = 240) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text if len(text) <= limit else text[:limit] + "..."


def _error_type_from_missing(missing: list[str]) -> str | None:
    mapping = {
        "missing_api_key": "auth_missing",
        "model_missing": "model_missing",
        "base_url_missing": "base_url_missing",
    }
    for key in missing:
        if key in mapping:
            return mapping[key]
    return "provider_not_configured" if missing else None


def _smoke_openai_provider(
    *,
    provider: str,
    provider_config: dict[str, Any],
    image_b64: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "configured": bool(provider_config.get("configured")),
        "key_present": bool(provider_config.get("api_key")),
        "key_masked": provider_config.get("key_masked"),
        "base_url": provider_config.get("base_url") or "",
        "model_or_endpoint": provider_config.get("model") or "",
        "modalities": provider_config.get("modalities") or {"input": ["text", "image"], "output": ["text"]},
        "supports_chat_completions": bool(provider_config.get("supports_chat_completions")),
        "health": "fail",
        "latency_ms": None,
        "error_type": _error_type_from_missing(list(provider_config.get("missing") or [])),
        "error_message": None,
        "request_metadata": {
            "provider": provider,
            "base_url": provider_config.get("base_url") or "",
            "model_or_endpoint": provider_config.get("model") or "",
            "timeout_seconds": timeout_seconds,
            "image_bytes": len(base64.b64decode(image_b64)),
            "input_modalities": ["text", "image"],
            "output_modalities": ["text"],
        },
        "response_summary": None,
    }
    if not provider_config.get("configured"):
        payload["error_message"] = ", ".join(provider_config.get("missing") or []) or "provider_not_configured"
        return payload

    started = time.perf_counter()
    try:
        response = ai_client._call_with_timeout(
            lambda: ai_client._chat_completion_json(
                api_key=str(provider_config["api_key"]),
                base_url=str(provider_config["base_url"]),
                model=str(provider_config["model"]),
                messages=ai_client._vision_call_messages(SMOKE_PROMPT, image_b64),
                temperature=0.0,
                timeout=timeout_seconds,
                default_headers=provider_config.get("default_headers"),
            ),
            timeout_seconds,
        )
        payload["health"] = "pass"
        payload["latency_ms"] = int((time.perf_counter() - started) * 1000)
        payload["response_summary"] = _truncate_jsonable(response)
        return payload
    except Exception as exc:
        message = str(exc)
        payload["latency_ms"] = int((time.perf_counter() - started) * 1000)
        payload["error_type"] = ai_client._vision_provider_error_type(message, type(exc).__name__)
        payload["error_message"] = message
        return payload


def _smoke_result(
    *,
    health: str,
    started: float,
    summary: dict[str, Any] | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
    request_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "health": health,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "error_type": error_type,
        "error_message": _truncate_text(error_message),
        "request_metadata": request_metadata or {},
        "response_summary": summary or {},
    }


def _ark_candidate_test(
    *,
    provider_config: dict[str, Any],
    candidate: dict[str, str],
    image_url: str,
    prompt: str,
    timeout_seconds: float,
    label: str,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    started = time.perf_counter()
    request_metadata = {
        "provider": "volcengine_ark_vl",
        "api_mode": provider_config.get("api_mode") or "responses",
        "base_url": provider_config.get("base_url") or "",
        "endpoint": provider_config.get("endpoint") or ai_client.DEFAULT_ARK_RESPONSES_PATH,
        "model": candidate.get("model") or "",
        "model_type": candidate.get("type") or "model_name",
        "smoke_label": label,
        "image_url_kind": "remote_url" if image_url.startswith("http") else "data_url",
        "input_modalities": ["text", "image"],
        "output_modalities": ["text"],
    }
    try:
        raw, summary = ai_client._call_with_timeout(
            lambda: ai_client._ark_responses_json(
                api_key=str(provider_config["api_key"]),
                base_url=str(provider_config["base_url"]),
                model=str(candidate["model"]),
                prompt=prompt,
                image_url=image_url,
                timeout=timeout_seconds,
                responses_path=str(provider_config.get("endpoint") or ai_client.DEFAULT_ARK_RESPONSES_PATH),
            ),
            timeout_seconds,
        )
        merged_summary = dict(summary)
        merged_summary["parsed_preview"] = _truncate_jsonable(raw)
        result = {
            "model": candidate.get("model") or "",
            "type": candidate.get("type") or "model_name",
            "health": "pass",
            "error_type": None,
            "error_message": None,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "response_summary": merged_summary,
        }
        smoke_result = _smoke_result(
            health="pass",
            started=started,
            summary=merged_summary,
            request_metadata=request_metadata,
        )
        return result, smoke_result
    except Exception as exc:
        message = str(exc)
        error_type = ai_client._vision_provider_error_type(message, type(exc).__name__)
        result = {
            "model": candidate.get("model") or "",
            "type": candidate.get("type") or "model_name",
            "health": "fail",
            "error_type": error_type,
            "error_message": _truncate_text(message),
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }
        smoke_result = _smoke_result(
            health="fail",
            started=started,
            error_type=error_type,
            error_message=message,
            request_metadata=request_metadata,
        )
        return result, smoke_result


def _smoke_ark_provider(
    *,
    provider_config: dict[str, Any],
    image_b64: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "configured": bool(provider_config.get("configured")),
        "api_mode": provider_config.get("api_mode") or "responses",
        "base_url": provider_config.get("base_url") or "",
        "endpoint": provider_config.get("endpoint") or ai_client.DEFAULT_ARK_RESPONSES_PATH,
        "key_present": bool(provider_config.get("api_key")),
        "key_masked": provider_config.get("key_masked"),
        "model_or_endpoint": provider_config.get("model") or "",
        "modalities": provider_config.get("modalities") or {"input": ["text", "image"], "output": ["text"]},
        "supports_chat_completions": bool(provider_config.get("supports_chat_completions")),
        "supports_responses": bool(provider_config.get("supports_responses")),
        "candidate_models_tested": [],
        "successful_model": None,
        "successful_model_type": None,
        "health": "fail",
        "latency_ms": None,
        "error_type": _error_type_from_missing(list(provider_config.get("missing") or [])),
        "error_message": None,
        "remote_smoke": None,
        "local_smoke": None,
    }
    if not provider_config.get("configured"):
        payload["error_message"] = ", ".join(provider_config.get("missing") or []) or "provider_not_configured"
        return payload

    candidates = list(provider_config.get("model_candidates") or [])
    successful_candidate: dict[str, str] | None = None
    started = time.perf_counter()
    for candidate in candidates:
        result, remote_smoke = _ark_candidate_test(
            provider_config=provider_config,
            candidate=candidate,
            image_url=ARK_REMOTE_SMOKE_IMAGE_URL,
            prompt=ARK_REMOTE_SMOKE_PROMPT,
            timeout_seconds=timeout_seconds,
            label="remote_url",
        )
        payload["candidate_models_tested"].append(result)
        if result["health"] == "pass":
            successful_candidate = candidate
            payload["remote_smoke"] = remote_smoke
            break
    if successful_candidate is None:
        if payload["candidate_models_tested"]:
            last = payload["candidate_models_tested"][-1]
            payload["error_type"] = last.get("error_type")
            payload["error_message"] = last.get("error_message")
        payload["latency_ms"] = int((time.perf_counter() - started) * 1000)
        return payload

    local_image_url = ai_client._data_url_for_page_b64(image_b64)
    _, local_smoke = _ark_candidate_test(
        provider_config=provider_config,
        candidate=successful_candidate,
        image_url=local_image_url,
        prompt=ARK_REMOTE_SMOKE_PROMPT,
        timeout_seconds=timeout_seconds,
        label="local_data_url",
    )
    payload["local_smoke"] = local_smoke
    payload["successful_model"] = successful_candidate.get("model")
    payload["successful_model_type"] = successful_candidate.get("type")
    payload["latency_ms"] = int((time.perf_counter() - started) * 1000)
    if local_smoke["health"] == "pass":
        payload["health"] = "pass"
        payload["error_type"] = None
        payload["error_message"] = None
    else:
        payload["error_type"] = local_smoke.get("error_type")
        payload["error_message"] = local_smoke.get("error_message")
    return payload


def run_provider_health_checks(
    *,
    provider_order: list[str] | None = None,
    timeout_seconds: float = 45.0,
) -> dict[str, Any]:
    load_project_env()
    image_b64 = smoke_image_b64()
    configs = ai_client.vision_provider_configs()
    ordered = provider_order or DEFAULT_PROVIDER_ORDER
    ordered = [provider for provider in ordered if provider in configs]
    providers: dict[str, Any] = {}
    for provider in ordered:
        if provider == "volcengine_ark_vl":
            providers[provider] = _smoke_ark_provider(
                provider_config=configs[provider],
                image_b64=image_b64,
                timeout_seconds=timeout_seconds,
            )
        else:
            providers[provider] = _smoke_openai_provider(
                provider=provider,
                provider_config=configs[provider],
                image_b64=image_b64,
                timeout_seconds=timeout_seconds,
            )

    recommended = [
        provider
        for provider in DEFAULT_PROVIDER_ORDER
        if providers.get(provider, {}).get("health") == "pass"
    ]
    recommended.extend(
        provider
        for provider in DEFAULT_PROVIDER_ORDER
        if provider not in recommended and provider in providers
    )
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "providers": providers,
        "recommended_provider_order": recommended,
    }


def build_provider_health_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Provider Health Report",
        "",
        f"- generated_at: {report.get('generated_at')}",
        f"- recommended_provider_order: {json.dumps(report.get('recommended_provider_order') or [], ensure_ascii=False)}",
        "",
        "| provider | configured | health | latency_ms | error_type |",
        "| --- | --- | --- | --- | --- |",
    ]
    providers = report.get("providers") or {}
    for provider in DEFAULT_PROVIDER_ORDER:
        item = providers.get(provider)
        if not item:
            continue
        lines.append(
            f"| {provider} | {item.get('configured')} | {item.get('health')} | "
            f"{item.get('latency_ms') if item.get('latency_ms') is not None else ''} | "
            f"{item.get('error_type') or ''} |"
        )
    for provider in DEFAULT_PROVIDER_ORDER:
        item = providers.get(provider)
        if not item:
            continue
        lines.extend(
            [
                "",
                f"## {provider}",
                "",
                f"- configured: {item.get('configured')}",
                f"- key_present: {item.get('key_present')}",
                f"- key_masked: {item.get('key_masked') or ''}",
                f"- base_url: {item.get('base_url') or ''}",
                f"- api_mode: {item.get('api_mode') or ''}",
                f"- endpoint: {item.get('endpoint') or ''}",
                f"- model_or_endpoint: {item.get('model_or_endpoint') or ''}",
                f"- modalities: {json.dumps(item.get('modalities') or {}, ensure_ascii=False)}",
                f"- supports_chat_completions: {item.get('supports_chat_completions')}",
                f"- supports_responses: {item.get('supports_responses')}",
                f"- health: {item.get('health')}",
                f"- latency_ms: {item.get('latency_ms') if item.get('latency_ms') is not None else ''}",
                f"- error_type: {item.get('error_type') or ''}",
                f"- error_message: {item.get('error_message') or ''}",
                f"- response_summary: {item.get('response_summary') or ''}",
            ]
        )
        if item.get("candidate_models_tested"):
            lines.append(f"- candidate_models_tested: {json.dumps(item.get('candidate_models_tested') or [], ensure_ascii=False)}")
        if item.get("successful_model"):
            lines.append(f"- successful_model: {item.get('successful_model')}")
            lines.append(f"- successful_model_type: {item.get('successful_model_type')}")
        if item.get("remote_smoke"):
            lines.append(f"- remote_smoke: {json.dumps(item.get('remote_smoke') or {}, ensure_ascii=False)}")
        if item.get("local_smoke"):
            lines.append(f"- local_smoke: {json.dumps(item.get('local_smoke') or {}, ensure_ascii=False)}")
    return "\n".join(lines).strip() + "\n"


def build_ark_provider_markdown(report: dict[str, Any]) -> str:
    ark = ((report.get("providers") or {}).get("volcengine_ark_vl") or {})
    lines = [
        "# Volcengine Ark Provider Report",
        "",
        f"- generated_at: {report.get('generated_at')}",
        f"- provider_id: volcengine_ark_vl",
        f"- configured: {ark.get('configured')}",
        f"- health: {ark.get('health')}",
        f"- key_present: {ark.get('key_present')}",
        f"- key_masked: {ark.get('key_masked') or ''}",
        f"- base_url: {ark.get('base_url') or ''}",
        f"- api_mode: {ark.get('api_mode') or ''}",
        f"- endpoint: {ark.get('endpoint') or ''}",
        f"- model_or_endpoint: {ark.get('model_or_endpoint') or ''}",
        f"- successful_model: {ark.get('successful_model') or ''}",
        f"- successful_model_type: {ark.get('successful_model_type') or ''}",
        f"- modalities: {json.dumps(ark.get('modalities') or {}, ensure_ascii=False)}",
        f"- supports_chat_completions: {ark.get('supports_chat_completions')}",
        f"- supports_responses: {ark.get('supports_responses')}",
        f"- latency_ms: {ark.get('latency_ms') if ark.get('latency_ms') is not None else ''}",
        f"- error_type: {ark.get('error_type') or ''}",
        f"- error_message: {ark.get('error_message') or ''}",
        f"- candidate_models_tested: {json.dumps(ark.get('candidate_models_tested') or [], ensure_ascii=False)}",
        f"- remote_smoke: {json.dumps(ark.get('remote_smoke') or {}, ensure_ascii=False)}",
        f"- local_smoke: {json.dumps(ark.get('local_smoke') or {}, ensure_ascii=False)}",
        f"- recommended_provider_order: {json.dumps(report.get('recommended_provider_order') or [], ensure_ascii=False)}",
    ]
    return "\n".join(lines).strip() + "\n"


def write_provider_health_reports(
    *,
    report_dir: str | Path,
    report: dict[str, Any],
) -> dict[str, str]:
    output = Path(report_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "provider-health-report.json"
    md_path = output / "provider-health-report.md"
    ark_md_path = output / "volcengine-ark-provider-report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(build_provider_health_markdown(report), encoding="utf-8")
    ark_md_path.write_text(build_ark_provider_markdown(report), encoding="utf-8")
    return {
        "json": str(json_path),
        "markdown": str(md_path),
        "ark_markdown": str(ark_md_path),
    }


def main(argv: list[str] | None = None) -> int:
    _ = argv
    report = run_provider_health_checks()
    paths = write_provider_health_reports(
        report_dir=PROJECT_ROOT / ".agent" / "reports",
        report=report,
    )
    print(json.dumps({"report_paths": paths, "recommended_provider_order": report["recommended_provider_order"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
