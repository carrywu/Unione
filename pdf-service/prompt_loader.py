from __future__ import annotations


_cache: dict[str, str] = {}


def invalidate() -> None:
    _cache.clear()
