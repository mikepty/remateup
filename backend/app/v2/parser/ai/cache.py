"""FASE 11 — AI response cache.

Key: sha256(campo + texto + pais).
Stored: respuesta (value), confidence, provider, timestamp (and model/reason).

Avoids repeated calls to the provider for identical inputs.
"""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend.app.v2.parser.context import ParserContext


def cache_key(field_name: str, text: str, country: str) -> str:
    payload = f"{country}|{field_name}|{text}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class AICache:
    def __init__(self, path: Optional[str] = None, max_entries: int = 2000):
        self._path = path
        self._max_entries = max_entries
        self._entries: dict[str, dict] = {}
        self._hits = 0
        self._misses = 0
        if path:
            self.load()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def key(self, field_name: str, context: ParserContext) -> str:
        return cache_key(field_name, context.text, context.country)

    def get(self, key: str) -> Optional[dict]:
        entry = self._entries.get(key)
        if entry is None:
            self._misses += 1
            return None
        self._hits += 1
        return entry

    def set(
        self,
        key: str,
        value: Any,
        confidence: float,
        provider: str,
        model: str = "",
        reason: str = "",
        decision: str = "",
        document_id: str = "",
    ) -> dict:
        entry = {
            "value": value,
            "confidence": confidence,
            "provider": provider,
            "model": model,
            "reason": reason,
            "decision": decision,
            "document_id": document_id,
            "timestamp": self._now(),
        }
        self._entries[key] = entry
        if len(self._entries) > self._max_entries:
            oldest = min(self._entries, key=lambda k: self._entries[k].get("timestamp", ""))
            del self._entries[oldest]
        return entry

    def stats(self) -> dict:
        return {
            "hits": self._hits,
            "misses": self._misses,
            "size": len(self._entries),
            "max_entries": self._max_entries,
            "path": self._path,
        }

    def hit_rate(self) -> float:
        total = self._hits + self._misses
        if total == 0:
            return 0.0
        return round(self._hits / total, 4)

    def clear(self):
        self._entries.clear()
        self._hits = 0
        self._misses = 0

    def to_dict(self) -> dict:
        return {"stats": self.stats(), "entries": self._entries}

    def save(self, path: Optional[str] = None):
        target = path or self._path
        if not target:
            return
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(self._entries, f, ensure_ascii=False, indent=2)

    def load(self, path: Optional[str] = None):
        target = path or self._path
        if not target or not os.path.exists(target):
            return
        with open(target, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            self._entries = data
