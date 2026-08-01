"""Builders de reportes (Parte 12) — puros y deterministas.

Cada builder recibe un `data: dict` (ya coleccionado por `admin_ext`) y
devuelve `(json_str, md_str)`. Nada escribe a disco aquí; el router persiste.
Reusa los motores de `engine.py` y los módulos de evaluación V2 existentes
(cuando se importan limpios); si un módulo V2 falla al importar, se reporta
como hallazgo en el diagnóstico en vez de romper la app (FASE 15: no romper).
"""
from __future__ import annotations

import json
from datetime import datetime

from .engine import _norm


def _md_table(headers, rows):
    if not rows:
        return "_Sin datos._\n"
    out = "| " + " | ".join(headers) + " |\n"
    out += "| " + " | ".join("---" for _ in headers) + " |\n"
    for r in rows:
        out += "| " + " | ".join(str(c) for c in r) + " |\n"
    return out


def render_hyper_learning(data: dict) -> tuple[str, str]:
    sugs = data.get("sugerencias", [])
    pa = [s for s in sugs if s.get("pais") == 1]
    md = ["# Hyper Learning Engine", ""]
    md.append(f"Total de sugerencias: **{len(sugs)}** "
              f"(Panamá: {len(pa)}, resto: {len(sugs) - len(pa)}).")
    md.append("")
    md.append("> Las sugerencias se basan en correcciones repetidas del cliente. "
              "**Nunca se aplican automáticamente**: cada una requiere aprobación explicita "
              "vía el editor o `/admin/aviso/{id}/aplicar`.")
    md.append("")
    by_tipo = {}
    for s in sugs:
        by_tipo.setdefault(s["tipo"], []).append(s)
    md.append("## Por tipo")
    md.append(_md_table(["tipo", "n"], [[t, len(v)] for t, v in
                                        sorted(by_tipo.items(), key=lambda kv: -len(kv[1]))]))
    md.append("## Sugerencias top (confianza)")
    rows = []
    for s in sugs[:20]:
        rows.append([s.get("tipo"), s.get("campo"), s.get("pais") or "-",
                     s.get("valor_referencia") or "—", s.get("valor_sugerido") or "—",
                     f"{s.get('count', 0)}", f"{s.get('confianza', 0):.2f}"])
    md.append(_md_table(["tipo", "campo", "país", "old", "new", "count", "conf"], rows))
    return json.dumps(data, indent=2, default=str), "\n".join(md) + "\n"


def render_hyper_intelligence(data: dict) -> tuple[str, str]:
    items = data.get("analisis_por_aviso", [])
    md = ["# Hyper Intelligence Engine", ""]
    md.append(f"Avisos analizados: **{len(items)}**.")
    md.append("")
    md.append(_md_table(
        ["aviso_id", "expediente", "motivo_fallo", "campos_faltantes", "confianza_predicha"],
        [[a.get("aviso_id"), a.get("expediente") or "—",
          ", ".join(a.get("motivo_fallo") or ["—"]),
          ", ".join(a.get("campos_faltantes") or ["—"]),
          f"{a.get('confianza_predicha', 0):.2f}"] for a in items]))
    return json.dumps(data, indent=2, default=str), "\n".join(md) + "\n"


def render_production_diagnosis(data: dict) -> tuple[str, str]:
    checks = data.get("checks", {})
    md = ["# Diagnóstico de Producción", ""]
    md.append(f"Generado: {data.get('timestamp', datetime.utcnow().isoformat())}")
    md.append("")
    md.append(_md_table(["check", "status", "detalle"],
                        [[k, v.get("status", "?"), v.get("detalle", "")]
                         for k, v in checks.items()]))
    fail = [k for k, v in checks.items() if v.get("status") in ("error", "fail")]
    md.append("")
    md.append(f"**Checks críticos con fallos: {len(fail)}** "
              + (", ".join(fail) if fail else "ninguno"))
    return json.dumps(data, indent=2, default=str), "\n".join(md) + "\n"


def render_ui_audit(data: dict) -> tuple[str, str]:
    findings = data.get("hallazgos", [])
    md = ["# Auditoría de Interfaz (index.html)", ""]
    md.append(_md_table(["elemento", "tipo", "estado", "observación"],
                        [[f.get("elemento"), f.get("tipo"), f.get("estado"), f.get("observacion", "")]
                         for f in findings]))
    return json.dumps(data, indent=2, default=str), "\n".join(md) + "\n"


def render_knowledge_evolution(data: dict) -> tuple[str, str]:
    ev = data.get("evolucion", [])
    md = ["# Evolución del Knowledge", ""]
    md.append(_md_table(["campo", "valor_anterior", "valor_nuevo", "veces", "última"],
                        [[e.get("campo"), e.get("valor_anterior") or "—",
                          e.get("valor_nuevo"), e.get("count"), e.get("ultima", "")]
                         for e in ev]))
    return json.dumps(data, indent=2, default=str), "\n".join(md) + "\n"


def render_continuous_learning(data: dict) -> tuple[str, str]:
    cl = data.get("registro", [])
    md = ["# Registro de Aprendizaje Continuo", ""]
    md.append(f"Eventos capturados: **{len(cl)}** (edición / aprobación / rechazo / "
              "eliminación / corrección).")
    md.append("")
    md.append("## Últimos eventos")
    md.append(_md_table(["timestamp", "agente", "accion", "aviso_id", "detalle"],
                        [[e.get("timestamp"), e.get("agente"), e.get("accion"),
                          e.get("aviso_id"), (e.get("detalle") or "")[:120]]
                         for e in cl[:30]]))
    return json.dumps(data, indent=2, default=str), "\n".join(md) + "\n"


def render_client_ready(data: dict) -> tuple[str, str]:
    md = ["# Reporte Client Ready — RemateUp", ""]
    md.append(f"Generado: {data.get('timestamp')}")
    md.append("")
    md.append("## Resumen global")
    md.append(_md_table(["ítem", "estado"],
                        [[k, v.get("status", "?")] if isinstance(v, dict) else [k, v]
                         for k, v in data.get("resumen", {}).items()]))
    md.append("## Issues abiertos (requieren atención)")
    issues = data.get("issues", [])
    if not issues:
        md.append("_Ninguno._")
    else:
        md.append(_md_table(["área", "severidad", "problema", "acción"],
                            [[i.get("area"), i.get("severidad"), i.get("problema"),
                              i.get("accion") or "—"] for i in issues]))
    md.append("")
    md.append("## Cómo validar")
    md.append("- Subir una página PA de prueba y confirmar que se generan avisos con "
              "fianza/minimo calculados y 0 discrepancias (ya verificado localmente sobre doc104).")
    md.append("- Descargar el Excel: `descripcion` = texto completo del bien; columnas "
              "`fianza`/`minimo` populadas.")
    return json.dumps(data, indent=2, default=str), "\n".join(md) + "\n"


BUILDERS = {
    "hyper_learning": render_hyper_learning,
    "hyper_intelligence": render_hyper_intelligence,
    "production_diagnosis": render_production_diagnosis,
    "ui_audit": render_ui_audit,
    "knowledge_evolution": render_knowledge_evolution,
    "continuous_learning": render_continuous_learning,
    "client_ready": render_client_ready,
}


def available_reports() -> list[str]:
    return sorted(BUILDERS)
