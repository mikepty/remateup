"""FASE 13 — Parte 13: Dashboard de Precisión.

Muestra (Panamá primero):

- Precisión Panamá / Colombia
- Recall, Precision, F1, Accuracy
- Cobertura por campo, por país, por parser
- Campos IA / Knowledge / Parser / Perdidos
"""

import json
from collections import Counter
from pathlib import Path
from typing import Optional

from backend.app.v2.evaluation.accuracy.corpus import (
    build_corpus, AVISO_POR_AVISO, GOLDEN_PATH, PARSER_VALIDATION, SAMPLES_DIR,
)
from backend.app.v2.evaluation.accuracy.parser_gap import parser_gap_report

GAP_FIELDS = ["expediente", "finca", "precio_base", "fecha_remate",
              "demandante", "demandado"]


def _metrics(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    accuracy = tp / (tp + fp + fn) if (tp + fp + fn) else 0.0
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "accuracy": round(accuracy, 4),
    }


def _pa_metrics() -> dict:
    """Métricas PA sobre avisos con golden (canónicos del cliente + parser_validation)."""
    return _accumulate(_pa_rows())


def _golden_for(sample_id: str) -> Optional[dict]:
    data = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    for suite in data.get("test_suites", []):
        if suite.get("pais") == "PA":
            for a in suite.get("expected_avisos", []):
                if str(a.get("expediente", "")).strip() == sample_id:
                    return a
    return None


def _pa_rows() -> list[dict]:
    rows = []
    from backend.app.v2.parser.factory import ParserFactory
    from backend.app.v2.parser.context import ParserContext
    parser = ParserFactory().get_parser("PA", "REMATE")

    def _parse(text: str) -> dict:
        ctx = ParserContext(country="PA", document_type="REMATE", text=text)
        return {f: (r.value if r.is_found else None) for f, r in parser.parse(ctx).items()}

    for txt in sorted((SAMPLES_DIR / "pa").glob("*.txt")):
        golden = _golden_for(txt.stem)
        if not golden:
            continue
        parsed = _parse(txt.read_text(encoding="utf-8"))
        for fname in GAP_FIELDS:
            gv = golden.get("base" if fname == "precio_base" else fname)
            if gv is None or str(gv) == "":
                continue
            pv = parsed.get(fname)
            rows.append({"campo": fname, "golden": str(gv), "valor": str(pv) if pv else None})

    for txt in sorted((PARSER_VALIDATION / "samples").glob("pa_aviso_*.txt")):
        exp_file = PARSER_VALIDATION / "expected" / (txt.stem + ".json")
        if not exp_file.exists():
            continue
        expected = json.loads(exp_file.read_text(encoding="utf-8"))
        parsed = _parse(txt.read_text(encoding="utf-8"))
        for fname, gdata in expected.items():
            if gdata.get("status") == "NOT_FOUND":
                continue
            pv = parsed.get(fname)
            rows.append({"campo": fname, "golden": str(gdata.get("value")),
                         "valor": str(pv) if pv else None})
    return rows


def _accumulate(rows: list[dict]) -> dict:
    tp = fp = fn = 0
    por_campo: dict[str, dict] = {}
    for r in rows:
        match = _values_match(str(r["golden"]), r["valor"])
        if r["valor"] is None:
            fn += 1
        elif match:
            tp += 1
        else:
            fp += 1
        bucket = por_campo.setdefault(r["campo"], {"tp": 0, "fp": 0, "fn": 0})
        if r["valor"] is None:
            bucket["fn"] += 1
        elif match:
            bucket["tp"] += 1
        else:
            bucket["fp"] += 1
    metrics = _metrics(tp, fp, fn)
    metrics["por_campo"] = {k: _metrics(v["tp"], v["fp"], v["fn"]) for k, v in por_campo.items()}
    return metrics


def _values_match(golden: str, actual) -> bool:
    if actual is None:
        return False
    def norm(s: str) -> str:
        return "".join(ch for ch in s if ch.isalnum()).upper()
    g, a = norm(golden), norm(actual)
    return g == a or g in a or a in g


