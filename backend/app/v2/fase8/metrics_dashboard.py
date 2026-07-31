"""FASE 8.7 — Metrics Dashboard.

Aggregates metrics from all FASE 8 modules into a unified dashboard
for monitoring pipeline health and performance.
"""

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))


@dataclass
class MetricPoint:
    name: str
    value: float
    unit: str
    category: str
    timestamp: str
    tags: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "category": self.category,
            "timestamp": self.timestamp,
            "tags": self.tags,
        }


class MetricsDashboard:
    def __init__(self):
        self.metrics: list[MetricPoint] = []

    def add_metric(self, name: str, value: float, unit: str,
                   category: str, tags: Optional[dict] = None):
        self.metrics.append(MetricPoint(
            name=name,
            value=value,
            unit=unit,
            category=category,
            timestamp=datetime.utcnow().isoformat(),
            tags=tags or {},
        ))

    def add_from_regression(self, report: dict):
        self.add_metric(
            "regression_match_rate",
            report.get("overall_match_rate", 0),
            "percent",
            "accuracy",
            {"test": "regression"},
        )
        self.add_metric(
            "regression_avg_time",
            report.get("avg_processing_time_ms", 0),
            "ms",
            "performance",
            {"test": "regression"},
        )
        if "summary" in report and "field_accuracy" in report["summary"]:
            for fname, stats in report["summary"]["field_accuracy"].items():
                self.add_metric(
                    f"field_accuracy_{fname}",
                    stats.get("accuracy", 0),
                    "percent",
                    "accuracy",
                    {"field": fname},
                )

    def add_from_stress(self, result: dict):
        self.add_metric(
            "stress_throughput",
            result.get("throughput_tasks_per_sec", 0),
            "tasks/sec",
            "performance",
            {"test": "stress"},
        )
        self.add_metric(
            "stress_success_rate",
            round(result.get("successful_tasks", 0) / max(result.get("total_tasks", 1), 1) * 100, 1),
            "percent",
            "reliability",
            {"test": "stress"},
        )

    def add_from_benchmark(self, results: dict):
        for test_name, result in results.get("results", {}).items():
            if "error" in result:
                continue
            self.add_metric(
                f"benchmark_{test_name}_throughput",
                result.get("throughput_records_per_sec", 0),
                "records/sec",
                "performance",
                {"test": test_name},
            )
            self.add_metric(
                f"benchmark_{test_name}_memory_peak",
                result.get("memory_peak_mb", 0),
                "MB",
                "resource",
                {"test": test_name},
            )
            self.add_metric(
                f"benchmark_{test_name}_success_rate",
                result.get("success_rate", 0),
                "percent",
                "reliability",
                {"test": test_name},
            )

    def add_from_certification(self, cert_report: dict):
        for doc in cert_report.get("documents", []):
            decision = doc.get("summary", {})
            self.add_metric(
                "certification_valid",
                decision.get("valid", 0),
                "count",
                "certification",
                {"document_id": doc.get("document_id", "")},
            )
            self.add_metric(
                "certification_invalid",
                decision.get("invalid", 0),
                "count",
                "certification",
                {"document_id": doc.get("document_id", "")},
            )
            self.add_metric(
                "certification_review",
                decision.get("review", 0),
                "count",
                "certification",
                {"document_id": doc.get("document_id", "")},
            )

    def generate_dashboard(self) -> dict:
        categories: dict[str, list[dict]] = {}
        for m in self.metrics:
            cat = m.category
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(m.to_dict())

        summary = {}
        for cat, points in categories.items():
            values = [p["value"] for p in points]
            summary[cat] = {
                "count": len(points),
                "avg": round(sum(values) / max(len(values), 1), 4),
                "min": round(min(values), 4) if values else 0,
                "max": round(max(values), 4) if values else 0,
            }

        return {
            "generated_at": datetime.utcnow().isoformat(),
            "total_metrics": len(self.metrics),
            "categories": summary,
            "metrics": [m.to_dict() for m in self.metrics],
        }

    def generate_summary(self) -> dict:
        accuracy_metrics = [m for m in self.metrics if m.category == "accuracy"]
        perf_metrics = [m for m in self.metrics if m.category == "performance"]
        reliability_metrics = [m for m in self.metrics if m.category == "reliability"]
        resource_metrics = [m for m in self.metrics if m.category == "resource"]

        def avg_or_zero(metrics: list[MetricPoint]) -> float:
            return round(sum(m.value for m in metrics) / max(len(metrics), 1), 4) if metrics else 0

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "accuracy": {
                "avg_match_rate": avg_or_zero([m for m in accuracy_metrics if "match_rate" in m.name]),
                "field_accuracy": {
                    m.name: m.value for m in accuracy_metrics if m.name.startswith("field_accuracy_")
                },
            },
            "performance": {
                "avg_throughput": avg_or_zero([m for m in perf_metrics if "throughput" in m.name]),
                "avg_time": avg_or_zero([m for m in perf_metrics if "time" in m.name]),
            },
            "reliability": {
                "avg_success_rate": avg_or_zero([m for m in reliability_metrics if "success" in m.name or "rate" in m.name]),
            },
            "resources": {
                "avg_memory_mb": avg_or_zero([m for m in resource_metrics if "memory" in m.name]),
            },
        }

    def save_dashboard(self, output_path: str):
        dashboard = self.generate_dashboard()
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(dashboard, f, indent=2, ensure_ascii=False)

    def save_summary(self, output_path: str):
        summary = self.generate_summary()
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
