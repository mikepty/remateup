"""FASE 11 — Comparativa (Parte 11): Solo Parser vs Parser + IA.

Per-field TP / FP / FN / Precision / Recall / F1 computed against the
golden dataset records (evaluation/golden_dataset/records.json).
"""

from pathlib import Path
from typing import Any, Optional

from backend.app.v2.evaluation.production.runner import ProductionDatasetRunner

GOLDEN_RECORDS_PATH = Path(__file__).resolve().parents[5] / "evaluation" / "golden_dataset" / "records.json"

FIELD_ALIASES = {
    "expediente": {"expediente", "numero_expediente", "n_expediente"},
    "demandante": {"demandante", "actor", "ejecutante"},
    "demandado": {"demandado", "deudor", "ejecutado"},
    "precio_base": {"precio_base", "base", "base_remate"},
    "fianza_porcentaje": {"fianza_porcentaje"},
    "minimo_porcentaje": {"minimo_porcentaje"},
    "fecha_remate": {"fecha_remate", "fecha", "fecha_aviso"},
    "finca": {"finca", "finca_matr"},
    "provincia": {"provincia"},
    "lugar": {"lugar"},
}


def _normalize(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip().lower()
    # FASE 12 — bug real corregido: los valores de moneda del golden se
    # almacenan como float (181080000.0); quitar el "." convertía el valor
    # en 10x (1810800000) y hacía imposible cualquier match de precio.
    if s.endswith(".0") and s[:-2].lstrip("-").isdigit():
        s = s[:-2]
    s = s.replace("$", "").replace(",", "").replace(".", "").replace(" ", "")
    return s


def values_match(expected: Any, actual: Any) -> bool:
    if expected is None or expected == "":
        return True
    return _normalize(expected) == _normalize(actual)


def find_field(fields: dict, field_name: str) -> Optional[dict]:
    aliases = FIELD_ALIASES.get(field_name, {field_name})
    for alias in aliases:
        if alias in fields:
            return fields[alias]
    return None


def compare_document(predicted: dict, expected: dict, fields: list[str]) -> dict:
    per_field = {}
    for field_name in fields:
        expected_value = expected.get(field_name)
        found = find_field(predicted, field_name)
        actual_value = found.get("value") if found else None
        actual_status = found.get("status") if found else "NOT_FOUND"

        if expected_value is None or expected_value == "":
            tp = fp = fn = 0
        elif values_match(expected_value, actual_value) and actual_status == "FOUND":
            tp, fp, fn = 1, 0, 0
        elif actual_status == "FOUND":
            tp, fp, fn = 0, 1, 0
        else:
            tp, fp, fn = 0, 0, 1
        per_field[field_name] = {"tp": tp, "fp": fp, "fn": fn}
    return per_field


def aggregate(per_doc: list[dict], fields: list[str]) -> dict:
    totals = {f: {"tp": 0, "fp": 0, "fn": 0} for f in fields}
    for doc in per_doc:
        for field_name, counts in doc.items():
            for k in ("tp", "fp", "fn"):
                totals[field_name][k] += counts[k]

    per_field_metrics = {}
    for field_name, t in totals.items():
        precision = t["tp"] / (t["tp"] + t["fp"]) if (t["tp"] + t["fp"]) else 0.0
        recall = t["tp"] / (t["tp"] + t["fn"]) if (t["tp"] + t["fn"]) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        per_field_metrics[field_name] = {
            "tp": t["tp"],
            "fp": t["fp"],
            "fn": t["fn"],
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }

    total_tp = sum(t["tp"] for t in totals.values())
    total_fp = sum(t["fp"] for t in totals.values())
    total_fn = sum(t["fn"] for t in totals.values())
    p = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 0.0
    r = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 0.0
    f1 = (2 * p * r / (p + r)) if (p + r) else 0.0
    return {
        "per_field": per_field_metrics,
        "totals": {"tp": total_tp, "fp": total_fp, "fn": total_fn,
                   "precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4)},
    }


def load_golden_records(country: str) -> list[dict]:
    import json

    if not GOLDEN_RECORDS_PATH.exists():
        return []
    data = json.loads(GOLDEN_RECORDS_PATH.read_text(encoding="utf-8"))
    records = []
    for suite in data.get("test_suites", []):
        if suite.get("pais") != country:
            continue
        for aviso in suite.get("expected_avisos", []):
            if aviso.get("expediente"):
                records.append(aviso)
    return records


def compare_corpus(
    samples_dir: str,
    country: str = "CO",
    fields: Optional[list[str]] = None,
    golden_records: Optional[list[dict]] = None,
) -> dict:
    """Runs each sample TXT twice (parser-only vs parser+AI) and compares
    both against the golden records."""
    from pathlib import Path

    fields = fields or ["expediente", "demandante", "demandado", "precio_base",
                        "fianza_porcentaje", "minimo_porcentaje", "fecha_remate",
                        "lugar", "provincia"]
    golden = golden_records
    if golden is None:
        golden = load_golden_records(country)
    golden_by_id = {g.get("expediente"): g for g in golden}

    parser_only = ProductionDatasetRunner(use_ai=False)
    with_ai = ProductionDatasetRunner(use_ai=True)

    docs_only = []
    docs_ai = []
    not_in_golden = []
    total = 0

    for path in sorted(Path(samples_dir).glob("*.txt")):
        doc_id = path.stem
        expected = golden_by_id.get(doc_id)
        if expected is None:
            not_in_golden.append(doc_id)
            continue
        total += 1
        r_only = parser_only.run_text(path.read_text(encoding="utf-8"), country, document_id=doc_id)
        r_ai = with_ai.run_text(path.read_text(encoding="utf-8"), country, document_id=doc_id)
        docs_only.append(compare_document(r_only.get("fields", {}), expected, fields))
        docs_ai.append(compare_document(r_ai.get("fields", {}), expected, fields))

    return {
        "country": country,
        "documents": total,
        "not_in_golden": not_in_golden,
        "parser_only": aggregate(docs_only, fields),
        "parser_plus_ai": aggregate(docs_ai, fields),
        "fields": fields,
    }
