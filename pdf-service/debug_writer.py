from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def write_debug_bundle(output_dir: str, **payloads: Any) -> None:
    debug = Path(output_dir) / "debug"
    debug.mkdir(parents=True, exist_ok=True)
    warnings = payloads.get("warnings") or {}
    for name, payload in payloads.items():
        if name == "markdown":
            continue
        (debug / f"{name}.json").write_text(
            json.dumps(_jsonable(payload), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    if warnings:
        (debug / "warnings.json").write_text(
            json.dumps(_jsonable(warnings), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value
