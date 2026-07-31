"""FASE 12 — Parte 4: AI Feedback Loop.

La IA hoy solo responde. Este módulo agrega métricas sin aprender ni modificar
Knowledge:

  campo, modelo, confidence, aceptado, rechazado, corregido, tiempo, cache.

- aceptado : la IA resolvió FOUND con confianza >= umbral y el valor se usó tal cual.
- rechazado: la IA respondió pero no se aceptó (NOT_FOUND / REQUIRES_REVIEW / error).
- corregido: la IA respondió FOUND pero el valor final difiere del propuesto.

Solo registra estadísticas. NO crea reglas, NO aprende, NO modifica Knowledge.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Optional

ACCEPTED_MIN_CONFIDENCE = 0.95


@dataclass
class AIFeedbackEntry:
    campo: str
    modelo: str
    confidence: float
    decision: str
    aceptado: bool
    rechazado: bool
    corregido: bool
    tiempo_ms: float
    cache_hit: bool
    documento: str = ""
    provider: str = ""

    def to_dict(self) -> dict:
        return {
            "campo": self.campo,
            "modelo": self.modelo,
            "provider": self.provider,
            "confidence": self.confidence,
            "decision": self.decision,
            "aceptado": self.aceptado,
            "rechazado": self.rechazado,
            "corregido": self.corregido,
            "tiempo_ms": round(self.tiempo_ms, 3),
            "cache_hit": self.cache_hit,
            "documento": self.documento,
        }


class AIFeedbackTracker:
    def __init__(self):
        self._entries: list[AIFeedbackEntry] = []
        self._cache_totals: dict = {}

    def record(self, entry: AIFeedbackEntry):
        self._entries.append(entry)

    def ingest_result(self, result: dict, documento: str = "", resolver=None):
        """Registra las decisiones de IA de un resultado de pipeline usando el
        audit log del resolver (cubre TODAS las llamadas: aceptadas, rechazadas
        y corregidas). Sin duplicar entradas."""
        self._resolver_hint = resolver
        entries = self._collect_audit_entries(result)
        if entries:
            self.ingest_audit_entries(entries, result=result, documento=documento)
        ai = result.get("ai", {}) or {}
        self.ingest_ai_summary(ai, documento or result.get("document_id", ""))

    def _collect_audit_entries(self, result: dict) -> list[dict]:
        """Lee el audit log en memoria del resolver usado por el pipeline."""
        resolver = getattr(self, "_resolver_hint", None)
        audit = None
        if resolver is not None:
            audit = getattr(resolver, "_audit", None)
        if audit is None:
            return []
        return audit.to_list()

    def ingest_audit_entries(self, entries: list[dict], result: Optional[dict] = None,
                             documento: str = ""):
        """Registra entradas de audit log. Aceptado/corregido se decide con el
        estado final real del campo (el audit no guarda el valor propuesto)."""
        final_status: dict[str, str] = {}
        if result is not None:
            fields = result.get("fields", {}) or {}
            final_status = {f: d.get("status") for f, d in fields.items() if isinstance(d, dict)}
        for a in entries:
            decision = str(a.get("decision", ""))
            final = final_status.get(a.get("campo", ""))
            if decision == "FOUND" and final == "FOUND":
                aceptado, corregido = True, False
            elif decision == "FOUND" and final is not None and final != "FOUND":
                # Respuesta de IA descartada / reemplazada por etapas posteriores.
                aceptado, corregido = False, True
            elif decision == "FOUND":
                # Sin estado final disponible (batch sin resultado): FOUND se
                # cuenta como aceptado; no hay evidencia de corrección.
                aceptado, corregido = True, False
            else:
                aceptado, corregido = False, False
            entry = AIFeedbackEntry(
                campo=str(a.get("campo", "")),
                modelo=str(a.get("modelo", "")),
                confidence=float(a.get("confidence", 0.0) or 0.0),
                decision=decision,
                aceptado=aceptado,
                rechazado=not (aceptado or corregido),
                corregido=corregido,
                tiempo_ms=float(a.get("latencia_ms", 0.0) or 0.0),
                cache_hit=False,
                documento=documento or str(a.get("documento", "")),
                provider=str(a.get("provider", "")),
            )
            self.record(entry)

    def ingest_ai_summary(self, summary: dict, documento: str = ""):
        """Acumula cache hits/misses y tiempo del summary de IA del pipeline."""
        self._cache_totals = {
            "cache_hits": self._cache_totals.get("cache_hits", 0) + int(summary.get("cache_hits", 0) or 0),
            "cache_misses": self._cache_totals.get("cache_misses", 0) + int(summary.get("cache_misses", 0) or 0),
            "ai_time_ms": self._cache_totals.get("ai_time_ms", 0.0) + float(summary.get("ai_time_ms", 0.0) or 0.0),
        }
        self._last_summary = {
            "cache_hits": summary.get("cache_hits", 0),
            "cache_misses": summary.get("cache_misses", 0),
            "ai_time_ms": summary.get("ai_time_ms", 0.0),
            "documento": documento,
        }

    def cache_summary(self) -> dict:
        totals = getattr(self, "_cache_totals", None) or {}
        return {
            "cache_hits": totals.get("cache_hits", 0),
            "cache_misses": totals.get("cache_misses", 0),
            "ai_time_ms": round(totals.get("ai_time_ms", 0.0), 2),
        }

    def summary(self) -> dict:
        total = len(self._entries)
        if total == 0:
            return {"entries": 0}
        aceptados = sum(1 for e in self._entries if e.aceptado)
        rechazados = sum(1 for e in self._entries if e.rechazado)
        corregidos = sum(1 for e in self._entries if e.corregido)
        avg_conf = sum(e.confidence for e in self._entries) / total
        avg_time = sum(e.tiempo_ms for e in self._entries) / total

        by_field: dict[str, dict] = {}
        by_model: dict[str, dict] = {}
        for e in self._entries:
            for bucket, key in ((by_field, e.campo), (by_model, e.modelo)):
                b = bucket.setdefault(key, {"total": 0, "aceptados": 0, "rechazados": 0,
                                            "corregidos": 0, "confianza_media": 0.0})
                b["total"] += 1
                b["aceptados"] += int(e.aceptado)
                b["rechazados"] += int(e.rechazado)
                b["corregidos"] += int(e.corregido)
                b["confianza_media"] += e.confidence
        for bucket in (by_field, by_model):
            for b in bucket.values():
                b["confianza_media"] = round(b["confianza_media"] / max(b["total"], 1), 4)
        return {
            "entries": total,
            "aceptados": aceptados,
            "rechazados": rechazados,
            "corregidos": corregidos,
            "tasa_aceptacion": round(aceptados / total, 4),
            "confianza_media": round(avg_conf, 4),
            "tiempo_medio_ms": round(avg_time, 3),
            "por_campo": by_field,
            "por_modelo": by_model,
            "aprendizaje_automatico": False,
            "knowledge_modificado": False,
        }

    def to_list(self) -> list[dict]:
        return [e.to_dict() for e in self._entries]
