"""FASE 13 — Parte 7: Knowledge Analytics.

knowledge.db está vacío (0 reglas, 0 correcciones). Este módulo analiza POR QUÉ
y calcula —como reporte, sin crear reglas—:

- qué reglas serían útiles
- qué reglas nunca existirán
- qué reglas deberían aprenderse
- qué reglas deberían ignorarse
"""

import json
import re
from collections import Counter
from pathlib import Path
from typing import Optional

from backend.app.v2.evaluation.accuracy.corpus import build_corpus, _golden_avisos
from backend.app.v2.knowledge.repository import KnowledgeRepository

KNOWLEDGE_DB = Path(__file__).resolve().parents[2] / "knowledge" / "knowledge.db"


def _db_counts(db_path: Optional[str] = None) -> dict:
    try:
        repo = KnowledgeRepository(db_path=db_path or str(KNOWLEDGE_DB))
        rules = repo.get_rules() if hasattr(repo, "get_rules") else []
        corrections = repo.get_corrections() if hasattr(repo, "get_corrections") else []
        return {"reglas": len(rules), "correcciones": len(corrections)}
    except Exception as e:
        return {"reglas": 0, "correcciones": 0, "error": str(e)}


# Reglas candidatas: label real (con frecuencia) -> campo del catálogo.
RULE_CANDIDATES = [
    ("expediente", r"EXPEDIENTE\s+N[°º.]?\s*([0-9]+[0-9\-/ ]*)", "PA"),
    ("expediente", r"NEGOCIO\s+N[°º.]?\s*([0-9]+[0-9\-/ ]*)", "PA"),
    ("expediente", r"E\s*-\s*([0-9]+[0-9\-/ ]*)", "PA"),
    ("precio_base", r"AVAL[ÚU]O\s+COMERCIAL\s*:\s*\$?\s*([\d.,]+)", "PA"),
    ("precio_base", r"VALOR\s+BASE\s*[:\s]*B?/?\.?\s*([\d.,]+)", "PA"),
    ("precio_base", r"BASE\s+DEL\s+REMATE\s*[:\s]*B?/?\.?\s*([\d.,]+)", "PA"),
    ("finca", r"FINCA\s+N[°º.]?\s*([0-9]+[0-9\s]*)", "PA"),
    ("finca", r"FOLIO\s+REAL\s+N[°º.]?\s*([0-9]+)", "PA"),
    ("juzgado", r"JUZGADO\s+[A-ZÁÉÍÓÚÑ0-9\s,.\"']+", "PA"),
    ("fecha_remate", r"FECHA\s+DE\s+REMATE\s*[:\s]*(\d{1,2}\s+DE\s+[A-ZÁÉÍÓÚÑ]+\s+DE\s+\d{4})", "PA"),
    ("precio_base", r"AVAL[ÚU]O\s+COMERCIAL\s*:\s*\$?\s*([\d.,]+)", "CO"),
    ("precio_base", r"BASE\s+DEL\s+REMATE\s*[:\s]*\$?\s*([\d.,]+)", "CO"),
    ("expediente", r"(?:EJ|DIV)\s*\.\s*[A-Z]{0,3}\s*\.?\s*No\.[0-9]+-?\s*([0-9]{3,})", "CO"),
    ("precio_base", r"\$\s*([\d]{1,3}(?:\.[\d]{3})+)\s*$", "CO"),
    ("demandado", r"Vs\.[A-ZÁÉÍÓÚÑ\s,\.]+", "CO"),
    ("demandante", r"([A-ZÁÉÍÓÚÑ\s,\.]+?)\s*Vs\.", "CO"),
    ("fianza_porcentaje", r"FIANZA\s+DEL\s+POSTOR\s*:\s*(\d+)%", "CO"),
    ("minimo_porcentaje", r"PORCENTAJE\s+M[ÍI]NIMO\s*:\s*(\d+)%", "CO"),
]


