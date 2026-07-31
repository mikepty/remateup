"""FASE 12 — Parte 8: Real Dataset Benchmark.

Ejecuta de nuevo `backend/data/uploads/` con todos los documentos reales y
compara sobre EL MISMO texto OCR real:

  Parser (solo)
  vs Parser+Knowledge
  vs Parser+Knowledge+IA

Muestra únicamente diferencias reales (campos cuyo estado/valor cambia entre
modos). No hay estimaciones: cada modo consume el mismo OCR real del documento.
"""

import json
import time
from pathlib import Path
from typing import Any, Optional

from backend.app.v2.parser.factory import ParserFactory
from backend.app.v2.parser.context import ParserContext
from backend.app.v2.production.smoke import run_text_pipeline
from backend.app.v2.parser.ai.integration import AIEnhancedPipeline

UPLOADS_DIR = Path(__file__).resolve().parents[4] / "data" / "uploads"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"

CO_PDFS = [
    "SEJURE_28_JULIO_2025_JANETH_RODRIGUEZ_parte1.pdf",
    "SEJURE_28_JULIO_2025_JANETH_RODRIGUEZ_parte2.pdf",
    "SEJURE_28_JULIO_2025_JANETH_RODRIGUEZ_parte3.pdf",
]

PA_IMAGES = [
    "21ce358d_1.jpg", "21ce358d_2.jpg", "5b48a468_1.jpg",
    "9a1ef910_1.jpg", "9a1ef910_2.jpg", "c84594ff_1.jpg",
    "c84594ff_2.jpg", "dfe0e387_1.jpg", "dfe0e387_2.jpg",
    "IMG-20260710-WA0014.jpg", "IMG-20260710-WA0018.jpg",
    "imagen1.jpg", "imagen2.jpg",
]


def _ocr_text(path: Path, cache: dict) -> str:
    from backend.app.v2.evaluation.production.avisos import _cached_text

    key = str(path).replace("\\", "/")
    if key in cache:
        text = _cached_text(cache[key])
        if text:
            return text
    name = path.name
    for ckey, value in cache.items():
        if Path(str(ckey)).name == name:
            text = _cached_text(value)
            if text:
                return text
    from backend.app.v2.ocr.processor import OCRProcessor

    doc = OCRProcessor().process_pdf(str(path)) if path.suffix.lower() == ".pdf" else OCRProcessor().process_image(str(path))
    text = (doc.full_text or "").strip()
    cache[key] = text
    return text


def _parser_only_fields(text: str, country: str) -> dict:
    parser = ParserFactory().get_parser(country.upper(), "REMATE")
    ctx = ParserContext(country=country.upper(), document_type="REMATE", text=text)
    return {
        fname: {"status": pr.status, "value": pr.value}
        for fname, pr in parser.parse(ctx).items()
        if pr.is_found
    }


def _fields_view(result: dict) -> dict:
    return {
        fname: {"status": fdata.get("status"), "value": fdata.get("value")}
        for fname, fdata in (result.get("fields", {}) or {}).items()
        if isinstance(fdata, dict)
    }


def _mode_summary(result: dict, fields: dict) -> dict:
    return {
        "fields": fields,
        "validation_decision": (result.get("validation", {}) or {}).get("decision"),
        "certification_decision": ((result.get("certification", {}) or {}).get("all_avisos", [{}]) or [{}])[0].get("decision"),
        "errors": result.get("errors", []),
    }


def _status_value(f: dict) -> tuple[str, str]:
    if not f:
        return "NOT_FOUND", ""
    return f.get("status", "NOT_FOUND"), str(f.get("value") or "")


def _field_diffs(parser_f: dict, knowledge_f: dict, ai_f: dict) -> list[dict]:
    all_fields = sorted(set(parser_f) | set(knowledge_f) | set(ai_f))
    diffs: list[dict] = []
    for fname in all_fields:
        p, k, a = _status_value(parser_f.get(fname)), _status_value(knowledge_f.get(fname)), _status_value(ai_f.get(fname))
        if p == k == a:
            continue
        diffs.append({
            "campo": fname,
            "parser": {"status": p[0], "value": p[1]},
            "parser_knowledge": {"status": k[0], "value": k[1]},
            "parser_knowledge_ia": {"status": a[0], "value": a[1]},
        })
    return diffs


