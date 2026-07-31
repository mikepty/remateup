import json
from typing import Any

V1_SOURCE = "v1"
V2_SOURCE = "v2"


def normalize_value(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip().upper()
    s = s.replace("Á", "A").replace("É", "E").replace("Í", "I")
    s = s.replace("Ó", "O").replace("Ú", "U").replace("Ñ", "N")
    s = s.replace(".", "").replace(",", "").replace("$", "").replace(" ", "")
    return s


COMPARISON_FIELDS = [
    "expediente", "demandante", "demandado", "base", "fianza_porcentaje",
    "minimo_porcentaje", "finca_matr", "codigo_ubicacion_prensa",
    "fecha", "hora", "lugar", "proceso", "categoria", "provincia",
    "descripcion", "plano", "lote_casa", "superficie",
    "periodico", "fecha_prensa", "pagina_prensa", "email_observaciones",
]


def compare_avisos(v1: dict, v2: dict) -> dict:
    result = {
        "matched": True,
        "field_comparison": {},
        "exact_matches": 0,
        "normalized_matches": 0,
        "mismatches": 0,
        "v1_only": 0,
        "v2_only": 0,
        "total_fields": len(COMPARISON_FIELDS),
        "match_score": 0.0,
    }

    v1_datos = v1.get("datos", v1)
    v2_datos = v2.get("datos", v2)

    for field in COMPARISON_FIELDS:
        v1_val = v1_datos.get(field)
        v2_val = v2_datos.get(field)

        v1_str = str(v1_val) if v1_val is not None else ""
        v2_str = str(v2_val) if v2_val is not None else ""

        exact = v1_str == v2_str
        norm = normalize_value(v1_val) == normalize_value(v2_val)

        comparison = {
            "v1": v1_val,
            "v2": v2_val,
            "exact_match": exact,
            "normalized_match": norm,
        }
        result["field_comparison"][field] = comparison

        if exact:
            result["exact_matches"] += 1
        elif norm:
            result["normalized_matches"] += 1
        else:
            result["mismatches"] += 1
            if v1_val and not v2_val:
                result["v1_only"] += 1
            elif v2_val and not v1_val:
                result["v2_only"] += 1

    total = result["total_fields"]
    if total > 0:
        result["match_score"] = round(
            (result["exact_matches"] + result["normalized_matches"] * 0.5) / total, 4
        )

    return result


def compare_documents(v1_avisos: list, v2_avisos: list) -> dict:
    comparisons = []
    for v1 in v1_avisos:
        best = None
        best_score = -1
        for v2 in v2_avisos:
            comp = compare_avisos(v1, v2)
            if comp["match_score"] > best_score:
                best_score = comp["match_score"]
                best = comp
        if best:
            comparisons.append(best)

    result = {
        "total_v1": len(v1_avisos),
        "total_v2": len(v2_avisos),
        "matched_avisos": len(comparisons),
        "average_match_score": round(
            sum(c["match_score"] for c in comparisons) / len(comparisons), 4
        ) if comparisons else 0,
        "total_exact_matches": sum(c["exact_matches"] for c in comparisons),
        "total_normalized_matches": sum(c["normalized_matches"] for c in comparisons),
        "total_mismatches": sum(c["mismatches"] for c in comparisons),
    }
    return result


def generate_report(v1_docs: dict, v2_docs: dict) -> str:
    lines = []
    lines.append("# Shadow Mode Comparison Report\n")
    lines.append(f"V1 documents processed: {len(v1_docs)}")
    lines.append(f"V2 documents processed: {len(v2_docs)}\n")

    total_v1_avisos = sum(len(av) for av in v1_docs.values())
    total_v2_avisos = sum(len(av) for av in v2_docs.values())
    lines.append(f"V1 avisos total: {total_v1_avisos}")
    lines.append(f"V2 avisos total: {total_v2_avisos}\n")

    all_comparisons = []
    for doc_id in v1_docs:
        if doc_id in v2_docs:
            comp = compare_documents(v1_docs[doc_id], v2_docs[doc_id])
            all_comparisons.append(comp)
            lines.append(f"## Document {doc_id}")
            lines.append(f"- V1 avisos: {comp['total_v1']}")
            lines.append(f"- V2 avisos: {comp['total_v2']}")
            lines.append(f"- Matched: {comp['matched_avisos']}")
            lines.append(f"- Match score: {comp['average_match_score']}")
            lines.append(f"- Exact matches: {comp['total_exact_matches']}")
            lines.append(f"- Normalized matches: {comp['total_normalized_matches']}")
            lines.append(f"- Mismatches: {comp['total_mismatches']}\n")

    if all_comparisons:
        lines.append("## Global Summary\n")
        lines.append(f"Average match score across all documents: {round(sum(c['average_match_score'] for c in all_comparisons) / len(all_comparisons), 4)}")
        lines.append(f"Total exact matches: {sum(c['total_exact_matches'] for c in all_comparisons)}")
        lines.append(f"Total mismatches: {sum(c['total_mismatches'] for c in all_comparisons)}")

    return "\n".join(lines)
