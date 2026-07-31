"""FASE 13 — Orquestador: Real World Accuracy Optimization (Panamá Prioritario).

Genera automáticamente (Parte 12) en output/:

  production_accuracy.{json,md}     (Parte 13: dashboard de precisión)
  country_statistics.{json,md}      (Partes 1-2: corpus estadístico)
  pattern_discovery.{json,md}       (Parte 5: Pattern Discovery Engine)
  coverage_real.{json,md}           (Parte 6: Coverage Analyzer)
  false_positive_report.{json,md}   (Parte 9: False Positives)
  parser_gap.{json,md}              (Parte 8: Parser Gap)
  knowledge_suggestions.{json,md}   (Partes 4+7: sugerencias y analytics)

Panamá siempre primero. Determinista y auditable; no modifica parsers ni
Knowledge (no se aprueba ninguna sugerencia).
"""

import json
import sys
import time
from pathlib import Path

from backend.app.v2.evaluation.accuracy.corpus import (
    build_corpus, country_statistics, statistics_to_markdown,
)
from backend.app.v2.evaluation.accuracy.pattern_discovery import (
    discover, discovery_to_markdown,
)
from backend.app.v2.evaluation.accuracy.coverage import (
    coverage_analysis, coverage_to_markdown,
)
from backend.app.v2.evaluation.accuracy.suggestions import (
    generate_suggestions, suggestions_to_markdown,
)
from backend.app.v2.evaluation.accuracy.knowledge_analytics import (
    knowledge_analytics, analytics_to_markdown,
)
from backend.app.v2.evaluation.accuracy.parser_gap import (
    parser_gap_report, gap_to_markdown,
)
from backend.app.v2.evaluation.accuracy.false_positive import (
    false_positive_report, fp_to_markdown,
)
from backend.app.v2.evaluation.accuracy.dashboard import (
    accuracy_dashboard, dashboard_to_markdown,
)

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def _write(name: str, payload: dict, md: str) -> None:
    (OUTPUT_DIR / f"{name}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUTPUT_DIR / f"{name}.md").write_text(md, encoding="utf-8")


def run_phase13() -> dict:
    started = time.perf_counter()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    docs = build_corpus()

    # Partes 1-2: estadísticas por país (PA primero).
    stats_pa = country_statistics("PA", docs)
    stats_co = country_statistics("CO", docs)
    _write("country_statistics", {
        "orden": ["PA", "CO"],
        "paises": {"PA": stats_pa, "CO": stats_co},
    }, "\n\n".join([statistics_to_markdown(stats_pa), statistics_to_markdown(stats_co)]))

    # Parte 5: Pattern Discovery (PA primero).
    texts_pa = [d.text for d in docs if d.country == "PA"]
    texts_co = [d.text for d in docs if d.country == "CO"]
    pd_pa = discover(texts_pa, "PA")
    pd_co = discover(texts_co, "CO")
    _write("pattern_discovery", {
        "orden": ["PA", "CO"],
        "paises": {"PA": pd_pa.to_dict(), "CO": pd_co.to_dict()},
    }, "\n\n".join([discovery_to_markdown(pd_pa), discovery_to_markdown(pd_co)]))

    # Parte 6: Coverage Analyzer.
    cov = coverage_analysis(docs)
    _write("coverage_real", cov, coverage_to_markdown(cov))

    # Parte 4: sugerencias automáticas (nunca aprobadas).
    sug = generate_suggestions(texts_pa, texts_co)
    _write("knowledge_suggestions", sug, suggestions_to_markdown(sug))

    # Parte 7: Knowledge Analytics.
    kz = knowledge_analytics()
    _write("knowledge_analytics", kz, analytics_to_markdown(kz))

    # Parte 8: Parser Gap.
    gap = parser_gap_report()
    _write("parser_gap", gap, gap_to_markdown(gap))

    # Parte 9: False Positive Report.
    fp = false_positive_report()
    _write("false_positive_report", fp, fp_to_markdown(fp))

    # Parte 13: Dashboard de Precisión.
    acc = accuracy_dashboard()
    _write("production_accuracy", acc, dashboard_to_markdown(acc))

    summary = {
        "fase": 13,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "tiempo_total_ms": round((time.perf_counter() - started) * 1000, 2),
        "artefactos": [
            "production_accuracy.json/md", "country_statistics.json/md",
            "pattern_discovery.json/md", "coverage_real.json/md",
            "false_positive_report.json/md", "parser_gap.json/md",
            "knowledge_suggestions.json/md", "knowledge_analytics.json/md",
        ],
        "resumen": {
            "documentos_analizados": len(docs),
            "pa": len([d for d in docs if d.country == "PA"]),
            "co": len([d for d in docs if d.country == "CO"]),
            "precision_pa": acc["panama"].get("precision"),
            "recall_pa": acc["panama"].get("recall"),
            "f1_pa": acc["panama"].get("f1"),
            "precision_co": acc["colombia"].get("precision"),
            "recall_co": acc["colombia"].get("recall"),
            "f1_co": acc["colombia"].get("f1"),
            "campos_perdidos": acc["campos_perdidos"],
            "sugerencias": sug["total_sugerencias"],
            "reglas_creadas": 0,
        },
    }
    (OUTPUT_DIR / "phase13_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return summary


if __name__ == "__main__":
    result = run_phase13()
    print(json.dumps(result.get("resumen", result), ensure_ascii=False, indent=1))
