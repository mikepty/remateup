"""FASE 12 — Parte 7: Production Dashboard.

Dashboard JSON + Markdown agregando TODO el dataset real:

  Procesados, Tiempo, Campos, Knowledge, IA, Validator, Certification,
  Duplicados, Errores, Warnings, Health, Slow stages, Top errores,
  Top reglas, Top campos faltantes, Top campos corregidos.
"""

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

from backend.app.v2.evaluation.production.knowledge_impact import generate_knowledge_impact_report


def _cert_decision(result: dict) -> str:
    cert = result.get("certification", {}) or {}
    avisos = cert.get("all_avisos", [])
    return avisos[0].get("decision", "unknown") if avisos else "unknown"


def _validation_decision(result: dict) -> str:
    return (result.get("validation", {}) or {}).get("decision", "unknown")


def _duplicate_level(result: dict) -> Optional[str]:
    dup = (result.get("validation", {}) or {}).get("duplicate_info", {}) or {}
    return dup.get("level")


def generate_production_dashboard(
    results: list[dict],
    aviso_run: Optional[dict] = None,
    ai_feedback_summary: Optional[dict] = None,
    knowledge_report: Optional[dict] = None,
    out_dir: Optional[str] = None,
) -> dict:
    n = len(results)
    total_ms = sum(r.get("total_time_ms", 0.0) for r in results)
    campos_found_total = sum(len((r.get("fields", {}) or {})) for r in results)
    campos_found_docs = [len((r.get("fields", {}) or {})) for r in results]

    knowledge_counts = Counter()
    for r in results:
        for fdata in (r.get("fields", {}) or {}).values():
            if isinstance(fdata, dict) and fdata.get("source") == "knowledge":
                knowledge_counts[fdata.get("evidence") and "" or "knowledge"] += 1
    knowledge_fields = sum(
        1 for r in results
        for fdata in (r.get("fields", {}) or {}).values()
        if isinstance(fdata, dict) and fdata.get("source") == "knowledge"
    )

    ai_fields = sum(len((r.get("ai", {}) or {}).get("ai_fields", [])) for r in results)
    ai_time_ms = sum((r.get("ai", {}) or {}).get("ai_time_ms", 0.0) for r in results)
    ai_cache_hits = sum((r.get("ai", {}) or {}).get("cache_hits", 0) for r in results)
    ai_cache_misses = sum((r.get("ai", {}) or {}).get("cache_misses", 0) for r in results)
    ai_tokens = sum((r.get("ai", {}) or {}).get("total_ai_tokens", 0) for r in results)
    ai_cost = sum((r.get("ai", {}) or {}).get("cost_usd", 0.0) for r in results)

    validator_decisions = Counter(_validation_decision(r) for r in results)
    validator_scores = [((r.get("validation", {}) or {}).get("score", 0.0)) for r in results]
    cert_decisions = Counter(_cert_decision(r) for r in results)
    duplicados = sum(1 for r in results if _duplicate_level(r) in ("DUPLICATED", "LIKELY_DUPLICATED"))

    errores = Counter()
    warnings = Counter()
    for r in results:
        for e in r.get("errors", []):
            errores[str(e)[:160]] += 1
        for w in r.get("warnings", []):
            warnings[str(w)[:160]] += 1

    stage_times: dict[str, list[float]] = defaultdict(list)
    for r in results:
        for sname, sdata in (r.get("stages", {}) or {}).items():
            if isinstance(sdata, dict) and isinstance(sdata.get("duration_ms"), (int, float)):
                stage_times[sname].append(float(sdata["duration_ms"]))
    slow_stages = sorted(
        ((s, sum(v) / len(v)) for s, v in stage_times.items() if v),
        key=lambda x: x[1], reverse=True,
    )[:8]

    missing_counter = Counter()
    for r in results:
        for f in ((r.get("validation", {}) or {}).get("fields_missing", []) or []):
            missing_counter[f] += 1

    knowledge_report = knowledge_report or generate_knowledge_impact_report()
    top_reglas = knowledge_report.get("top_reglas", [])

    corregidos: list[dict] = []
    if ai_feedback_summary:
        for campo, b in ai_feedback_summary.get("por_campo", {}).items():
            if b.get("corregidos", 0) > 0:
                corregidos.append({"campo": campo, "corregidos": b["corregidos"]})
    corregidos = sorted(corregidos, key=lambda x: x["corregidos"], reverse=True)[:10]

    health = None
    try:
        from backend.app.v2.production.health import run_health_check

        health = run_health_check()
    except Exception as e:
        health = {"status": "ERROR", "error": str(e)}

    dashboard = {
        "procesados": {
            "documentos": n,
            "avisos_por_documento": aviso_run,
        },
        "tiempo": {
            "total_ms": round(total_ms, 2),
            "promedio_ms": round(total_ms / max(n, 1), 2),
            "slow_stages": [{"stage": s, "promedio_ms": round(t, 2)} for s, t in slow_stages],
        },
        "campos": {
            "total_encontrados": campos_found_total,
            "promedio_por_documento": round(campos_found_total / max(n, 1), 2),
            "por_documento": campos_found_docs,
        },
        "knowledge": {
            "campos_resueltos_por_knowledge": knowledge_fields,
            "total_reglas": knowledge_report.get("total_reglas", 0),
            "reglas_usadas": knowledge_report.get("reglas_usadas", 0),
            "reglas_nunca_usadas": knowledge_report.get("reglas_nunca_usadas_count", 0),
            "reglas_expiradas": knowledge_report.get("reglas_expiradas_count", 0),
            "top_reglas": top_reglas,
        },
        "ia": {
            "campos_resueltos_por_ia": ai_fields,
            "tiempo_ms": round(ai_time_ms, 2),
            "cache_hits": ai_cache_hits,
            "cache_misses": ai_cache_misses,
            "tokens_totales": ai_tokens,
            "costo_usd": round(ai_cost, 6),
            "feedback": ai_feedback_summary or {},
        },
        "validator": {
            "decisiones": dict(validator_decisions),
            "score_promedio": round(sum(validator_scores) / max(len(validator_scores), 1), 4) if validator_scores else 0.0,
        },
        "certification": {
            "decisiones": dict(cert_decisions),
        },
        "duplicados": duplicados,
        "errores": {"total": sum(errores.values()), "top": dict(errores.most_common(10))},
        "warnings": {"total": sum(warnings.values()), "top": dict(warnings.most_common(10))},
        "health": health,
        "top_campos_faltantes": dict(missing_counter.most_common(10)),
        "top_campos_corregidos": corregidos,
    }

    if out_dir:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "production_dashboard.json").write_text(
            json.dumps(dashboard, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
        )
        (out / "production_dashboard.md").write_text(_to_markdown(dashboard), encoding="utf-8")
    return dashboard


def _to_markdown(d: dict) -> str:
    lines = ["# Production Dashboard (FASE 12)", ""]
    lines.append("## Procesados")
    lines.append(f"- Documentos: **{d['procesados']['documentos']}**")
    if d["procesados"]["avisos_por_documento"]:
        av = d["procesados"]["avisos_por_documento"]
        lines.append(f"- Avisos anclados: **{av.get('avisos_procesados', 0)}** de {av.get('golden_avisos', 0)} golden")
    lines.append("")
    lines.append("## Tiempo")
    lines.append(f"- Total: **{d['tiempo']['total_ms']} ms** | Promedio: **{d['tiempo']['promedio_ms']} ms**")
    lines.append("")
    lines.append("| Slow stage | promedio ms |")
    lines.append("|---|---|")
    for s in d["tiempo"]["slow_stages"]:
        lines.append(f"| {s['stage']} | {s['promedio_ms']} |")
    lines.append("")
    lines.append("## Campos")
    lines.append(f"- Total encontrados: **{d['campos']['total_encontrados']}** | Promedio por documento: **{d['campos']['promedio_por_documento']}**")
    lines.append("")
    lines.append("## Knowledge")
    lines.append(f"- Campos resueltos por knowledge: **{d['knowledge']['campos_resueltos_por_knowledge']}**")
    lines.append(f"- Reglas: total **{d['knowledge']['total_reglas']}** | usadas **{d['knowledge']['reglas_usadas']}** | nunca usadas **{d['knowledge']['reglas_nunca_usadas']}** | expiradas **{d['knowledge']['reglas_expiradas']}**")
    lines.append("")
    lines.append("## IA")
    ia = d["ia"]
    lines.append(f"- Campos resueltos por IA: **{ia['campos_resueltos_por_ia']}** | tiempo: **{ia['tiempo_ms']} ms**")
    lines.append(f"- Cache: hits **{ia['cache_hits']}** | misses **{ia['cache_misses']}** | tokens **{ia['tokens_totales']}** | costo **${ia['costo_usd']}**")
    fb = ia.get("feedback") or {}
    if fb:
        lines.append(f"- AI feedback: {fb.get('entries', 0)} entradas | aceptados {fb.get('aceptados', 0)} | rechazados {fb.get('rechazados', 0)} | corregidos {fb.get('corregidos', 0)}")
    lines.append("")
    lines.append("## Validator")
    for k, v in d["validator"]["decisiones"].items():
        lines.append(f"- {k}: **{v}**")
    lines.append(f"- Score promedio: **{d['validator']['score_promedio']}**")
    lines.append("")
    lines.append("## Certification")
    for k, v in d["certification"]["decisiones"].items():
        lines.append(f"- {k}: **{v}**")
    lines.append("")
    lines.append(f"## Duplicados: **{d['duplicados']}**")
    lines.append("")
    lines.append(f"## Errores: **{d['errores']['total']}** | Warnings: **{d['warnings']['total']}**")
    if d["errores"]["top"]:
        lines.append("### Top errores")
        for k, v in d["errores"]["top"].items():
            lines.append(f"- ({v}) {k}")
    lines.append("")
    lines.append("## Health")
    h = d["health"] or {}
    lines.append(f"- Status: **{h.get('status', 'unknown')}**")
    if h.get("checks"):
        lines.append("| check | estado |")
        lines.append("|---|---|")
        for name, c in h["checks"].items():
            lines.append(f"| {name} | {c.get('status') if isinstance(c, dict) else c} |")
    lines.append("")
    lines.append("## Top campos faltantes")
    for k, v in d["top_campos_faltantes"].items():
        lines.append(f"- {k}: **{v}**")
    lines.append("")
    lines.append("## Top campos corregidos (IA)")
    for c in d["top_campos_corregidos"]:
        lines.append(f"- {c['campo']}: **{c['corregidos']}**")
    lines.append("")
    return "\n".join(lines)
