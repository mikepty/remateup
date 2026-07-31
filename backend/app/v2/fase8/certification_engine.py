"""FASE 8.9 — Certification Engine.

Runs the full V2 pipeline against the golden dataset and certifies
production readiness based on accuracy, performance, and reliability
criteria.
"""

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from backend.app.v2.fase8.golden_dataset import GoldenDatasetManager
from backend.app.v2.fase8.regression import RegressionFramework
from backend.app.v2.fase8.stress_test import StressTest
from backend.app.v2.fase8.benchmark import PerformanceBenchmark
from backend.app.v2.fase8.audit_trail import AuditTrailBuilder
from backend.app.v2.fase8.explainability import ExplainabilityEngine
from backend.app.v2.fase8.metrics_dashboard import MetricsDashboard
from backend.app.v2.fase8.production_report import ProductionReportGenerator

from backend.app.v2.certification.certifier import Certifier
from backend.app.v2.certification.models import CertDecision

from backend.app.v2.schema.coverage import CoverageAnalyzer
from backend.app.v2.schema.completion import CompletionAuditor
from backend.app.v2.schema.validation import CompatibilityChecker


@dataclass
class CertificationCriterion:
    name: str
    description: str
    threshold: float
    operator: str
    unit: str
    passed: bool = False
    actual_value: float = 0.0
    details: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "threshold": self.threshold,
            "operator": self.operator,
            "unit": self.unit,
            "passed": self.passed,
            "actual_value": self.actual_value,
            "details": self.details,
        }


