"""FASE 10 — Operational Report.

Generates the production output artifacts:

processing_report.json / .md
performance_report.json / .md
metrics_dashboard.json / .md
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from backend.app.v2.production.config import ProductionConfig, get_default


def _round_values(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: _round_values(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_round_values(v) for v in data]
    if isinstance(data, float):
        return round(data, 4)
    return data


class OperationalReportGenerator:
    def __init__(self, config: Optional[ProductionConfig] = None):
        self.config = config or get_default()
        self.output_dir = self.config.output_path()

    def generate(
        self,
        processing: Optional[dict] = None,
        performance: Optional[dict] = None,
        metrics: Optional[dict] = None,
        health: Optional[dict] = None,
    ) -> dict[str, Path]:
        timestamp = datetime.utcnow().isoformat()
        processing = _round_values(processing or {})
        performance = _round_values(performance or {})
        metrics = _round_values(metrics or {})
        health = health or {}

        processing_report = {
            "report": "processing_report",
            "phase": "FASE 10",
            "timestamp": timestamp,
            "metrics": metrics,
            "health": health,
            "summary": {
                "documents": metrics.get("documentos_procesados", 0),
                "avisos": metrics.get("avisos_detectados", 0),
                "errors": metrics.get("errores", 0),
                "warnings": metrics.get("warnings", 0),
                "avg_time_ms": metrics.get("tiempo_promedio_ms", 0.0),
            },
        }

        performance_report = {
            "report": "performance_report",
            "phase": "FASE 10",
            "timestamp": timestamp,
            "profiler": performance.get("profiler", {}),
            "memory": performance.get("memory", {}),
            "benchmark": performance.get("benchmark", {}),
        }

        metrics_dashboard = {
            "report": "metrics_dashboard",
            "phase": "FASE 10",
            "timestamp": timestamp,
            "metrics": metrics,
            "health": {k: v for k, v in (health or {}).items()
                       if k in ("status", "summary")},
            "performance": {
                "total_avg_ms": performance.get("profiler", {}).get("totals", {}).get("avg_ms", 0.0),
                "slowest_stage": performance.get("profiler", {}).get("slowest_stage", {}),
                "best_throughput": performance.get("benchmark", {}).get("best_throughput_docs_per_sec", 0.0),
            },
        }

        paths = {
            "processing_report.json": self._write_json("processing_report", processing_report),
            "processing_report.md": self._write_md("processing_report", self._processing_md(processing_report)),
            "performance_report.json": self._write_json("performance_report", performance_report),
            "performance_report.md": self._write_md("performance_report", self._performance_md(performance_report)),
            "metrics_dashboard.json": self._write_json("metrics_dashboard", metrics_dashboard),
            "metrics_dashboard.md": self._write_md("metrics_dashboard", self._dashboard_md(metrics_dashboard)),
        }
        return paths

    def _write_json(self, name: str, data: dict) -> Path:
        path = self.output_dir / f"{name}.json"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return path

    def _write_md(self, name: str, content: str) -> Path:
        path = self.output_dir / f"{name}.md"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def _processing_md(self, report: dict) -> str:
        metrics = report.get("metrics", {})
        health = report.get("health", {})
        lines = [
            "# Processing Report — FASE 10",
            "",
            f"**Timestamp:** {report['timestamp']}",
            f"**Health:** {health.get('status', 'unknown')}",
            "",
            "## Métricas de procesamiento",
            "",
            "| Métrica | Valor |",
            "| --- | --- |",
        ]
        for k, v in metrics.items():
            lines.append(f"| {k.replace('_', ' ').title()} | {v} |")
        lines.append("")
        lines.append("## Health Check")
        lines.append("")
        for check in health.get("checks", {}).values():
            lines.append(f"- **{check['check']}:** {check['status']} — {check['detail']}")
        lines.append("")
        return "\n".join(lines)

    def _performance_md(self, report: dict) -> str:
        profiler = report.get("profiler", {})
        memory = report.get("memory", {})
        benchmark = report.get("benchmark", {})
        lines = [
            "# Performance Report — FASE 10",
            "",
            f"**Timestamp:** {report['timestamp']}",
            "",
            "## Pipeline Profiler",
            "",
            "| Etapa | Muestras | Total (ms) | Promedio (ms) | Máx (ms) | Mín (ms) | Desviación |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for stage in profiler.get("stages", []):
            lines.append(
                f"| {stage['stage']} | {stage['count']} | {stage['total_ms']} | "
                f"{stage['avg_ms']} | {stage['max_ms']} | {stage['min_ms']} | {stage['std_ms']} |"
            )
        lines.append("")
        lines.append("## Memoria")
        lines.append("")
        lines.append(f"- Objetos creados: {memory.get('total_objects_created', 0)}")
        lines.append(f"- Objetos liberados: {memory.get('total_objects_freed', 0)}")
        lines.append(f"- Pico de memoria: {memory.get('peak_memory', {}).get('peak_traced_mb', 0)} MB")
        lines.append("")
        lines.append("## Benchmark")
        lines.append("")
        for batch in benchmark.get("batch_sizes", []):
            lines.append(
                f"- Lote {batch['batch_size']}: {batch['throughput_docs_per_sec']} docs/s "
                f"— {batch['avg_time_ms']} ms/doc"
            )
        lines.append("")
        return "\n".join(lines)

    def _dashboard_md(self, report: dict) -> str:
        metrics = report.get("metrics", {})
        health = report.get("health", {})
        perf = report.get("performance", {})
        lines = [
            "# Metrics Dashboard — FASE 10",
            "",
            f"**Timestamp:** {report['timestamp']}",
            f"**Health:** {health.get('status', 'unknown')}",
            "",
            "## Dashboard",
            "",
        ]
        for k, v in metrics.items():
            lines.append(f"- **{k.replace('_', ' ').title()}:** {v}")
        lines.append("")
        lines.append("## Rendimiento")
        lines.append("")
        lines.append(f"- Tiempo promedio total: {perf.get('total_avg_ms', 0)} ms")
        lines.append(f"- Mejor throughput: {perf.get('best_throughput', 0)} docs/s")
        lines.append("")
        return "\n".join(lines)


def generate_reports(
    processing: Optional[dict] = None,
    performance: Optional[dict] = None,
    metrics: Optional[dict] = None,
    health: Optional[dict] = None,
) -> dict[str, Path]:
    return OperationalReportGenerator().generate(
        processing=processing, performance=performance,
        metrics=metrics, health=health,
    )
