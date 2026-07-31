"""FASE 12 — Orchestrator: ejecuta las Partes 1-9 sobre el dataset real y
genera todos los artefactos en output/.

  output/aviso_por_aviso.json     (Parte 2)
  output/pipeline_trace.json      (Parte 3)
  output/ai_feedback.json         (Parte 4)
  output/knowledge_impact.{json,md} (Parte 5)
  output/field_quality.{json,md}  (Parte 6)
  output/production_dashboard.{json,md} (Parte 7)
  output/real_benchmark.{json,md} (Parte 8)
  output/architecture_audit.{json,md} (Parte 9)

Determinista y auditable: cada artefacto documenta su origen y sus datos.
"""

import json
import sys
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from backend.app.v2.evaluation.production.avisos import AvisoRunner, avisos_to_json
from backend.app.v2.evaluation.production.trace import build_traces, traces_to_json
from backend.app.v2.evaluation.production.ai_feedback import AIFeedbackTracker
from backend.app.v2.evaluation.production.knowledge_impact import generate_knowledge_impact_report
from backend.app.v2.evaluation.production.field_quality import (
    generate_field_quality_report, write_field_quality_report,
)
from backend.app.v2.evaluation.production.dashboard import generate_production_dashboard
from backend.app.v2.evaluation.production.benchmark import run_real_benchmark
from backend.app.v2.evaluation.production.architecture_audit import run_architecture_audit

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
UPLOADS_DIR = Path(__file__).resolve().parents[4] / "data" / "uploads"

CO_PDFS = [
    "SEJURE_28_JULIO_2025_JANETH_RODRIGUEZ_parte1.pdf",
    "SEJURE_28_JULIO_2025_JANETH_RODRIGUEZ_parte2.pdf",
    "SEJURE_28_JULIO_2025_JANETH_RODRIGUEZ_parte3.pdf",
]

GOLDEN_PATH = Path(__file__).resolve().parents[5] / "evaluation" / "golden_dataset" / "records.json"


AUDIT_PATH = Path(__file__).resolve().parents[3] / "v2" / "parser" / "ai" / "audit" / "ai_audit.jsonl"