def run_real_benchmark(
    uploads_dir: str = "",
    use_ai: bool = True,
    ocr_cache: Optional[dict] = None,
    out_dir: Optional[str] = None,
) -> dict:
    base = Path(uploads_dir) if uploads_dir else UPLOADS_DIR
    cache: dict = dict(ocr_cache or {})
    if not cache:
        cached_file = OUTPUT_DIR / "real_ocr_texts.json"
        if cached_file.exists():
            try:
                cache = json.loads(cached_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                cache = {}

    files = [base / f for f in CO_PDFS if (base / f).exists()]
    files += [base / f for f in PA_IMAGES if (base / f).exists()]
    if not files:
        files = sorted(p for p in base.iterdir() if p.suffix.lower() in (".pdf", ".jpg", ".jpeg", ".png"))

    ai_pipeline = AIEnhancedPipeline()
    comparisons: list[dict] = []
    total_ms = 0.0

    for path in files:
        country = "CO" if path.suffix.lower() == ".pdf" else "PA"
        doc_id = path.stem
        start = time.perf_counter()
        text = _ocr_text(path, cache)
        if not text:
            comparisons.append({"file": str(path), "error": "OCR sin texto"})
            continue

        p_fields = _parser_only_fields(text, country)
        k_result = run_text_pipeline(text, country=country, document_id=doc_id, source_type="benchmark")
        k_fields = _fields_view(k_result)
        a_result = ai_pipeline.run_text(text, country=country, document_id=doc_id,
                                        source_type="benchmark", use_ai=use_ai)
        a_fields = _fields_view(a_result)

        diffs = _field_diffs(p_fields, k_fields, a_fields)
        kd = ((k_result.get("validation", {}) or {}).get("decision"),
              ((k_result.get("certification", {}) or {}).get("all_avisos", [{}]) or [{}])[0].get("decision"))
        ad = ((a_result.get("validation", {}) or {}).get("decision"),
              ((a_result.get("certification", {}) or {}).get("all_avisos", [{}]) or [{}])[0].get("decision"))
        comparisons.append({
            "file": str(path),
            "country": country,
            "ocr_chars": len(text),
            "parser": _mode_summary({"fields": p_fields, "validation": {}, "certification": {}, "errors": []}, p_fields),
            "parser_knowledge": _mode_summary(k_result, k_fields),
            "parser_knowledge_ia": _mode_summary(a_result, a_fields),
            "diferencias_reales": diffs,
            "decisiones_certificacion_pk_vs_pkia": {"parser_knowledge": kd, "parser_knowledge_ia": ad},
            "tiempo_ms": round((time.perf_counter() - start) * 1000, 2),
        })
        total_ms += (time.perf_counter() - start) * 1000

    total_diffs = sum(len(c.get("diferencias_reales", [])) for c in comparisons if "error" not in c)
    report = {
        "dataset": str(base),
        "documentos": len(comparisons),
        "modos": ["parser", "parser_knowledge", "parser_knowledge_ia"],
        "diferencias_reales_totales": total_diffs,
        "tiempo_total_ms": round(total_ms, 2),
        "comparaciones": comparisons,
        "resumen": {
            "campos_que_cambian_entre_modos": sorted({
                d["campo"] for c in comparisons if "error" not in c for d in c.get("diferencias_reales", [])
            }),
        },
        "nota": "Cada modo consume el mismo texto OCR real del documento; solo se listan diferencias reales.",
    }

    if out_dir:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "real_benchmark.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
        )
        (out / "real_benchmark.md").write_text(benchmark_to_markdown(report), encoding="utf-8")
    return report


def benchmark_to_markdown(report: dict) -> str:
    lines = [
        "# Real Dataset Benchmark (FASE 12)", "",
        f"- Dataset: `{report['dataset']}`",
        f"- Documentos: **{report['documentos']}**",
        f"- Diferencias reales totales: **{report['diferencias_reales_totales']}**",
        f"- Tiempo total: **{report['tiempo_total_ms']} ms**",
        f"- Modos: {', '.join(report['modos'])}",
        "",
        "## Diferencias reales por documento", "",
    ]
    for c in report["comparaciones"]:
        if "error" in c:
            lines.append(f"### {Path(c['file']).name} — ERROR: {c['error']}")
            continue
        lines.append(f"### {Path(c['file']).name} ({c['country']}, {c['ocr_chars']} chars)")
        if not c["diferencias_reales"]:
            lines.append("_Sin diferencias entre modos._")
            continue
        lines.append("| campo | parser | parser+knowledge | parser+knowledge+IA |")
        lines.append("|---|---|---|---|")
        for d in c["diferencias_reales"]:
            p = f"{d['parser']['status']}:{d['parser']['value']}"
            k = f"{d['parser_knowledge']['status']}:{d['parser_knowledge']['value']}"
            a = f"{d['parser_knowledge_ia']['status']}:{d['parser_knowledge_ia']['value']}"
            lines.append(f"| {d['campo']} | {p} | {k} | {a} |")
        kd = (c["parser_knowledge"].get("certification_decision"), c["parser_knowledge"].get("validation_decision"))
        ad = (c["parser_knowledge_ia"].get("certification_decision"), c["parser_knowledge_ia"].get("validation_decision"))
        lines.append("")
        lines.append(f"- Certification +K vs +K+IA: **{kd[0]}** vs **{ad[0]}** | Validator: **{kd[1]}** vs **{ad[1]}**")
        lines.append("")
    lines += ["", f"## Campos que cambian entre modos", ""]
    for f in report["resumen"]["campos_que_cambian_entre_modos"]:
        lines.append(f"- {f}")
    lines += ["", f"_Nota: {report['nota']}_", ""]
    return "\n".join(lines)
