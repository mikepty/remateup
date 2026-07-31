"""FASE 11 — Reportes de validación en producción (Parte 10).

Genera:

    production_validation.json
    production_validation.md

con: Documentos, Avisos encontrados, Avisos válidos, Descartados,
Duplicados, Campos por documento, Campos IA, Campos deterministas,
Tiempo promedio, Tiempo IA, Costo estimado, Cache hit, Cache miss.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from backend.app.v2.evaluation.production.runner import OUTPUT_DIR


def build_markdown(report: dict) -> str:
    lines = [
        "# Validación en Producción — Dataset Real",
        "",
        f"**Fecha:** {report.get('timestamp', '')}",
        f"**Proveedor IA:** {report.get('provider', '')}",
        f"**Dataset:** {report.get('dataset', '')}",
        "",
        "## Resumen",
        "",
        "| Métrica | Valor |",
        "| --- | --- |",
    ]
    for key, label in (
        ("documentos", "Documentos"),
        ("avisos_encontrados", "Avisos encontrados"),
        ("avisos_validos", "Avisos válidos"),
        ("descartados", "Descartados"),
        ("duplicados", "Duplicados"),
        ("campos_ia", "Campos IA"),
        ("campos_deterministas", "Campos deterministas"),
        ("tiempo_promedio_ms", "Tiempo promedio (ms)"),
        ("tiempo_ia_ms", "Tiempo IA (ms)"),
        ("costo_estimado_usd", "Costo estimado (USD)"),
        ("cache_hit", "Cache hit"),
        ("cache_miss", "Cache miss"),
    ):
        value = report.get("summary", {}).get(key)
        if value is not None:
            lines.append(f"| {label} | {value} |")

    lines += ["", "## Campos por documento", "", "| Documento | Campos | Cantidad |", "| --- | --- | --- |"]
    for entry in report.get("summary", {}).get("campos_por_documento", []):
        lines.append(
            f"| {entry.get('document_id', '')} | {', '.join(entry.get('campos', []))} | {entry.get('cantidad', 0)} |"
        )

    comparison = report.get("comparison")
    if comparison:
        lines += ["", "## Comparativa: Solo Parser vs Parser + IA", ""]
        for mode, label in (("parser_only", "Solo Parser"), ("parser_plus_ai", "Parser + IA")):
            agg = comparison.get(mode, {})
            totals = agg.get("totals", {})
            lines.append(f"### {label}")
            lines.append("")
            lines.append(
                f"TP={totals.get('tp', 0)} FP={totals.get('fp', 0)} FN={totals.get('fn', 0)} "
                f"Precision={totals.get('precision', 0)} Recall={totals.get('recall', 0)} F1={totals.get('f1', 0)}"
            )
            lines.append("")
            lines.append("| Campo | TP | FP | FN | Precision | Recall | F1 |")
            lines.append("| --- | --- | --- | --- | --- | --- | --- |")
            for field_name, m in agg.get("per_field", {}).items():
                lines.append(
                    f"| {field_name} | {m['tp']} | {m['fp']} | {m['fn']} | "
                    f"{m['precision']} | {m['recall']} | {m['f1']} |"
                )
            lines.append("")

    if report.get("errors"):
        lines += ["", "## Errores", ""]
        for e in report["errors"]:
            lines.append(f"- {e.get('file', '')}: {e.get('error', '')}")

    return "\n".join(lines)


def generate_production_validation(report: dict, output_dir: Path = OUTPUT_DIR) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    report.setdefault("timestamp", datetime.now(timezone.utc).isoformat())

    json_path = output_dir / "production_validation.json"
    md_path = output_dir / "production_validation.md"

    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    md_path.write_text(build_markdown(report), encoding="utf-8")

    return {
        "json": str(json_path),
        "md": str(md_path),
        "json_size": json_path.stat().st_size,
        "md_size": md_path.stat().st_size,
    }
