from __future__ import annotations

import json
import os
import uuid
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
        _atomic_write_json(debug / f"{name}.json", payload)
    if warnings:
        _atomic_write_json(debug / "warnings.json", warnings)


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


def _atomic_write_json(path: Path, payload: Any) -> None:
    content = json.dumps(_jsonable(payload), ensure_ascii=False, indent=2).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp_path.open("wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        tmp_path.replace(path)
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
