"""FASE 13 — Parte 8: Real Parser Gap Report.

Compara la cadena real contra el Ground Truth y localiza EXACTAMENTE dónde se
pierde cada campo:

  OCR → Parser → Knowledge → AI → Validator → Certification  vs  Ground Truth

Fuentes reales:
- PA: avisos canónicos del cliente (golden) y samples parser_validation (GT).
- CO: aviso_por_aviso.json de FASE 12 (16 avisos anclados en los PDFs reales).
- Benchmark real de FASE 12 (mismo OCR para los 3 modos).
"""

import json
import re
from collections import Counter
from pathlib import Path
from typing import Optional

from backend.app.v2.evaluation.accuracy.corpus import (
    build_corpus, GOLDEN_PATH, AVISO_POR_AVISO, REAL_BENCHMARK,
    SAMPLES_DIR, PARSER_VALIDATION,
)

GAP_FIELDS = ["expediente", "finca", "precio_base", "fecha_remate",
              "demandante", "demandado"]


def _norm(value) -> str:
    if value is None:
        return ""
    s = str(value)
    return re.sub(r"\s+", "", s.replace("$", "").replace("B/.", "").replace(".", "").replace(",", ""))


def _match(golden, actual) -> bool:
    g, a = _norm(golden), _norm(actual)
    if not g or not a:
        return False
    return g == a or g in a or a in g


def _co_golden_by_expediente() -> dict:
    data = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    out = {}
    for suite in data.get("test_suites", []):
        if suite.get("pais") != "CO":
            continue
        for aviso in suite.get("expected_avisos", []):
            out[str(aviso.get("expediente", "")).strip()] = aviso
    return out


def _co_gap(aviso_por_aviso: dict) -> list[dict]:
    golden_map = _co_golden_by_expediente()
    rows = []
    for run in aviso_por_aviso.get("results", []):
        for aviso in run.get("avisos", []):
            golden = golden_map.get(str(aviso.get("expediente", "")).strip(), {})
            result = aviso.get("pipeline_result", {})
            fields = result.get("fields", {}) or {}
            for fname in GAP_FIELDS:
                g = golden.get(fname, golden.get({"precio_base": "base"}.get(fname, fname), ""))
                if fname == "precio_base":
                    g = golden.get("base", "")
                if g is None or str(g) == "":
                    continue
                field = fields.get(fname) or {}
                parser_found = (field.get("source") == "parser" and field.get("status") == "FOUND")
                final_found = field.get("status") == "FOUND"
                rows.append({
                    "documento": run.get("document_id"),
                    "expediente": aviso.get("expediente"),
                    "campo": fname,
                    "golden": g,
                    "parser_found": parser_found,
                    "knowledge_found": False,
                    "ia_found": field.get("source") == "ai" and final_found,
                    "final_found": final_found,
                    "certificacion": aviso.get("certification_decision"),
                })
    return rows


def _pa_gap() -> list[dict]:
    rows = []
    # Avisos canónicos del cliente (samples pa/ -> golden).
    golden_map = {}
    data = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    for suite in data.get("test_suites", []):
        if suite.get("pais") == "PA":
            for a in suite.get("expected_avisos", []):
                golden_map[str(a.get("expediente", "")).strip()] = a

    from backend.app.v2.parser.factory import ParserFactory
    from backend.app.v2.parser.context import ParserContext
    parser = ParserFactory().get_parser("PA", "REMATE")

    def _run(text: str) -> dict:
        ctx = ParserContext(country="PA", document_type="REMATE", text=text)
        return {f: r.to_dict() if hasattr(r, "to_dict") else {"value": r.value, "status": "FOUND" if r.is_found else "NOT_FOUND"}
                for f, r in parser.parse(ctx).items()}

    for txt in sorted((SAMPLES_DIR / "pa").glob("*.txt")):
        text = txt.read_text(encoding="utf-8")
        g = golden_map.get(txt.stem)
        if not g:
            continue
        parsed = _run(text)
        for fname in GAP_FIELDS:
            if fname == "precio_base":
                gv = g.get("base")
            else:
                gv = g.get(fname)
            if gv is None or str(gv) == "":
                continue
            p = parsed.get(fname) or {}
            found = p.get("status") == "FOUND"
            rows.append({
                "documento": "pa_sample_" + txt.stem,
                "expediente": g.get("expediente"),
                "campo": fname,
                "golden": gv,
                "parser_found": found,
                "knowledge_found": False,
                "ia_found": False,
                "final_found": found,
                "certificacion": "N/A",
            })

    # Samples parser_validation (GT = expected/).
    expected_dir = PARSER_VALIDATION / "expected"
    for txt in sorted((PARSER_VALIDATION / "samples").glob("pa_aviso_*.txt")):
        exp_file = expected_dir / (txt.stem + ".json")
        if not exp_file.exists():
            continue
        expected = json.loads(exp_file.read_text(encoding="utf-8"))
        parsed = _run(txt.read_text(encoding="utf-8"))
        for fname, gdata in expected.items():
            if gdata.get("status") == "NOT_FOUND":
                continue
            gv = gdata.get("value")
            p = parsed.get(fname) or {}
            found = p.get("status") == "FOUND"
            value_ok = found and _match(gv, p.get("value"))
            rows.append({
                "documento": "pv_" + txt.stem,
                "expediente": re.sub(r"[^0-9-]", "", txt.stem),
                "campo": fname,
                "golden": gv,
                "parser_found": found,
                "knowledge_found": False,
                "ia_found": False,
                "final_found": found,
                "certificacion": "N/A",
            })
    return rows


