from typing import Any

COMPARISON_FIELDS = [
    "expediente", "demandante", "demandado", "base", "fianza_porcentaje",
    "minimo_porcentaje", "finca_matr", "codigo_ubicacion_prensa",
    "fecha", "hora", "lugar", "proceso", "categoria", "provincia",
    "descripcion", "plano", "lote_casa", "superficie",
    "periodico", "fecha_prensa", "pagina_prensa", "email_observaciones",
]

FIELD_PRIORITY = {
    "expediente": "critical", "demandante": "critical", "demandado": "critical",
    "base": "critical", "finca_matr": "critical",
    "fianza_porcentaje": "high", "minimo_porcentaje": "high", "fecha": "high",
    "hora": "medium", "lugar": "medium", "proceso": "medium",
    "categoria": "medium", "provincia": "medium",
    "descripcion": "medium", "plano": "low", "lote_casa": "low",
    "superficie": "low", "periodico": "low", "fecha_prensa": "low",
    "pagina_prensa": "low", "email_observaciones": "low",
}


def normalize(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip().upper()
    for a, b in (("Á", "A"), ("É", "E"), ("Í", "I"), ("Ó", "O"), ("Ú", "U"), ("Ñ", "N")):
        s = s.replace(a, b)
    s = s.replace(".", "").replace(",", "").replace("$", "").replace(" ", "")
    return s


def compare_field(v1: Any, v2: Any) -> dict:
    v1_str = str(v1) if v1 is not None else ""
    v2_str = str(v2) if v2 is not None else ""
    exact = v1_str == v2_str
    norm = normalize(v1) == normalize(v2)
    return {
        "v1": v1,
        "v2": v2,
        "exact_match": exact,
        "normalized_match": norm,
        "v1_empty": v1 is None or v1_str.strip() == "",
        "v2_empty": v2 is None or v2_str.strip() == "",
        "v1_only": (v1 is not None and v1_str.strip() != "" and (v2 is None or v2_str.strip() == "")),
        "v2_only": (v2 is not None and v2_str.strip() != "" and (v1 is None or v1_str.strip() == "")),
    }


def compare_avisos(v1_datos: dict, v2_datos: dict) -> dict:
    results = {}
    exact_matches = 0
    norm_matches = 0
    mismatches = 0
    v1_only = 0
    v2_only = 0

    for field in COMPARISON_FIELDS:
        c = compare_field(v1_datos.get(field), v2_datos.get(field))
        results[field] = c
        if c["exact_match"]:
            exact_matches += 1
        elif c["normalized_match"]:
            norm_matches += 1
        else:
            mismatches += 1
        if c["v1_only"]:
            v1_only += 1
        if c["v2_only"]:
            v2_only += 1

    total = len(COMPARISON_FIELDS)
    return {
        "fields": results,
        "exact_matches": exact_matches,
        "normalized_matches": norm_matches,
        "mismatches": mismatches,
        "v1_only_values": v1_only,
        "v2_only_values": v2_only,
        "total_fields": total,
        "exact_accuracy": round(exact_matches / total, 4) if total else 0,
        "normalized_accuracy": round((exact_matches + norm_matches) / total, 4) if total else 0,
    }


def aggregate_results(comparisons: list[dict]) -> dict:
    field_totals = {f: {"exact": 0, "norm": 0, "mismatch": 0, "count": 0} for f in COMPARISON_FIELDS}
    total_exact = 0
    total_norm = 0
    total_mismatch = 0
    total_fields_acc = 0

    for comp in comparisons:
        for field, result in comp["fields"].items():
            field_totals[field]["count"] += 1
            if result["exact_match"]:
                field_totals[field]["exact"] += 1
                total_exact += 1
            elif result["normalized_match"]:
                field_totals[field]["norm"] += 1
                total_norm += 1
            else:
                field_totals[field]["mismatch"] += 1
                total_mismatch += 1
            total_fields_acc += 1

    field_summary = {}
    for field, ft in field_totals.items():
        if ft["count"] > 0:
            field_summary[field] = {
                "count": ft["count"],
                "exact_accuracy": round(ft["exact"] / ft["count"], 4),
                "normalized_accuracy": round((ft["exact"] + ft["norm"]) / ft["count"], 4),
                "priority": FIELD_PRIORITY.get(field, "low"),
            }

    return {
        "field_summary": field_summary,
        "global_exact_accuracy": round(total_exact / total_fields_acc, 4) if total_fields_acc else 0,
        "global_normalized_accuracy": round((total_exact + total_norm) / total_fields_acc, 4) if total_fields_acc else 0,
        "total_field_comparisons": total_fields_acc,
        "total_exact_matches": total_exact,
        "total_mismatches": total_mismatch,
        "avisos_compared": len(comparisons),
        "critical_accuracy": _critial_accuracy(field_summary),
    }


def _critial_accuracy(field_summary: dict) -> dict:
    critical = {f: s for f, s in field_summary.items() if FIELD_PRIORITY.get(f) == "critical"}
    high = {f: s for f, s in field_summary.items() if FIELD_PRIORITY.get(f) == "high"}
    return {
        "critical_fields": len(critical),
        "critical_exact_accuracy": round(
            sum(s["exact_accuracy"] for s in critical.values()) / len(critical), 4
        ) if critical else 0,
        "high_fields": len(high),
        "high_exact_accuracy": round(
            sum(s["exact_accuracy"] for s in high.values()) / len(high), 4
        ) if high else 0,
    }