@dataclass
class CertificationResult:
    certified: bool
    score: float
    criteria: list[CertificationCriterion]
    timestamp: str
    pipeline_version: str
    details: dict

    def to_dict(self) -> dict:
        return {
            "certified": self.certified,
            "score": self.score,
            "timestamp": self.timestamp,
            "pipeline_version": self.pipeline_version,
            "criteria": [c.to_dict() for c in self.criteria],
            "details": self.details,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


class CertificationEngine:
    PASSING_SCORE = 70.0

    def __init__(self, golden_path: Optional[str] = None):
        self.golden = GoldenDatasetManager(golden_path)
        self.regression = RegressionFramework(golden_path)
        self.stress = StressTest(golden_path)
        self.benchmark = PerformanceBenchmark(golden_path)
        self.explainability = ExplainabilityEngine()
        self.dashboard = MetricsDashboard()
        self.report_gen = ProductionReportGenerator()
        self.certifier = Certifier()
        self.analyzer = CoverageAnalyzer()
        self.compat_checker = CompatibilityChecker(analyzer=self.analyzer)
        self.completion = CompletionAuditor(registry=self.analyzer.registry,
                                            analyzer=self.analyzer)

    def run_alignment_check(self) -> dict:
        """FASE 8.10.5 — alignment validations: coverage by field, by country,
        by document type and by stage, plus missing critical fields.

        Blocks CERTIFIED when:
        - a critical field has no producer
        - a required field has no consumer
        - a field required by the golden dataset is produced by no parser
        """
        analysis = self.analyzer.run_full_analysis()

        critical_missing = []
        for field in analysis["never_produced"]:
            definition = self.analyzer.registry.resolve(field)
            if definition and definition.priority == "critical":
                critical_missing.append(field)

        required_no_consumer = []
        for field in analysis["never_consumed"]:
            definition = self.analyzer.registry.resolve(field)
            if definition and definition.required:
                required_no_consumer.append(field)

        blockers = self.compat_checker.find_certification_blockers()

        audit = self.completion.run_full_audit()

        return {
            "coverage_by_field": analysis["fields"],
            "coverage_by_country": analysis["coverage_by_country"],
            "coverage_by_document_type": {
                dt: self.analyzer.coverage_by_document_type(dt)
                for dt in ("pdf_tabular", "newspaper_images", "individual_images")
            },
            "coverage_by_stage": analysis["coverage_by_stage"],
            "critical_fields_missing_producer": sorted(critical_missing),
            "required_fields_no_consumer": sorted(required_no_consumer),
            "golden_fields_without_parser": sorted(blockers),
            "alignment_pct": analysis["alignment_pct"],
            "blocked": len(critical_missing) > 0 or len(required_no_consumer) > 0 or len(blockers) > 0,
            "overall_alignment": audit["overall_alignment"],
            "blocked_fields": [b["field"] for b in audit["blocked_fields"]],
            "certified_fields": audit["certified_fields"],
            "orphan_fields": audit["orphan_fields"],
            "unused_fields": audit["missing_consumers"],
            "missing_producers": audit["missing_producers"],
            "missing_consumers": audit["missing_consumers"],
            "invalid_aliases": audit["invalid_aliases"],
            "type_conflicts": audit["type_conflicts"],
            "format_conflicts": audit["format_conflicts"],
        }

    def run_certification(self) -> CertificationResult:
        criteria: list[CertificationCriterion] = []
        details: dict = {}

        regression_report = self.regression.run_regression()
        reg_dict = regression_report.to_dict()
        details["regression"] = reg_dict

        criterion = CertificationCriterion(
            name="parser_accuracy",
            description="Parser F1 score against golden dataset",
            threshold=0.85,
            operator=">=",
            unit="F1 score",
            actual_value=regression_report.summary.get("field_accuracy", {}),
        )

        match_rate = reg_dict.get("overall_match_rate", 0)
        criterion.passed = match_rate >= 85.0
        criterion.actual_value = match_rate
        criterion.details = f"Match rate: {match_rate}% (threshold: 85%)"
        criteria.append(criterion)

        self.dashboard.add_from_regression(reg_dict)

        stress_result = self.stress.run_concurrent(num_threads=4, iterations=2)
        stress_dict = stress_result.to_dict()
        details["stress_test"] = stress_dict

        stress_success_rate = round(
            stress_result.successful_tasks / max(stress_result.total_tasks, 1) * 100, 1
        )
        criterion = CertificationCriterion(
            name="stress_test_reliability",
            description="Stress test success rate under concurrent load",
            threshold=95.0,
            operator=">=",
            unit="percent",
            actual_value=stress_success_rate,
            passed=stress_success_rate >= 95.0,
            details=f"{stress_result.successful_tasks}/{stress_result.total_tasks} tasks succeeded",
        )
        criteria.append(criterion)

        self.dashboard.add_from_stress(stress_dict)

        benchmark_results = self.benchmark.run_all_benchmarks()
        details["benchmark"] = benchmark_results

        self.dashboard.add_from_benchmark(benchmark_results)

        bench_parser = benchmark_results.get("results", {}).get("parser", {})
        if "error" not in bench_parser:
            throughput = bench_parser.get("throughput_records_per_sec", 0)
            criterion = CertificationCriterion(
                name="parser_throughput",
                description="Parser throughput (records per second)",
                threshold=10.0,
                operator=">=",
                unit="records/sec",
                actual_value=throughput,
                passed=throughput >= 10.0,
                details=f"Throughput: {throughput} records/sec",
            )
            criteria.append(criterion)

            mem_peak = bench_parser.get("memory_peak_mb", 0)
            criterion = CertificationCriterion(
                name="parser_memory",
                description="Parser memory usage",
                threshold=50.0,
                operator="<=",
                unit="MB",
                actual_value=mem_peak,
                passed=mem_peak <= 50.0,
                details=f"Peak memory: {mem_peak:.1f} MB",
            )
            criteria.append(criterion)

        golden_validation = self.golden.validate()
        details["golden_dataset_validation"] = golden_validation

        criterion = CertificationCriterion(
            name="golden_dataset_integrity",
            description="Golden dataset integrity check",
            threshold=1.0,
            operator="==",
            unit="boolean",
            actual_value=1.0 if golden_validation["valid"] else 0.0,
            passed=golden_validation["valid"],
            details=f"Records: {golden_validation['total_records']}, Issues: {len(golden_validation['issues'])}",
        )
        criteria.append(criterion)

        alignment = self.run_alignment_check()
        details["schema_alignment"] = alignment

        criterion = CertificationCriterion(
            name="schema_alignment",
            description="Schema alignment across parser/knowledge/validator/normalizer/confidence/golden/certification",
            threshold=100.0,
            operator=">=",
            unit="percent",
            actual_value=alignment["alignment_pct"],
            passed=alignment["alignment_pct"] >= 100.0,
            details=(
                f"Alignment: {alignment['alignment_pct']}% — "
                f"blocked: {alignment['blocked']}"
            ),
        )
        criteria.append(criterion)

        for label, fields in (
            ("critical_fields_missing_producer", alignment["critical_fields_missing_producer"]),
            ("required_fields_no_consumer", alignment["required_fields_no_consumer"]),
            ("golden_fields_without_parser", alignment["golden_fields_without_parser"]),
        ):
            name = "alignment_" + label
            criteria.append(CertificationCriterion(
                name=name,
                description=f"{label.replace('_', ' ')}",
                threshold=0.0,
                operator="==",
                unit="count",
                actual_value=float(len(fields)),
                passed=len(fields) == 0,
                details=f"Fields: {', '.join(fields) if fields else 'none'}",
            ))

        score = self._calculate_score(criteria)
        certified = score >= self.PASSING_SCORE
        if alignment["blocked"]:
            certified = False

        cert_summary = {
            "certified": certified,
            "score": score,
            "criteria_passed": sum(1 for c in criteria if c.passed),
            "criteria_total": len(criteria),
        }
        details["certification_summary"] = cert_summary

        return CertificationResult(
            certified=certified,
            score=score,
            criteria=criteria,
            timestamp=datetime.utcnow().isoformat(),
            pipeline_version="8.0.0",
            details=details,
        )

    def _calculate_score(self, criteria: list[CertificationCriterion]) -> float:
        if not criteria:
            return 0.0

        passed = sum(1 for c in criteria if c.passed)
        base_score = (passed / len(criteria)) * 100

        weighted_scores = []
        weights = {
            "parser_accuracy": 0.35,
            "stress_test_reliability": 0.20,
            "parser_throughput": 0.15,
            "parser_memory": 0.10,
            "golden_dataset_integrity": 0.20,
        }

        for c in criteria:
            w = weights.get(c.name, 0.1)
            score = w * 100 if c.passed else 0
            weighted_scores.append(score)

        weighted_score = sum(weighted_scores)
        return round(min(weighted_score * 2, 100.0), 1)

    def generate_production_report(self, cert_result: CertificationResult) -> str:
        self.report_gen.add_section("regression", cert_result.details.get("regression", {}))
        self.report_gen.add_section("stress_test", cert_result.details.get("stress_test", {}))
        self.report_gen.add_section("benchmark", cert_result.details.get("benchmark", {}))
        self.report_gen.add_section("certification", {
            "valid_count": 1 if cert_result.certified else 0,
            "invalid_count": 0 if cert_result.certified else 1,
            "total_avisos": 1,
        })

        report = self.report_gen.generate()

        output_dir = Path(__file__).parent / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        report_path = output_dir / "production_report.json"
        md_path = output_dir / "production_report.md"

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(report.to_markdown())

        return str(report_path)

    def save_certification(self, cert_result: CertificationResult, output_path: str):
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(cert_result.to_json())

    def print_summary(self, cert_result: CertificationResult):
        print()
        print("=" * 70)
        print("  FASE 8 — CERTIFICATION ENGINE RESULTS")
        print("=" * 70)
        print(f"  Certified: {'YES' if cert_result.certified else 'NO'}")
        print(f"  Score: {cert_result.score}/100")
        print(f"  Criteria passed: {sum(1 for c in cert_result.criteria if c.passed)}/{len(cert_result.criteria)}")
        print()
        print("  Criteria:")
        for c in cert_result.criteria:
            status = "PASS" if c.passed else "FAIL"
            print(f"    [{status}] {c.name}: {c.actual_value} {c.unit} (threshold: {c.threshold})")
        print()
        print("=" * 70)
