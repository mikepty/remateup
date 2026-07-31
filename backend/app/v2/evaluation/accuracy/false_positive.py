"""FASE 13 — Parte 9: False Positive Report.

Encuentra sobre los datos reales:

- avisos descartados correctamente
- avisos descartados incorrectamente
- duplicados
- falsos duplicados
- avisos reales rechazados
- avisos inválidos aceptados
"""

import json
import re
from collections import Counter
from pathlib import Path
from typing import Optional

from backend.app.v2.evaluation.accuracy.corpus import (
    build_corpus, AVISO_POR_AVISO, REAL_BENCHMARK,
)

EDICTO_RE = re.compile(r"EDICTO\s+EMPLAZATORIO|EDICTO\s+DE\s+REMATE|EDICTO", re.I)
AVISO_RE = re.compile(r"AVISO\s+DE\s+REMATE", re.I)


def _expediente_key(text: str) -> str:
    """Clave canónica de expediente encontrada en un texto (dígitos base)."""
    m = re.search(r"(?:EXPEDIENTE|NEGOCIO|EXPE\.?|EXP\.?)\s*(?:N[°º.]?\s*)?([0-9]{3,}[0-9\-/ ]*)", text, re.I)
    if not m:
        m = re.search(r"([0-9]{4,}[0-9\-/]{2,})", text)
    if not m:
        return ""
    return re.sub(r"\s+", "", m.group(1))


def false_positive_report() -> dict:
    docs = build_corpus()
    pa = [d for d in docs if d.country == "PA"]
    co = [d for d in docs if d.country == "CO"]

    # 1) Descartados correctamente: páginas/avisos con EDICTO y sin AVISO DE REMATE.
    #    Los docs fuente="golden" son registros sintéticos de GT (no páginas reales).
    descartados_correctos = []
    descartados_incorrectos = []
    for d in pa:
        if d.source == "golden":
            continue
        tiene_edicto = bool(EDICTO_RE.search(d.text))
        tiene_aviso = bool(AVISO_RE.search(d.text))
        if tiene_edicto and not tiene_aviso:
            descartados_correctos.append({"documento": d.document_id, "motivo": "edicto_sin_aviso_de_remate"})
        if not tiene_edicto and not tiene_aviso:
            descartados_incorrectos.append({"documento": d.document_id, "motivo": "sin_aviso_ni_edicto_detectado"})

    # 2) Duplicados reales: mismo expediente en documentos distintos.
    por_expediente: dict[str, list[str]] = {}
    for d in pa + co:
        key = _expediente_key(d.text)
        if key:
            por_expediente.setdefault(key, []).append(d.document_id)
    duplicados = {k: v for k, v in por_expediente.items() if len(v) > 1}

    # 3) Falsos duplicados: prefijos de dígitos largos compartidos (expedientes distintos).
    falsos_duplicados = []
    claves = sorted(por_expediente.keys())
    for i, a in enumerate(claves):
        for b in claves[i + 1:]:
            if a != b and (a[:6] == b[:6] or a[-6:] == b[-6:]):
                falsos_duplicados.append({"expediente_a": a, "expediente_b": b, "motivo": "prefijo/sufijo_compartido"})

    # 4) Avisos reales rechazados: golden CO anclados cuya certificación NO es OK.
    avisos_reales_rechazados = []
    if AVISO_POR_AVISO.exists():
        avp = json.loads(AVISO_POR_AVISO.read_text(encoding="utf-8"))
        for run in avp.get("results", []):
            for aviso in run.get("avisos", []):
                decision = aviso.get("certification_decision")
                if decision not in ("VALID", "OK", "CERTIFIED", "INCOMPLETE"):
                    avisos_reales_rechazados.append({
                        "documento": run.get("document_id"),
                        "expediente": aviso.get("expediente"),
                        "decision": decision,
                        "motivo": "certificacion_rechaza_aviso_real",
                    })

    # 5) Avisos inválidos aceptados: certificación NO INVALID en documentos con
    #    texto de remate incompleto (benchmark).
    invalidos_aceptados = []
    if REAL_BENCHMARK.exists():
        bench = json.loads(REAL_BENCHMARK.read_text(encoding="utf-8"))
        for c in bench.get("comparaciones", []):
            if "error" in c:
                continue
            cert = ((c.get("parser_knowledge_ia") or {}).get("certification_decision") or "?")
            if cert not in ("INVALID", "N/A", "?"):
                invalidos_aceptados.append({
                    "documento": Path(c["file"]).stem,
                    "decision": cert,
                })

    return {
        "documentos_analizados": len(pa) + len(co),
        "pa": len(pa), "co": len(co),
        "avisos_descartados_correctamente": descartados_correctos,
        "avisos_descartados_incorrectamente": descartados_incorrectos,
        "duplicados": duplicados,
        "falsos_duplicados": falsos_duplicados,
        "avisos_reales_rechazados": avisos_reales_rechazados,
        "avisos_invalidos_aceptados": invalidos_aceptados,
        "totales": {
            "descartados_correctos": len(descartados_correctos),
            "descartados_incorrectos": len(descartados_incorrectos),
            "duplicados": len(duplicados),
            "falsos_duplicados": len(falsos_duplicados),
            "rechazados": len(avisos_reales_rechazados),
            "invalidos_aceptados": len(invalidos_aceptados),
        },
        "nota": "Determinista sobre el corpus real. Ningún aviso se modifica.",
    }


def fp_to_markdown(report: dict) -> str:
    lines = ["# False Positive Report (FASE 13, Parte 9)", ""]
    lines.append(f"- Documentos analizados: {report['documentos_analizados']} (PA: {report['pa']}, CO: {report['co']})")
    for seccion, key in (("Avisos descartados correctamente", "avisos_descartados_correctamente"),
                         ("Avisos descartados incorrectamente", "avisos_descartados_incorrectamente"),
                         ("Avisos reales rechazados", "avisos_reales_rechazados"),
                         ("Avisos inválidos aceptados", "avisos_invalidos_aceptados")):
        lines += ["", f"## {seccion}", ""]
        lines.append("| detalle |")
        lines.append("| --- |")
        for item in report.get(key, []):
            lines.append(f"| {json.dumps(item, ensure_ascii=False)} |")
    lines += ["", "## Duplicados", ""]
    lines.append("| expediente | documentos |")
    lines.append("| --- | --- |")
    for key, docs in report.get("duplicados", {}).items():
        lines.append(f"| {key} | {', '.join(docs)} |")
    lines += ["", "## Falsos duplicados", ""]
    lines.append("| expediente A | expediente B | motivo |")
    lines.append("| --- | --- | --- |")
    for item in report.get("falsos_duplicados", []):
        lines.append(f"| {item['expediente_a']} | {item['expediente_b']} | {item['motivo']} |")
    lines += ["", "## Totales", ""]
    lines.append("| concepto | cantidad |")
    lines.append("| --- | --- |")
    for k, v in report.get("totales", {}).items():
        lines.append(f"| {k} | {v} |")
    return "\n".join(lines)