def _co_metrics() -> dict:
    if not AVISO_POR_AVISO.exists():
        return _metrics(0, 0, 0)
    avp = json.loads(AVISO_POR_AVISO.read_text(encoding="utf-8"))
    tp = fp = fn = 0
    por_campo: dict[str, dict] = {}
    for run in avp.get("results", []):
        for aviso in run.get("avisos", []):
            comparison = aviso.get("comparison", {})
            per = comparison.get("per_field", {})
            for campo, data in per.items():
                bucket = por_campo.setdefault(campo, {"tp": 0, "fp": 0, "fn": 0})
                bucket["tp"] += data.get("tp", 0)
                bucket["fp"] += data.get("fp", 0)
                bucket["fn"] += data.get("fn", 0)
    for bucket in por_campo.values():
        tp += bucket["tp"]
        fp += bucket["fp"]
        fn += bucket["fn"]
    metrics = _metrics(tp, fp, fn)
    metrics["por_campo"] = {k: _metrics(v["tp"], v["fp"], v["fn"]) for k, v in por_campo.items()}
    return metrics


def _cobertura(gap: dict, pa_metrics: dict, co_metrics: dict) -> dict:
    per = {}
    for campo in GAP_FIELDS:
        pa = pa_metrics.get("por_campo", {}).get(campo, {})
        co = co_metrics.get("por_campo", {}).get(campo, {})
        per[campo] = {
            "pa_tp": pa.get("tp", 0), "pa_fn": pa.get("fn", 0),
            "co_tp": co.get("tp", 0), "co_fn": co.get("fn", 0),
            "cobertura_pa": round(pa.get("recall", 0), 4),
            "cobertura_co": round(co.get("recall", 0), 4),
        }
    return per


def accuracy_dashboard() -> dict:
    pa = _pa_metrics()
    co = _co_metrics()
    gap = parser_gap_report()
    docs = build_corpus()

    por_parser = {
        "PA REMATE": pa,
        "CO REMATE": co,
    }
    return {
        "panama": pa,
        "colombia": co,
        "por_parser": por_parser,
        "cobertura_por_campo": _cobertura(gap, pa, co),
        "cobertura_por_pais": {
            "PA": {"documentos": len([d for d in docs if d.country == "PA"]),
                   "avisos": sum(len(d.avisos) for d in docs if d.country == "PA"),
                   "recall": pa.get("recall"), "precision": pa.get("precision"),
                   "f1": pa.get("f1")},
            "CO": {"documentos": len([d for d in docs if d.country == "CO"]),
                   "avisos": sum(len(d.avisos) for d in docs if d.country == "CO"),
                   "recall": co.get("recall"), "precision": co.get("precision"),
                   "f1": co.get("f1")},
        },
        "campos_ia": {"fuente": "benchmark FASE 12", "detalle": gap["resumen_por_etapa"].get("ia_recupera", 0)},
        "campos_knowledge": 0,
        "campos_parser": gap["filas_con_golden"] - gap["resumen_por_etapa"].get("parser_pierde", 0),
        "campos_perdidos": gap["perdidas_totales"],
        "nota": "Métricas reales: golden del cliente + parser_validation (PA) y aviso_por_aviso anclado (CO).",
    }


def dashboard_to_markdown(d: dict) -> str:
    lines = ["# Dashboard de Precisión (FASE 13)", ""]
    lines.append("## Panamá (prioridad)")
    lines.append(f"- Precision: {d['panama']['precision']} | Recall: {d['panama']['recall']} | "
                 f"F1: {d['panama']['f1']} | Accuracy: {d['panama']['accuracy']}")
    lines.append("## Colombia")
    lines.append(f"- Precision: {d['colombia']['precision']} | Recall: {d['colombia']['recall']} | "
                 f"F1: {d['colombia']['f1']} | Accuracy: {d['colombia']['accuracy']}")
    lines += ["", "## Cobertura por campo", ""]
    lines.append("| campo | PA recall | CO recall |")
    lines.append("| --- | --- | --- |")
    for campo, c in d["cobertura_por_campo"].items():
        lines.append(f"| {campo} | {c['cobertura_pa']} | {c['cobertura_co']} |")
    lines += ["", "## Cobertura por país", ""]
    for pais in ("PA", "CO"):
        c = d["cobertura_por_pais"][pais]
        lines.append(f"- {pais}: docs {c['documentos']} | avisos {c['avisos']} | recall {c['recall']} | f1 {c['f1']}")
    lines += ["", "## Campos por origen", ""]
    lines.append(f"- IA: {d['campos_ia']}")
    lines.append(f"- Knowledge: {d['campos_knowledge']}")
    lines.append(f"- Parser: {d['campos_parser']}")
    lines.append(f"- Perdidos: {d['campos_perdidos']}")
    return "\n".join(lines)
