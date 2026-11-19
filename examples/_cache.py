"""A tiny file cache for the examples: every Satelit call costs credits, so keep answers for a while.

Answers live in examples/.cache/ (git-ignored). Delete the folder to force fresh calls.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, Tuple

from satelit import Response

CACHE = Path(__file__).resolve().parent / ".cache"


def cached(key: str, ttl_seconds: int, load: Callable[[], Response[Any]]) -> Tuple[Any, Dict[str, Any], bool]:
    """Returns ``(data, meta, from_cache)``: the copy if younger than ``ttl_seconds``, else a fresh call."""
    file = CACHE / (hashlib.sha256(key.encode()).hexdigest()[:16] + ".json")
    try:
        hit = json.loads(file.read_text(encoding="utf-8"))
        if time.time() - hit["at"] < ttl_seconds:
            return hit["data"], hit["meta"], True
    except (OSError, ValueError, KeyError):
        pass  # no copy yet
    r = load()
    CACHE.mkdir(exist_ok=True)
    file.write_text(
        json.dumps({"at": time.time(), "data": r.data, "meta": r.meta}, ensure_ascii=False), encoding="utf-8"
    )
    return r.data, r.meta, False


def attribution_line(meta: Dict[str, Any]) -> str:
    """The line every screen that shows the data must carry: the answer's attribution, its sources, and Satelit."""
    parts = [meta["attribution"]] if meta.get("attribution") else []
    names = [s["name"] for s in meta.get("sources") or [] if s.get("name") and s["name"] != "Satelit"]
    if names and not parts:
        parts.append("Source: " + ", ".join(names))
    if not any("satelit.md" in p for p in parts):
        parts.append("Data: Satelit (satelit.md)")
    return " | ".join(parts)