def _benchmark_gap() -> list[dict]:
    """Evidencia IA sobre las imágenes reales PA (benchmark FASE 12, mismo OCR)."""
    rows = []
    if not REAL_BENCHMARK.exists():
        return rows
    bench = json.loads(REAL_BENCHMARK.read_text(encoding="utf-8"))
    for c in bench.get("comparaciones", []):
        if "error" in c or c.get("country") != "PA":
            continue
        parser_f = c.get("parser", {}).get("fields", {})
        ia_f = c.get("parser_knowledge_ia", {}).get("fields", {})
        for fname in GAP_FIELDS:
            p = parser_f.get(fname) or {}
            a = ia_f.get(fname) or {}
            rows.append({
                "documento": Path(c["file"]).stem,
                "expediente": "?",
                "campo": fname,
                "golden": None,
                "parser_found": p.get("status") == "FOUND",
                "knowledge_found": False,
                "ia_found": a.get("status") == "FOUND",
                "final_found": a.get("status") == "FOUND",
                "certificacion": ((c.get("parser_knowledge_ia") or {}).get("certification_decision")),
            })
    return rows


def parser_gap_report() -> dict:
    rows = []
    if AVISO_POR_AVISO.exists():
        rows.extend(_co_gap(json.loads(AVISO_POR_AVISO.read_text(encoding="utf-8"))))
    rows.extend(_pa_gap())
    rows.extend(_benchmark_gap())

    # Dónde se pierde cada campo (solo filas con golden real).
    con_golden = [r for r in rows if r.get("golden") is not None]
    perdidos = {}
    totales = Counter()
    for r in con_golden:
        key = r["campo"]
        totales[key] += 1
        if not r["final_found"]:
            perdido = perdidos.setdefault(key, Counter())
            if not r["parser_found"]:
                perdido["se_pierde_en_parser"] += 1
            else:
                perdido["se_pierde_despues_del_parser"] += 1
    perdidos = {k: dict(v) for k, v in perdidos.items()}

    # Resumen por etapa.
    etapas = {
        "ocr_pierde": 0, "parser_pierde": 0, "knowledge_pierde": 0,
        "ia_recupera": 0, "ia_no_recupera": 0,
        "validator_certificacion": Counter(),
    }
    for r in con_golden:
        if not r["parser_found"]:
            if r["ia_found"]:
                etapas["ia_recupera"] += 1
            else:
                etapas["parser_pierde"] += 1
        if r["certificacion"] and r["certificacion"] != "N/A":
            etapas["validator_certificacion"][r["certificacion"]] += 1

    return {
        "fuentes": {
            "co_avisos_anclados": len(_co_gap(json.loads(AVISO_POR_AVISO.read_text(encoding="utf-8")))) if AVISO_POR_AVISO.exists() else 0,
            "pa_canonicos_cliente": len([r for r in _pa_gap() if r["documento"].startswith("pa_sample")]),
            "pa_parser_validation": len([r for r in _pa_gap() if r["documento"].startswith("pv_")]),
            "pa_imagenes_benchmark": len([r for r in _benchmark_gap()]),
        },
        "filas_con_golden": len(con_golden),
        "donde_se_pierde_por_campo": perdidos,
        "resumen_por_etapa": {k: dict(v) if isinstance(v, Counter) else v for k, v in etapas.items()},
        "perdidas_totales": sum(sum(v.values()) for v in perdidos.values()),
        "rows": rows,
        "nota": "Knowledge no aplica: knowledge.db vacío (0 reglas). AI solo cubre los campos permitidos por policy.",
    }


def gap_to_markdown(report: dict) -> str:
    lines = ["# Real Parser Gap Report (FASE 13, Parte 8)", ""]
    lines.append(f"- Filas con ground truth: {report['filas_con_golden']}")
    lines.append(f"- Pérdidas totales vs GT: {report['perdidas_totales']}")
    lines += ["", "## Dónde se pierde cada campo", ""]
    lines.append("| campo | se pierde en parser | se pierde después |")
    lines.append("| --- | --- | --- |")
    for campo, data in report["donde_se_pierde_por_campo"].items():
        lines.append(f"| {campo} | {data.get('se_pierde_en_parser', 0)} | {data.get('se_pierde_despues_del_parser', 0)} |")
    lines += ["", "## Resumen por etapa", ""]
    for k, v in report["resumen_por_etapa"].items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## Detalle por documento (primeros 40)", ""]
    lines.append("| doc | expediente | campo | golden | parser | IA | final | cert |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in report["rows"][:40]:
        lines.append(
            f"| {r['documento']} | {r['expediente']} | {r['campo']} | {str(r['golden'])[:30]} | "
            f"{'SÍ' if r['parser_found'] else 'no'} | {'SÍ' if r['ia_found'] else 'no'} | "
            f"{'SÍ' if r['final_found'] else 'no'} | {r['certificacion']} |"
        )
    return "\n".join(lines)