def _read_audit_log(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    except (json.JSONDecodeError, OSError):
        return []


def load_golden_avisos(country: str = "CO") -> list[dict]:
    data = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    for suite in data.get("test_suites", []):
        if suite.get("pais") == country:
            return list(suite.get("expected_avisos", []))
    return []


def assign_golden_to_pdfs(ocr_cache: dict, golden: list[dict], pdf_paths: list[str]) -> dict:
    """Asigna cada aviso golden al primer PDF cuyo OCR real contiene su
    expediente (determinista). Las claves del dict resultante son las rutas
    absolutas de `pdf_paths` (mismas que consume AvisoRunner)."""
    from backend.app.v2.evaluation.production.avisos import _cached_text

    text_by_name: dict[str, str] = {}
    for key, value in ocr_cache.items():
        name = Path(str(key)).name
        text_by_name.setdefault(name, _cached_text(value))

    assigned: dict[str, list[dict]] = {p: [] for p in pdf_paths}
    for aviso in golden:
        target = "".join(ch for ch in str(aviso.get("expediente") or "") if ch.isdigit())
        placed = False
        for pdf in pdf_paths:
            text = text_by_name.get(Path(pdf).name, "")
            if text and target and "".join(ch for ch in text if ch.isdigit()).find(target) >= 0:
                assigned[pdf].append(aviso)
                placed = True
                break
        if not placed:
            assigned[pdf_paths[0]].append(aviso)
    return assigned


def load_ocr_cache() -> dict:
    cached = OUTPUT_DIR / "real_ocr_texts.json"
    if cached.exists():
        try:
            return json.loads(cached.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def run_phase12(use_ai: bool = True, uploads_dir: str = "", out_dir: Optional[str] = None) -> dict:
    load_dotenv("backend/.env")
    out = Path(out_dir) if out_dir else OUTPUT_DIR
    out.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    ocr_cache = load_ocr_cache()
    golden = load_golden_avisos("CO")
    pdf_paths = [str(UPLOADS_DIR / f) if uploads_dir == "" else str(Path(uploads_dir) / f)
                 for f in CO_PDFS]
    pdf_paths = [p for p in pdf_paths if Path(p).exists()]
    golden_by_pdf = assign_golden_to_pdfs(ocr_cache, golden, pdf_paths)

    # Partes 2 + 3 + 4: aviso por aviso con traza y feedback de IA
    audit_baseline = len(_read_audit_log(AUDIT_PATH))
    runner = AvisoRunner(use_ai=use_ai, ocr_cache=dict(ocr_cache))
    aviso_run = runner.run_directory(pdf_paths, "CO", golden_by_pdf)
    (out / "aviso_por_aviso.json").write_text(avisos_to_json(aviso_run), encoding="utf-8")

    traces: list[dict] = []
    tracker = AIFeedbackTracker()
    all_results: list[dict] = []
    final_status_by_doc: dict[str, dict] = {}
    for run in aviso_run.get("results", []):
        traces.extend(build_traces(run))
        for aviso in run.get("avisos", []):
            result = aviso.get("pipeline_result", {})
            all_results.append(result)
            tracker.ingest_result(result, documento=run.get("documento"))
            fields = result.get("fields", {}) or {}
            final_status_by_doc[aviso.get("aviso_id", "")] = {
                f: d.get("status") for f, d in fields.items() if isinstance(d, dict)
            }
    (out / "pipeline_trace.json").write_text(traces_to_json(traces), encoding="utf-8")

    # Parte 6: Field Quality Report (avisos + resultados del benchmark de imágenes PA)
    benchmark = run_real_benchmark(uploads_dir=uploads_dir, use_ai=use_ai,
                                   ocr_cache=dict(ocr_cache), out_dir=str(out))
    for c in benchmark.get("comparaciones", []):
        if "error" in c:
            continue
        all_results.append(_benchmark_compare_to_result(c, "parser_knowledge_ia"))
        b_fields = ((c.get("parser_knowledge_ia") or {}).get("fields") or {})
        final_status_by_doc[Path(c["file"]).stem] = {
            f: d.get("status") for f, d in b_fields.items() if isinstance(d, dict)
        }

    # Parte 4: ingiere SOLO las decisiones de IA registradas en audit durante
    # esta ejecución (el audit log acumula llamadas de ejecuciones previas).
    audit_by_doc: dict[str, list[dict]] = {}
    for a in _read_audit_log(AUDIT_PATH)[audit_baseline:]:
        audit_by_doc.setdefault(str(a.get("documento", "")), []).append(a)
    for documento, entries in audit_by_doc.items():
        tracker.ingest_audit_entries(entries, result={"fields": final_status_by_doc.get(documento, {})})

    ai_feedback = {"summary": tracker.summary(), "entries": tracker.to_list(),
                   "cache": tracker.cache_summary()}
    (out / "ai_feedback.json").write_text(json.dumps(ai_feedback, ensure_ascii=False, indent=1), encoding="utf-8")

    # Parte 5: Knowledge Impact Report
    knowledge_report = generate_knowledge_impact_report(out_dir=str(out))

    field_report = generate_field_quality_report(all_results)
    write_field_quality_report(field_report, str(out))

    # Parte 7: Production Dashboard
    dashboard = generate_production_dashboard(
        all_results,
        aviso_run={
            "avisos_procesados": sum(r.get("avisos_procesados", 0) for r in aviso_run.get("results", [])),
            "avisos_anclados": sum(r.get("avisos_anclados", 0) for r in aviso_run.get("results", [])),
            "golden_avisos": sum(r.get("golden_avisos", 0) for r in aviso_run.get("results", [])),
        },
        ai_feedback_summary=tracker.summary(),
        knowledge_report=knowledge_report,
        out_dir=str(out),
    )

    # Parte 9: Architecture Audit
    audit = run_architecture_audit(out_dir=str(out))

    phase_report = {
        "fase": 12,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "use_ai": use_ai,
        "tiempo_total_ms": round((time.perf_counter() - started) * 1000, 2),
        "audit_log_baseline": audit_baseline,
        "audit_log_final": len(_read_audit_log(AUDIT_PATH)),
        "artefactos": {
            "aviso_por_aviso": "aviso_por_aviso.json",
            "pipeline_trace": "pipeline_trace.json",
            "ai_feedback": "ai_feedback.json",
            "knowledge_impact": "knowledge_impact.json / knowledge_impact.md",
            "field_quality": "field_quality.json / field_quality.md",
            "production_dashboard": "production_dashboard.json / production_dashboard.md",
            "real_benchmark": "real_benchmark.json / real_benchmark.md",
            "architecture_audit": "architecture_audit.json / architecture_audit.md",
        },
        "resumen": {
            "pdfs_procesados": len(pdf_paths),
            "avisos_anclados": sum(r.get("avisos_anclados", 0) for r in aviso_run.get("results", [])),
            "avisos_procesados": sum(r.get("avisos_procesados", 0) for r in aviso_run.get("results", [])),
            "precision_promedio_aviso_por_aviso": {
                r.get("document_id"): r.get("metrics", {}).get("precision")
                for r in aviso_run.get("results", [])
            },
            "f1_promedio_aviso_por_aviso": {
                r.get("document_id"): r.get("metrics", {}).get("f1")
                for r in aviso_run.get("results", [])
            },
            "diferencias_reales_benchmark": benchmark.get("diferencias_reales_totales", 0),
            "modulos_muertos_audit": len(audit.get("modulos_muertos", [])),
            "dependencias_circulares_audit": len(audit.get("dependencias_circulares", [])),
        },
    }
    (out / "phase12_summary.json").write_text(
        json.dumps(phase_report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return phase_report


def _benchmark_compare_to_result(compare: dict, mode: str) -> dict:
    """Convierte una comparación del benchmark a un pseudo-resultado de pipeline
    para los reportes de calidad de campos (misma forma que un resultado real)."""
    fields = {}
    for fname, fdata in (compare.get(mode, {}).get("fields", {}) or {}).items():
        fields[fname] = {"value": fdata.get("value"), "status": fdata.get("status"),
                         "source": "parser"}
    result = {
        "document_id": Path(compare["file"]).stem,
        "country": compare["country"],
        "fields": fields,
        "validation": {},
        "certification": {},
        "stages": {},
        "total_time_ms": compare.get("tiempo_ms", 0.0),
        "errors": [],
        "warnings": [],
    }
    return result


if __name__ == "__main__":
    use_ai = "--no-ai" not in sys.argv
    summary = run_phase12(use_ai=use_ai)
    print(json.dumps(summary.get("resumen", summary), ensure_ascii=False, indent=1))
