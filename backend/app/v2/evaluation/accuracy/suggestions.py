"""FASE 13 — Parte 4: Sugerencias automáticas (nunca aprobadas).

El sistema propone —solo como sugerencias—:

- nuevos alias (etiquetas alternativas reales)
- nuevas expresiones
- nuevos labels
- nuevos patrones

Detectadas del corpus real con frecuencia. NUNCA se aprueban automáticamente
y NUNCA modifican parsers ni Knowledge. Cada sugerencia documenta su evidencia.
"""

import re
from collections import Counter

FIELD_LABELS = {
    "expediente": ["EXPEDIENTE", "EXPE", "EXP"],
    "finca": ["FINCA", "FOLIO REAL"],
    "matricula": ["MATRICULA", "MATRÍCULA"],
    "precio_base": ["BASE DEL REMATE", "BASE", "PRECIO BASE", "VALOR BASE", "AVALUO COMERCIAL", "AVALÚO COMERCIAL"],
    "fianza_porcentaje": ["FIANZA", "FIANZA DEL POSTOR"],
    "minimo_porcentaje": ["PORCENTAJE MÍNIMO", "PORCENTAJE MINIMO", "PORCENTAJE"],
    "fecha_remate": ["FECHA DE REMATE", "FECHA DEL REMATE", "FECHA PROBABLE"],
    "demandante": ["DEMANDANTE", "ACTOR", "EJECUTANTE", "ACREEDOR"],
    "demandado": ["DEMANDADO", "DEUDOR", "EJECUTADO"],
    "juzgado": ["JUZGADO"],
    "lugar": ["LUGAR"],
    "municipio": ["MUNICIPIO"],
    "provincia": ["PROVINCIA"],
    "hora": ["HORA"],
}


def _variants(text: str, label: str) -> Counter:
    """Variantes reales de un label (con/sin acentos, espacios, guiones)."""
    pattern = "".join(rf"[{ch}{_alt(ch)}]?" if ch in "ÁÉÍÓÚÑáéíóúñ" else re.escape(ch) for ch in label)
    found = Counter()
    for m in re.finditer(pattern, text, re.I):
        found[m.group(0)] += 1
    return found


def _alt(ch: str) -> str:
    return {
        "Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U", "Ñ": "N",
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n",
    }.get(ch, "")


def generate_suggestions(texts_pa: list[str], texts_co: list[str]) -> dict:
    pa_joined = "\n".join(texts_pa)
    co_joined = "\n".join(texts_co)

    sugerencias = []
    for campo, labels in FIELD_LABELS.items():
        for label in labels:
            for pais, joined in (("PA", pa_joined), ("CO", co_joined)):
                variants = _variants(joined, label)
                for variant, count in variants.most_common(5):
                    if count == 0 or variant.upper() == label.upper():
                        continue
                    sugerencias.append({
                        "tipo": "alias",
                        "campo": campo,
                        "pais": pais,
                        "alias_sugerido": variant,
                        "label_referencia": label,
                        "frecuencia": count,
                        "estado": "SUGERENCIA",
                        "aprobado": False,
                    })

    # Expresiones recurrentes reales (2-4 palabras) por país.
    sugerencias.extend(_expression_suggestions(pa_joined, "PA"))
    sugerencias.extend(_expression_suggestions(co_joined, "CO"))

    # Labels nuevos: etiquetas en mayúsculas repetidas que no son labels conocidos.
    sugerencias.extend(_new_labels(pa_joined, "PA"))
    sugerencias.extend(_new_labels(co_joined, "CO"))

    # Panamá primero, luego por frecuencia descendente (determinista).
    sugerencias.sort(key=lambda s: (0 if s["pais"] == "PA" else 1, -s["frecuencia"], s["tipo"]))

    return {
        "total_sugerencias": len(sugerencias),
        "nunca_aprobadas_automaticamente": True,
        "sugerencias": sugerencias,
        "nota": "Las sugerencias requieren revisión humana. Nada se aprueba ni se aplica automáticamente.",
    }


_EXPR_RE = re.compile(r"\b[A-ZÁÉÍÓÚÑ]{3,}(?:\s+[A-ZÁÉÍÓÚÑ]{3,}){1,3}\b")


def _expression_suggestions(text: str, pais: str) -> list[dict]:
    counter = Counter()
    for m in _EXPR_RE.finditer(text):
        expr = m.group(0)
        if expr in ("AVISO DE REMATE", "EDICTO EMPLAZATORIO", "BASE DEL REMATE",
                    "FECHA DE REMATE", "AVALUO COMERCIAL", "AVALÚO COMERCIAL",
                    "CIRCUITO JUDICIAL DE", "REPUBLICA DE PANAMA", "REPÚBLICA DE PANAMÁ"):
            continue
        counter[expr] += 1
    out = []
    for expr, count in counter.most_common(15):
        if count < 2:
            continue
        out.append({
            "tipo": "expresion",
            "campo": "general",
            "pais": pais,
            "expresion": expr,
            "frecuencia": count,
            "estado": "SUGERENCIA",
            "aprobado": False,
        })
    return out


def _new_labels(text: str, pais: str) -> list[dict]:
    counter = Counter()
    for m in re.finditer(r"\b[A-ZÁÉÍÓÚÑ]{4,}\s*:", text):
        label = m.group(0)[:-1].strip()
        counter[label] += 1
    out = []
    known = {"AVISO", "EDICTO", "JUEZ", "JUEZA", "REPUBLICA", "REPÚBLICA", "ORGANO",
             "ÓRGANO", "DATOS", "LINDEROS", "OBSERVACIONES", "RESTRICCIONES", "NORTE",
             "SUR", "ESTE", "OESTE", "NOTIFIQ"}
    for label, count in counter.most_common(20):
        if label in known or count < 2:
            continue
        out.append({
            "tipo": "label_nuevo",
            "campo": "general",
            "pais": pais,
            "label": label,
            "frecuencia": count,
            "estado": "SUGERENCIA",
            "aprobado": False,
        })
    return out


def suggestions_to_markdown(report: dict) -> str:
    lines = ["# Sugerencias automáticas (FASE 13, Parte 4)", ""]
    lines.append(f"- Total sugerencias: {report['total_sugerencias']} | "
                 f"Aprobación automática: {report['nunca_aprobadas_automaticamente']}")
    for tipo in ("alias", "expresion", "label_nuevo"):
        lines += ["", f"## {tipo.upper()}", ""]
        lines.append("| campo | país | sugerencia | referencia | frecuencia |")
        lines.append("| --- | --- | --- | --- | --- |")
        for s in report["sugerencias"]:
            if s["tipo"] != tipo:
                continue
            detalle = s.get("alias_sugerido") or s.get("expresion") or s.get("label")
            ref = s.get("label_referencia", "-")
            lines.append(f"| {s['campo']} | {s['pais']} | {detalle} | {ref} | {s['frecuencia']} |")
    return "\n".join(lines)
