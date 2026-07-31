"""FASE 12 — Parte 3: Pipeline Trace.

Trazabilidad completa por aviso para poder reconstruir exactamente el recorrido:

  documento, pagina, bbox, segmento, parser utilizado, knowledge aplicado,
  IA utilizada, validator, certification, tiempo, resultado.

Salida JSON por aviso (array), 100% determinista a partir del resultado del
pipeline y de la información de la propia etapa.
"""

import json
import re
from typing import Any, Optional

RULE_ID_RE = re.compile(r"rule:(?:regex|alias|format|contextual):([a-f0-9]{12}):v(\d+)")


def _parser_info(country: str, document_type: str = "REMATE") -> dict:
    from backend.app.v2.parser.factory import ParserFactory

    try:
        parser = ParserFactory().get_parser(country.upper(), document_type)
        return {
            "pais": country.upper(),
            "tipo": document_type,
            "nombre": parser.__class__.__name__,
        }
    except Exception as e:
        return {"pais": country.upper(), "tipo": document_type, "nombre": "unknown", "error": str(e)}


def _knowledge_applied(fields: dict) -> list[dict]:
    """Reglas de knowledge aplicadas, extraídas de la evidencia de los campos
    con source=knowledge (method: rule:regex:<id>:v<n>)."""
    rules: list[dict] = []
    for fname, fdata in fields.items():
        if not isinstance(fdata, dict) or fdata.get("source") != "knowledge":
            continue
        for ev in fdata.get("evidence") or []:
            method = ev.get("method", "") if isinstance(ev, dict) else getattr(ev, "method", "")
            m = RULE_ID_RE.search(str(method))
            if m:
                rules.append({
                    "campo": fname,
                    "rule_id": m.group(1),
                    "version": int(m.group(2)),
                })
    return rules


def _ai_used(result: dict) -> dict:
    ai = result.get("ai", {}) or {}
    if not ai.get("enabled", True):
        return {"usada": False}
    return {
        "usada": True,
        "campos": ai.get("ai_fields", []),
        "provider": ai.get("provider", ""),
        "tiempo_ms": ai.get("ai_time_ms", 0.0),
        "cache_hits": ai.get("cache_hits", 0),
        "cache_misses": ai.get("cache_misses", 0),
        "cost_usd": ai.get("cost_usd", 0.0),
        "total_tokens": ai.get("total_ai_tokens", 0),
    }


def _validator_info(result: dict) -> dict:
    validation = result.get("validation", {}) or {}
    return {
        "decision": validation.get("decision", ""),
        "score": validation.get("score", 0.0),
        "campos_encontrados": validation.get("fields_found", []),
        "campos_faltantes": validation.get("fields_missing", []),
        "reglas_aplicadas": len(validation.get("rules_applied", [])),
        "reglas_fallidas": len(validation.get("rules_failed", [])),
        "duplicado": (validation.get("duplicate_info") or {}).get("level"),
    }


def _certification_info(result: dict) -> dict:
    cert = result.get("certification", {}) or {}
    avisos = cert.get("all_avisos", [])
    return {
        "decision": avisos[0].get("decision") if avisos else "unknown",
        "confianza": avisos[0].get("confidence") if avisos else None,
    }


def build_trace(aviso: dict) -> dict:
    """Construye la traza JSON completa de un aviso del run aviso-por-aviso."""
    result = aviso.get("pipeline_result", {})
    comparison = aviso.get("comparison", {})
    fields = result.get("fields", {})
    return {
        "documento": aviso.get("documento"),
        "aviso_id": aviso.get("aviso_id"),
        "expediente_golden": aviso.get("expediente"),
        "pagina": aviso.get("pagina"),
        "bbox": aviso.get("bbox"),
        "segmento": aviso.get("segmento"),
        "parser": _parser_info(result.get("country", "")),
        "knowledge": {
            "aplicado": bool(_knowledge_applied(fields)),
            "reglas": _knowledge_applied(fields),
        },
        "ia": _ai_used(result),
        "validator": _validator_info(result),
        "certification": _certification_info(result),
        "tiempo_ms": result.get("total_time_ms", 0.0),
        "resultado": {
            fname: {
                "valor": fdata.get("value"),
                "estado": fdata.get("status"),
                "confianza": fdata.get("confidence"),
                "fuente": fdata.get("source"),
            }
            for fname, fdata in fields.items()
        },
        "comparacion_golden": {
            "precision": comparison.get("precision"),
            "recall": comparison.get("recall"),
            "f1": comparison.get("f1"),
            "errores": comparison.get("errores", []),
        },
    }


def build_traces(aviso_run: dict) -> list[dict]:
    """Ensambla el array de trazas de un run aviso-por-aviso (documento incluido)."""
    traces: list[dict] = []
    for aviso in aviso_run.get("avisos", []):
        trace = build_trace(aviso)
        trace["documento"] = aviso_run.get("documento")
        traces.append(trace)
    return traces


def traces_to_json(traces: list[dict]) -> str:
    return json.dumps({"pipeline_trace": traces}, ensure_ascii=False, indent=1, default=str)