def knowledge_analytics(db_path: Optional[str] = None) -> dict:
    docs = build_corpus()
    db = _db_counts(db_path)

    # Frecuencia de evidencia real por candidato.
    candidates: list[dict] = []
    per_pais: dict[str, int] = {"PA": 0, "CO": 0}
    for campo, pattern, pais in RULE_CANDIDATES:
        n = 0
        ejemplos = Counter()
        for d in docs:
            if d.country != pais:
                continue
            for m in re.finditer(pattern, d.text, re.I):
                n += 1
                ejemplos[m.group(1).strip() if m.lastindex else m.group(0).strip()] += 1
        per_pais[pais] += n
        candidates.append({
            "campo": campo, "pais": pais, "patron": pattern,
            "frecuencia_evidencia": n,
            "ejemplos": dict(ejemplos.most_common(3)),
        })

    utiles = [c for c in candidates if c["frecuencia_evidencia"] >= 3]
    aprendibles = [c for c in candidates if 1 <= c["frecuencia_evidencia"] < 3]
    ignorables = [c for c in candidates if c["frecuencia_evidencia"] == 0]
    nunca_existiran = _never_rules(docs)

    return {
        "knowledge_db": db,
        "por_que_esta_vacia": {
            "reglas": 0 if db.get("reglas", 0) == 0 else db.get("reglas"),
            "razones": [
                "El pipeline no aprende: AIFeedbackTracker registra métricas sin escribir reglas.",
                "Las reglas se crean solo por revisión humana (aprobación manual).",
                "No existe mecanismo de extracción automática de correcciones al conocimiento.",
                "La tabla de correcciones requiere un flujo de feedback que nunca se activó en producción.",
            ],
        },
        "reglas_utiles": sorted(utiles, key=lambda c: -c["frecuencia_evidencia"]),
        "reglas_deberian_aprenderse": sorted(aprendibles, key=lambda c: -c["frecuencia_evidencia"]),
        "reglas_deberian_ignorarse": ignorables,
        "reglas_que_nunca_existiran": nunca_existiran,
        "evidencia_por_pais": per_pais,
        "reglas_creadas": 0,
        "nota": "Reporte analítico. NINGUNA regla se crea ni se aprueba aquí.",
    }


def _never_rules(docs) -> list[dict]:
    """Campos del catálogo sin evidencia textual real -> no habrá regla posible."""
    joined_pa = "\n".join(d.text for d in docs if d.country == "PA")
    joined_co = "\n".join(d.text for d in docs if d.country == "CO")
    checks = [
        ("hora", r"\bHORA\b", joined_pa, joined_co),
        ("fecha_publicacion", r"FECHA\s+DE\s+PUBLICACI[ÓO]N", joined_pa, joined_co),
        ("descripcion", r"DESCRIPCI[ÓO]N", joined_pa, joined_co),
        ("avaluo", r"AVAL[ÚU]O", joined_pa, joined_co),
        ("lugar", r"\bLUGAR\b", joined_pa, joined_co),
        ("proceso", r"\bPROCESO\b", joined_pa, joined_co),
    ]
    out = []
    for campo, pattern, pa, co in checks:
        n = len(re.findall(pattern, pa, re.I)) + len(re.findall(pattern, co, re.I))
        out.append({"campo": campo, "evidencia_textual_total": n})
    return out


def analytics_to_markdown(report: dict) -> str:
    lines = ["# Knowledge Analytics (FASE 13, Parte 7)", ""]
    lines.append(f"- knowledge.db: {report['knowledge_db']}")
    lines += ["", "## ¿Por qué está vacía?", ""]
    for razon in report["por_que_esta_vacia"]["razones"]:
        lines.append(f"- {razon}")
    for seccion, key in (("Reglas que serían útiles", "reglas_utiles"),
                         ("Reglas que deberían aprenderse", "reglas_deberian_aprenderse"),
                         ("Reglas que deberían ignorarse", "reglas_deberian_ignorarse")):
        lines += ["", f"## {seccion}", ""]
        lines.append("| campo | país | patrón | frecuencia | ejemplos |")
        lines.append("| --- | --- | --- | --- | --- |")
        for c in report.get(key, []):
            ej = ", ".join(f"{v}:{f}" for v, f in c.get("ejemplos", {}).items())
            lines.append(f"| {c['campo']} | {c['pais']} | `{c['patron']}` | {c['frecuencia_evidencia']} | {ej} |")
    lines += ["", "## Reglas que nunca existirán (sin evidencia real)", ""]
    lines.append("| campo | evidencia textual total |")
    lines.append("| --- | --- |")
    for r in report.get("reglas_que_nunca_existiran", []):
        lines.append(f"| {r['campo']} | {r['evidencia_textual_total']} |")
    lines.append("")
    lines.append("> NINGUNA regla se creó: este reporte es analítico.")
    return "\n".join(lines)
