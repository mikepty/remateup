"""FASE 11 — AI audit log.

Stores per-call audit entries:

- provider
- modelo
- tokens (prompt, completion, total)
- latencia
- prompt hash
- response hash
- confidence
- campo
- documento

The API key is NEVER stored.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class AIAuditLog:
    def __init__(self, path: Optional[str] = None):
        default_dir = Path(__file__).resolve().parent / "audit"
        self._path = path or str(default_dir / "ai_audit.jsonl")
        self._entries: list[dict] = []

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def record(
        self,
        provider: str,
        modelo: str,
        tokens: dict,
        latencia_ms: float,
        prompt_hash: str,
        response_hash: str,
        confidence: float,
        campo: str,
        documento: str = "",
        decision: str = "",
        status: str = "success",
        country: str = "",
    ) -> dict:
        entry = {
            "provider": provider,
            "modelo": modelo,
            "tokens": {
                "prompt_tokens": int(tokens.get("prompt_tokens", 0)),
                "completion_tokens": int(tokens.get("completion_tokens", 0)),
                "total_tokens": int(tokens.get("total_tokens", 0)),
            },
            "latencia_ms": round(float(latencia_ms), 3),
            "prompt_hash": prompt_hash,
            "response_hash": response_hash,
            "confidence": float(confidence),
            "campo": campo,
            "documento": documento,
            "decision": decision,
            "status": status,
            "country": country,
            "timestamp": self._now(),
        }
        self._entries.append(entry)
        self._append_to_file(entry)
        return entry

    def _append_to_file(self, entry: dict):
        try:
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def to_list(self) -> list[dict]:
        return list(self._entries)

    def count(self) -> int:
        return len(self._entries)

    def stats(self) -> dict:
        total_tokens = sum(e["tokens"]["total_tokens"] for e in self._entries)
        total_latency = sum(e["latencia_ms"] for e in self._entries)
        by_provider: dict[str, int] = {}
        by_decision: dict[str, int] = {}
        for e in self._entries:
            by_provider[e["provider"]] = by_provider.get(e["provider"], 0) + 1
            by_decision[e["decision"]] = by_decision.get(e["decision"], 0) + 1
        return {
            "entries": len(self._entries),
            "total_tokens": total_tokens,
            "avg_latency_ms": round(total_latency / len(self._entries), 3) if self._entries else 0.0,
            "by_provider": by_provider,
            "by_decision": by_decision,
        }

    def clear(self):
        self._entries.clear()

    def path(self) -> str:
        return self._path
