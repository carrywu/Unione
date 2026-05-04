from __future__ import annotations

from typing import Any

import ai_client


def get_config_value(
    key: str,
    env_key: str | None = None,
    default: str | None = None,
) -> str:
    value = ai_client.current_config_value(key, env_key, default)
    return str(value or "").strip()


def get_flag(
    key: str,
    env_key: str | None = None,
    *,
    default: bool,
) -> bool:
    value = get_config_value(key, env_key)
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def get_positive_int(
    key: str,
    env_key: str | None = None,
    *,
    default: int,
) -> int:
    value = get_config_value(key, env_key)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def get_json_path_override(
    key: str,
    env_key: str | None = None,
) -> str:
    return get_config_value(key, env_key)


def compact_dict(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if value not in (None, "", [], {})
    }
