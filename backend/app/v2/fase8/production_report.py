"""FASE 8.8 — Production Report.

Generates comprehensive production readiness reports combining
all FASE 8 evaluation results.
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
class ProductionReport:
    timestamp: str
    pipeline_version: str
    executive_summary: dict
    regression_analysis: dict
    stress_test_results: dict
    performance_benchmark: dict
    audit_trail_summary: dict
    explainability_summary: dict
    certification_status: dict
    recommendations: list[str]
    readiness_score: float
    is_ready: bool

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "pipeline_version": self.pipeline_version,
            "readiness_score": self.readiness_score,
            "is_ready": self.is_ready,
            "executive_summary": self.executive_summary,
            "regression_analysis": self.regression_analysis,
            "stress_test_results": self.stress_test_results,
            "performance_benchmark": self.performance_benchmark,
            "audit_trail_summary": self.audit_trail_summary,
            "explainability_summary": self.explainability_summary,
            "certification_status": self.certification_status,
            "recommendations": self.recommendations,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def to_markdown(self) -> str:
        lines = []
        lines.append("# Production Readiness Report — FASE 8")
        lines.append("")
        lines.append(f"**Timestamp:** {self.timestamp}")
        lines.append(f"**Pipeline Version:** {self.pipeline_version}")
        lines.append(f"**Readiness Score:** {self.readiness_score:.1f}/100")
        lines.append(f"**Production Ready:** {'YES' if self.is_ready else 'NO'}")
        lines.append("")
        lines.append("---")
        lines.append("")

        lines.append("## Executive Summary")
        for k, v in self.executive_summary.items():
            lines.append(f"- **{k.replace('_', ' ').title()}:** {v}")
        lines.append("")

        lines.append("## Regression Analysis")
        lines.append(f"- Total records tested: {self.regression_analysis.get('total_records', 0)}")
        lines.append(f"- Total matches: {self.regression_analysis.get('total_matches', 0)}")
        lines.append(f"- Match rate: {self.regression_analysis.get('overall_match_rate', 0)}%")
        lines.append(f"- Avg processing time: {self.regression_analysis.get('avg_processing_time_ms', 0)}ms")
        lines.append("")

        lines.append("## Stress Test Results")
        lines.append(f"- Total tasks: {self.stress_test_results.get('total_tasks', 0)}")
        lines.append(f"- Successful: {self.stress_test_results.get('successful_tasks', 0)}")
        lines.append(f"- Failed: {self.stress_test_results.get('failed_tasks', 0)}")
        lines.append(f"- Throughput: {self.stress_test_results.get('throughput_tasks_per_sec', 0)} tasks/sec")
        lines.append(f"- Thread safe: {self.stress_test_results.get('thread_safe', False)}")
        lines.append("")

        lines.append("## Performance Benchmark")
        bench = self.performance_benchmark.get("results", {})
        for test_name, result in bench.items():
            if isinstance(result, dict) and "error" not in result:
                lines.append(f"### {test_name}")
                lines.append(f"- Throughput: {result.get('throughput_records_per_sec', 0)} records/sec")
                lines.append(f"- Memory peak: {result.get('memory_peak_mb', 0)} MB")
                lines.append(f"- Success rate: {result.get('success_rate', 0)}%")
                lines.append("")

        lines.append("## Audit Trail Summary")
        for k, v in self.audit_trail_summary.items():
            lines.append(f"- **{k.replace('_', ' ').title()}:** {v}")
        lines.append("")

        lines.append("## Explainability Summary")
        for k, v in self.explainability_summary.items():
            lines.append(f"- **{k.replace('_', ' ').title()}:** {v}")
        lines.append("")

        lines.append("## Certification Status")
        for k, v in self.certification_status.items():
            lines.append(f"- **{k.replace('_', ' ').title()}:** {v}")
        lines.append("")

        lines.append("## Recommendations")
        for i, rec in enumerate(self.recommendations, 1):
            lines.append(f"{i}. {rec}")
        lines.append("")

        return "\n".join(lines)


class ProductionReportGenerator:
    def __init__(self):
        self.sections: dict[str, Any] = {}

    def add_section(self, name: str, data: Any):
        self.sections[name] = data

    def generate(self) -> ProductionReport:
        regression = self.sections.get("regression", {})
        stress = self.sections.get("stress_test", {})
        benchmark = self.sections.get("benchmark", {})
        audit = self.sections.get("audit_trail", {})
        explainability = self.sections.get("explainability", {})
        certification = self.sections.get("certification", {})

        exec_summary = {
            "total_records_evaluated": regression.get("total_records", 0),
            "match_rate": regression.get("overall_match_rate", 0),
            "stress_throughput": stress.get("throughput_tasks_per_sec", 0) if stress else 0,
            "stress_success_rate": (
                round(stress.get("successful_tasks", 0) / max(stress.get("total_tasks", 1), 1) * 100, 1)
                if stress else 0
            ),
            "avg_processing_time_ms": regression.get("avg_processing_time_ms", 0),
            "pipeline_version": benchmark.get("pipeline_version", "8.0.0") if benchmark else "8.0.0",
        }

        readiness_score = self._calculate_readiness(
            regression, stress, benchmark, certification
        )

        is_ready = readiness_score >= 70.0

        recommendations = self._generate_recommendations(
            regression, stress, benchmark, certification
        )

        return ProductionReport(
            timestamp=datetime.utcnow().isoformat(),
            pipeline_version=benchmark.get("pipeline_version", "8.0.0") if benchmark else "8.0.0",
            executive_summary=exec_summary,
            regression_analysis=regression or {},
            stress_test_results=stress or {},
            performance_benchmark=benchmark or {},
            audit_trail_summary=audit or {},
            explainability_summary=explainability or {},
            certification_status=certification or {},
            recommendations=recommendations,
            readiness_score=readiness_score,
            is_ready=is_ready,
        )

    def _calculate_readiness(self, regression: dict, stress: dict,
                             benchmark: dict, certification: dict) -> float:
        score = 0.0

        match_rate = regression.get("overall_match_rate", 0)
        if match_rate >= 95:
            score += 30
        elif match_rate >= 85:
            score += 25
        elif match_rate >= 70:
            score += 20
        elif match_rate >= 50:
            score += 10

        if stress:
            success_rate = round(
                stress.get("successful_tasks", 0) / max(stress.get("total_tasks", 1), 1) * 100, 1
            )
            if success_rate >= 95:
                score += 20
            elif success_rate >= 90:
                score += 15
            elif success_rate >= 80:
                score += 10

            if stress.get("thread_safe", False):
                score += 5

        if benchmark and "results" in benchmark:
            perf_results = benchmark["results"]
            for test_name, result in perf_results.items():
                if isinstance(result, dict) and "error" not in result:
                    success = result.get("success_rate", 0)
                    if success >= 95:
                        score += 10
                        break

        if certification:
            valid = certification.get("valid_count", 0)
            invalid = certification.get("invalid_count", 0)
            total = max(valid + invalid, 1)
            valid_pct = valid / total * 100
            if valid_pct >= 90:
                score += 25
            elif valid_pct >= 75:
                score += 20
            elif valid_pct >= 50:
                score += 10

        score += 10

        return min(score, 100.0)

    def _generate_recommendations(self, regression: dict, stress: dict,
                                  benchmark: dict, certification: dict) -> list[str]:
        recs = []

        match_rate = regression.get("overall_match_rate", 0)
        if match_rate < 90:
            recs.append(f"Improve parser accuracy (current match rate: {match_rate}%)")
            field_acc = regression.get("summary", {}).get("field_accuracy", {})
            for fname, stats in field_acc.items():
                if stats.get("accuracy", 100) < 80:
                    recs.append(f"  - Focus on field '{fname}': {stats.get('accuracy', 0)}% accuracy")

        if stress:
            success_rate = round(
                stress.get("successful_tasks", 0) / max(stress.get("total_tasks", 1), 1) * 100, 1
            )
            if success_rate < 95:
                recs.append(f"Address concurrency issues (success rate: {success_rate}%)")
            if not stress.get("thread_safe", False):
                recs.append("Ensure thread safety in parser components")

        if benchmark and "results" in benchmark:
            for test_name, result in benchmark["results"].items():
                if isinstance(result, dict) and "error" not in result:
                    mem = result.get("memory_peak_mb", 0)
                    if mem > 100:
                        recs.append(f"Optimize memory usage in {test_name} (peak: {mem:.1f} MB)")

        if certification:
            invalid = certification.get("invalid_count", 0)
            if invalid > 0:
                recs.append(f"Review {invalid} invalid certification(s)")

        if not recs:
            recs.append("Pipeline is performing well. Continue monitoring.")

        return recs

    def save_report(self, report: ProductionReport, output_path: str):
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            f.write(report.to_json())

        md_path = path.with_suffix(".md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(report.to_markdown())
