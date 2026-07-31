"""FASE 13 — Parte 6: Coverage Analyzer Real.

Indica sobre el corpus real (no el golden teórico):

- campos que aparecen realmente
- campos que casi nunca aparecen
- campos que nunca aparecen
- campos exclusivos de Panamá
- campos exclusivos de Colombia
- campos que sobran (en el catálogo pero sin evidencia real)
- campos que faltan (evidencia real sin campo en el catálogo)

Determinista: solo mide lo que existe en los documentos reales.
"""

import json
import re
from collections import Counter
from typing import Optional

from backend.app.v2.schema.definitions import get_definitions
from backend.app.v2.evaluation.accuracy.corpus import (
    CorpusDocument, build_corpus, _golden_avisos,
)

# Etiquetas/patrones reales que evidencian cada campo en texto crudo OCR.
# Las claves son nombres SEMÁNTICOS; _CATALOG_ALIAS las mapea al catálogo real.
FIELD_EVIDENCE = {
    "expediente": [r"EXPEDIENTE", r"NEGOCIO", r"E\.J\.E\.?"],
    "finca": [r"FINCA", r"FOLIO\s+REAL"],
    "matricula": [r"MATR[ÍI]CULA"],
    "precio_base": [r"BASE\s+(?:DEL\s+)?REMATE", r"AVAL[ÚU]O", r"PRECIO\s+BASE", r"VALOR\s+BASE"],
    "fianza_porcentaje": [r"FIANZA\s+DEL\s+POSTOR"],
    "minimo_porcentaje": [r"PORCENTAJE\s+M[ÍI]NIMO"],
    "fecha_remate": [r"FECHA\s+DE\s+REMATE", r"FECHA\s+(?:DEL\s+)?REMATE"],
    "hora": [r"\bHORA\b", r"\d{1,2}:\d{2}\s*(?:A\.?\s*M\.?|P\.?\s*M\.?|AM|PM)"],
    "demandante": [r"DEMANDANTE", r"ACTOR", r"EJECUTANTE", r"ACREEDOR"],
    "demandado": [r"DEMANDADO", r"DEUDOR", r"EJECUTADO"],
    "juzgado": [r"JUZGADO"],
    "lugar": [r"LUGAR", r"EN\s+EL\s+MUNICIPIO\s+DE", r"CIRCUITO\s+JUDICIAL"],
    "municipio": [r"MUNICIPIO", r"DEL\s+MUNICIPIO\s+DE"],
    "provincia": [r"PROVINCIA"],
    "fecha_publicacion": [r"FECHA\s+DE\s+PUBLICACI[ÓO]N"],
    "avaluo": [r"AVAL[ÚU]O\s+COMERCIAL"],
    "descripcion": [r"DESCRIPCI[ÓO]N", r"LINDEROS", r"UBICADO"],
    "proceso": [r"PROCESO", r"EJECUTIVO", r"HIPOTECARIO"],
}

# Nombre semántico -> campo real del catálogo (si existe).
_CATALOG_ALIAS = {
    "expediente": "expediente",
    "finca": "finca",
    "matricula": "finca",          # matrícula inmobiliaria = finca (alias finca_matr)
    "precio_base": "precio_base",
    "fianza_porcentaje": "fianza_porcentaje",
    "minimo_porcentaje": "minimo_porcentaje",
    "fecha_remate": "fecha_remate",
    "hora": "hora",
    "demandante": "demandante",
    "demandado": "demandado",
    "juzgado": "juzgado",          # NO existe en el catálogo -> campo que falta
    "lugar": "lugar",
    "municipio": "municipio",      # NO existe en el catálogo -> campo que falta
    "provincia": "provincia",
    "fecha_publicacion": "fecha_publicacion",  # NO existe -> campo que falta
    "avaluo": "precio_base",       # avalúo comercial es evidencia de precio base
    "descripcion": "descripcion",
    "proceso": "proceso",
}


def _evidence_count(text: str, patterns: list[str]) -> int:
    n = 0
    for p in patterns:
        n += len(re.findall(p, text, re.I))
    return n


def coverage_analysis(docs: Optional[list[CorpusDocument]] = None) -> dict:
    docs = docs or build_corpus()
    catalog = {d.field_name for d in get_definitions()}

    by_country: dict[str, dict] = {}
    evidence_per_country: dict[str, dict] = {}
    for country in ("PA", "CO"):
        texts = [d.text for d in docs if d.country == country]
        joined = "\n".join(texts)
        evidence: dict[str, int] = {}
        for fname, patterns in FIELD_EVIDENCE.items():
            evidence[fname] = _evidence_count(joined, patterns)
        evidence_per_country[country] = evidence

        # Campos presentes según golden real (ground truth con valores).
        golden_keys: Counter = Counter()
        for aviso in _golden_avisos(country):
            for key, value in aviso.items():
                if value is not None and str(value) != "":
                    golden_keys[key] += 1

        by_country[country] = {
            "evidencia_textual": dict(sorted(evidence.items(), key=lambda kv: -kv[1])),
            "campos_con_valor_en_golden": dict(golden_keys.most_common()),
        }

    # Síntesis sobre el catálogo (33 campos), usando el mapeo semántico->catálogo.
    catalog_report = {}
    evidencia_por_campo: dict[str, dict] = {}
    for sem_name, ev_pa in evidence_per_country["PA"].items():
        ev_co = evidence_per_country["CO"].get(sem_name, 0)
        campo = _CATALOG_ALIAS.get(sem_name)
        if campo is None or campo not in catalog:
            continue
        acumulado = evidencia_por_campo.setdefault(campo, {"evidencia_pa": 0, "evidencia_co": 0})
        acumulado["evidencia_pa"] += ev_pa
        acumulado["evidencia_co"] += ev_co
    for fname in sorted(catalog):
        ev = evidencia_por_campo.get(fname, {"evidencia_pa": 0, "evidencia_co": 0})
        pa, co = ev["evidencia_pa"], ev["evidencia_co"]
        catalog_report[fname] = {
            "evidencia_pa": pa,
            "evidencia_co": co,
            "nunca_aparece": pa == 0 and co == 0,
            "casi_nunca_aparece": 0 < pa + co <= 2,
            "aparece_realmente": pa + co > 2,
            "exclusivo_pa": pa > 0 and co == 0,
            "exclusivo_co": co > 0 and pa == 0,
            "en_catalogo": True,
        }

    # Campos con evidencia real pero que NO tienen campo en el catálogo.
    missing = {}
    for sem_name, patterns in FIELD_EVIDENCE.items():
        campo = _CATALOG_ALIAS.get(sem_name)
        if campo is not None and campo in catalog:
            continue
        ev_pa = evidence_per_country["PA"].get(sem_name, 0)
        ev_co = evidence_per_country["CO"].get(sem_name, 0)
        if ev_pa + ev_co == 0:
            continue  # sin evidencia real no es un campo que falte
        missing[sem_name] = {
            "evidencia_pa": ev_pa,
            "evidencia_co": ev_co,
            "en_catalogo": False,
        }

    return {
        "total_documentos": len(docs),
        "documentos_por_pais": {c: len([d for d in docs if d.country == c]) for c in ("PA", "CO")},
        "por_pais": by_country,
        "por_campo_catalogo": catalog_report,
        "campos_nunca_aparecen": [f for f, r in catalog_report.items() if r["nunca_aparece"]],
        "campos_casi_nunca_aparecen": [f for f, r in catalog_report.items() if r["casi_nunca_aparece"]],
        "campos_exclusivos_pa": [f for f, r in catalog_report.items() if r["exclusivo_pa"]],
        "campos_exclusivos_co": [f for f, r in catalog_report.items() if r["exclusivo_co"]],
        "campos_sobran": [f for f, r in catalog_report.items() if r["nunca_aparece"]],
        "campos_faltan": missing,
        "nota": "Cobertura medida sobre el corpus real (OCR de uploads + samples + parser_validation + golden).",
    }


def coverage_to_markdown(report: dict) -> str:
    lines = ["# Coverage Analyzer Real (FASE 13)", ""]
    lines.append(f"- Documentos: {report['total_documentos']} | "
                 f"PA: {report['documentos_por_pais']['PA']} | CO: {report['documentos_por_pais']['CO']}")
    lines += ["", "## Por país (Panamá primero)", ""]
    for country in ("PA", "CO"):
        data = report["por_pais"][country]
        lines += ["", f"### {country}", ""]
        lines.append("| campo | evidencia textual |")
        lines.append("| --- | --- |")
        for fname, count in data["evidencia_textual"].items():
            lines.append(f"| {fname} | {count} |")
        lines += ["", f"### {country} — campos con valor en golden", ""]
        lines.append("| campo | avisos con valor |")
        lines.append("| --- | --- |")
        for fname, count in data["campos_con_valor_en_golden"].items():
            lines.append(f"| {fname} | {count} |")
    lines += ["", "## Por campo del catálogo", ""]
    lines.append("| campo | PA | CO | nunca | casi nunca | exclusivo PA | exclusivo CO |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for fname, r in sorted(report["por_campo_catalogo"].items()):
        lines.append(
            f"| {fname} | {r['evidencia_pa']} | {r['evidencia_co']} | "
            f"{'SÍ' if r['nunca_aparece'] else ''} | {'SÍ' if r['casi_nunca_aparece'] else ''} | "
            f"{'SÍ' if r['exclusivo_pa'] else ''} | {'SÍ' if r['exclusivo_co'] else ''} |"
        )
    lines += ["", "## Campos que faltan (evidencia real sin campo en catálogo)", ""]
    if report["campos_faltan"]:
        lines.append("| campo | PA | CO |")
        lines.append("| --- | --- | --- |")
        for fname, r in report["campos_faltan"].items():
            lines.append(f"| {fname} | {r['evidencia_pa']} | {r['evidencia_co']} |")
    else:
        lines.append("Ninguno.")
    lines.append("")
    return "\n".join(lines)
