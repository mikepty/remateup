"""Tests for FASE 8 — Production Hardening & Certification modules."""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from backend.app.v2.fase8.golden_dataset import (
    GoldenDatasetManager,
    GoldenRecord,
    TestSuite,
)
from backend.app.v2.fase8.regression import (
    RegressionFramework,
    RegressionReport,
    AvisoRegressionResult,
    FieldResult,
    values_match,
    normalize_value,
)
from backend.app.v2.fase8.stress_test import (
    StressTest,
    StressTestResult,
)
from backend.app.v2.fase8.benchmark import (
    PerformanceBenchmark,
    BenchmarkResult,
)
from backend.app.v2.fase8.audit_trail import (
    AuditTrailBuilder,
    AuditTrail,
    FieldProvenance,
)
from backend.app.v2.fase8.explainability import (
    ExplainabilityEngine,
    Explanation,
    FieldExplanation,
)
from backend.app.v2.fase8.metrics_dashboard import (
    MetricsDashboard,
    MetricPoint,
)
from backend.app.v2.fase8.production_report import (
    ProductionReportGenerator,
    ProductionReport,
)
from backend.app.v2.fase8.certification_engine import (
    CertificationEngine,
    CertificationResult,
    CertificationCriterion,
)


GOLDEN_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..",
    "evaluation", "golden_dataset", "records.json"
))


# ─── Golden Dataset Tests ─────────────────────────────────────────────────────


class TestGoldenRecord:
    def test_from_dict_full(self):
        d = {
            "id": "1",
            "expediente": "2023-01327",
            "demandante": "Test",
            "demandado": "Other",
            "base": 100000.0,
            "fianza_porcentaje": 40.0,
            "minimo_porcentaje": 70.0,
            "finca_matr": "82699",
            "fecha": "2026-07-15",
            "provincia": "Panama",
        }
        r = GoldenRecord.from_dict(d)
        assert r.id == "1"
        assert r.expediente == "2023-01327"
        assert r.base == 100000.0
        assert r.fianza_porcentaje == 40.0

    def test_from_dict_minimal(self):
        d = {
            "id": "1",
            "expediente": "2023-01327",
            "demandante": "Test",
            "demandado": None,
            "base": 100000.0,
        }
        r = GoldenRecord.from_dict(d)
        assert r.demandado is None
        assert r.fianza_porcentaje is None

    def test_to_dict(self):
        r = GoldenRecord(
            id="1", expediente="EXP1", demandante="Test",
            demandado=None, base=100000.0,
            fianza_porcentaje=40.0,
        )
        d = r.to_dict()
        assert d["id"] == "1"
        assert d["expediente"] == "EXP1"
        assert "demandado" not in d
        assert "fianza_porcentaje" in d


class TestGoldenDatasetManager:
    def test_load(self):
        mgr = GoldenDatasetManager(GOLDEN_PATH)
        data = mgr.load()
        assert "test_suites" in data
        assert len(data["test_suites"]) == 3

    def test_get_suites(self):
        mgr = GoldenDatasetManager(GOLDEN_PATH)
        suites = mgr.get_suites()
        assert len(suites) == 3
        assert suites[0].id == "colombia_pdf_tabular"
        assert suites[1].id == "panama_newspaper"
        assert suites[2].id == "panama_individual"

    def test_get_all_records(self):
        mgr = GoldenDatasetManager(GOLDEN_PATH)
        records = mgr.get_all_records()
        assert len(records) == 22

    def test_get_record_by_id(self):
        mgr = GoldenDatasetManager(GOLDEN_PATH)
        record = mgr.get_record("2023-01327")
        assert record is not None
        assert record.expediente == "2023-01327"

    def test_get_record_not_found(self):
        mgr = GoldenDatasetManager(GOLDEN_PATH)
        record = mgr.get_record("nonexistent")
        assert record is None

    def test_get_records_by_country(self):
        mgr = GoldenDatasetManager(GOLDEN_PATH)
        pa_records = mgr.get_records_by_country("PA")
        assert len(pa_records) == 6
        co_records = mgr.get_records_by_country("CO")
        assert len(co_records) == 16

    def test_validate(self):
        mgr = GoldenDatasetManager(GOLDEN_PATH)
        result = mgr.validate()
        assert result["total_suites"] == 3
        assert result["total_records"] == 22
        assert isinstance(result["valid"], bool)
        assert isinstance(result["issues"], list)

    def test_get_critical_fields(self):
        mgr = GoldenDatasetManager(GOLDEN_PATH)
        fields = mgr.get_critical_fields()
        assert "expediente" in fields
        assert "demandante" in fields
        assert "demandado" in fields
        assert "base" in fields

    def test_get_field_coverage(self):
        mgr = GoldenDatasetManager(GOLDEN_PATH)
        coverage = mgr.get_field_coverage()
        assert "expediente" in coverage
        assert coverage["expediente"]["present"] == 22
        assert coverage["expediente"]["coverage_pct"] == 100.0


class TestNormalizeValue:
    def test_simple(self):
        assert normalize_value("hello") == "HELLO"

    def test_none(self):
        assert normalize_value(None) == ""

    def test_strips_spaces(self):
        assert normalize_value("  hello world  ") == "HELLOWORLD"

    def test_removes_punctuation(self):
        assert normalize_value("$1,000.00") == "100000"


class TestValuesMatch:
    def test_exact_match(self):
        assert values_match("hello", "hello", strict=True) is True

    def test_normalized_match(self):
        assert values_match("$1,000", "1000", strict=False) is True

    def test_no_match(self):
        assert values_match("hello", "world", strict=True) is False

    def test_both_none(self):
        assert values_match(None, None) is True

    def test_one_none(self):
        assert values_match(None, "hello") is False


# ─── Regression Tests ─────────────────────────────────────────────────────────


class TestFieldResult:
    def test_init(self):
        fr = FieldResult(
            field_name="expediente",
            v2_field_name="expediente",
            expected="123",
            actual="123",
            match=True,
            normalized_match=True,
        )
        assert fr.field_name == "expediente"
        assert fr.match is True

    def test_to_dict(self):
        fr = FieldResult(
            field_name="expediente",
            v2_field_name="expediente",
            expected="123",
            actual="123",
            match=True,
            normalized_match=True,
        )
        d = fr.to_dict()
        assert d["field"] == "expediente"
        assert d["v2_field"] == "expediente"
        assert d["match"] is True


class TestAvisoRegressionResult:
    def test_init(self):
        r = AvisoRegressionResult(
            record_id="1",
            expediente="EXP1",
        )
        assert r.record_id == "1"
        assert r.overall_match is False
        assert r.field_results == []

    def test_to_dict(self):
        r = AvisoRegressionResult(
            record_id="1",
            expediente="EXP1",
            overall_match=True,
            match_score=1.0,
        )
        d = r.to_dict()
        assert d["record_id"] == "1"
        assert d["overall_match"] is True


class TestRegressionFramework:
    def test_init(self):
        rf = RegressionFramework(GOLDEN_PATH)
        assert rf.golden is not None

    def test_build_test_text(self):
        rf = RegressionFramework(GOLDEN_PATH)
        record = GoldenRecord(
            id="1", expediente="EXP1", demandante="Test",
            demandado="Other", base=100000.0,
        )
        text = rf._build_test_text(record)
        assert "AVISO DE REMATE" in text
        assert "EXPEDIENTE: EXP1" in text
        assert "DEMANDANTE: Test" in text

    def test_run_regression(self):
        rf = RegressionFramework(GOLDEN_PATH)
        report = rf.run_regression(max_records=5)
        assert report.total_records == 5
        assert report.total_records >= 0
        assert isinstance(report.overall_match_rate, float)
        assert isinstance(report.avg_processing_time_ms, float)

    def test_run_regression_by_country(self):
        rf = RegressionFramework(GOLDEN_PATH)
        report = rf.run_regression(country="CO", max_records=3)
        assert report.total_records == 3

    def test_save_report(self, tmp_path):
        rf = RegressionFramework(GOLDEN_PATH)
        report = rf.run_regression(max_records=3)
        output = str(tmp_path / "regression_report.json")
        rf.save_report(report, output)
        assert os.path.exists(output)
        with open(output) as f:
            data = json.load(f)
        assert "total_records" in data


# ─── Stress Test Tests ─────────────────────────────────────────────────────────


class TestStressTestResult:
    def test_to_dict(self):
        r = StressTestResult(
            total_tasks=10,
            successful_tasks=9,
            failed_tasks=1,
            total_duration_ms=100.0,
            avg_task_duration_ms=10.0,
            max_task_duration_ms=20.0,
            min_task_duration_ms=5.0,
            throughput_tasks_per_sec=100.0,
        )
        d = r.to_dict()
        assert d["total_tasks"] == 10
        assert d["successful_tasks"] == 9


class TestStressTest:
    def test_init(self):
        st = StressTest(GOLDEN_PATH)
        assert st.golden is not None

    def test_run_concurrent(self):
        st = StressTest(GOLDEN_PATH)
        result = st.run_concurrent(num_threads=2, iterations=1)
        assert result.total_tasks > 0
        assert result.successful_tasks + result.failed_tasks == result.total_tasks

    def test_run_batch(self):
        st = StressTest(GOLDEN_PATH)
        result = st.run_batch(batch_size=5, batches=2)
        assert "total_batches" in result
        assert result["total_batches"] == 2
        assert result["total_records"] == 10

    def test_save_result(self, tmp_path):
        st = StressTest(GOLDEN_PATH)
        result = st.run_concurrent(num_threads=2, iterations=1)
        output = str(tmp_path / "stress_result.json")
        st.save_result(result, output)
        assert os.path.exists(output)


# ─── Benchmark Tests ───────────────────────────────────────────────────────────


class TestBenchmarkResult:
    def test_to_dict(self):
        r = BenchmarkResult(
            test_name="parser_benchmark",
            records_tested=39,
            total_time_ms=100.0,
            avg_time_per_record_ms=2.5,
            max_time_ms=10.0,
            min_time_ms=1.0,
            memory_peak_mb=5.0,
            memory_current_mb=2.0,
            throughput_records_per_sec=390.0,
            pipeline_version="8.0.0",
            timestamp="2026-07-30T00:00:00",
        )
        d = r.to_dict()
        assert d["test_name"] == "parser_benchmark"
        assert d["records_tested"] == 39


class TestPerformanceBenchmark:
    def test_init(self):
        pb = PerformanceBenchmark(GOLDEN_PATH)
        assert pb.golden is not None

    def test_benchmark_parser(self):
        pb = PerformanceBenchmark(GOLDEN_PATH)
        result = pb.benchmark_parser(max_records=5)
        assert result.records_tested == 5
        assert result.total_time_ms > 0

    def test_benchmark_normalization(self):
        pb = PerformanceBenchmark(GOLDEN_PATH)
        result = pb.benchmark_normalization(max_records=5)
        assert result.records_tested == 5
        assert result.test_name == "normalization_benchmark"

    def test_save_result(self, tmp_path):
        pb = PerformanceBenchmark(GOLDEN_PATH)
        result = pb.benchmark_parser(max_records=3)
        output = str(tmp_path / "benchmark.json")
        pb.save_result(result, output)
        assert os.path.exists(output)


# ─── Audit Trail Tests ────────────────────────────────────────────────────────


class TestFieldProvenance:
    def test_init(self):
        fp = FieldProvenance(
            field_name="expediente",
            v2_field_name="expediente",
            value="123",
            source="parser",
            confidence=0.95,
            stage="parser",
            timestamp="2026-07-30T00:00:00",
        )
        assert fp.field_name == "expediente"
        assert fp.source == "parser"

    def test_to_dict(self):
        fp = FieldProvenance(
            field_name="expediente",
            v2_field_name="expediente",
            value="123",
            source="parser",
            confidence=0.95,
            stage="parser",
            timestamp="2026-07-30T00:00:00",
        )
        d = fp.to_dict()
        assert d["field_name"] == "expediente"
        assert d["confidence"] == 0.95


class TestAuditTrail:
    def test_init(self):
        trail = AuditTrail(
            document_id="test_001",
            country="PA",
            source_type="newspaper_images",
            pipeline_version="8.0.0",
            timestamp="2026-07-30T00:00:00",
        )
        assert trail.document_id == "test_001"
        assert trail.fields == []

    def test_add_field(self):
        trail = AuditTrail(
            document_id="test_001",
            country="PA",
            source_type="newspaper_images",
            pipeline_version="8.0.0",
            timestamp="2026-07-30T00:00:00",
        )
        fp = FieldProvenance(
            field_name="expediente",
            v2_field_name="expediente",
            value="123",
            source="parser",
            confidence=0.95,
            stage="parser",
            timestamp="2026-07-30T00:00:00",
        )
        trail.add_field(fp)
        assert len(trail.fields) == 1

    def test_get_field(self):
        trail = AuditTrail(
            document_id="test_001",
            country="PA",
            source_type="newspaper_images",
            pipeline_version="8.0.0",
            timestamp="2026-07-30T00:00:00",
        )
        fp = FieldProvenance(
            field_name="expediente",
            v2_field_name="expediente",
            value="123",
            source="parser",
            confidence=0.95,
            stage="parser",
            timestamp="2026-07-30T00:00:00",
        )
        trail.add_field(fp)
        result = trail.get_field("expediente")
        assert result is not None
        assert result.value == "123"

    def test_get_by_source(self):
        trail = AuditTrail(
            document_id="test_001",
            country="PA",
            source_type="newspaper_images",
            pipeline_version="8.0.0",
            timestamp="2026-07-30T00:00:00",
        )
        trail.add_field(FieldProvenance("a", "a", "1", "parser", 0.9, "parser", "2026-07-30T00:00:00"))
        trail.add_field(FieldProvenance("b", "b", "2", "knowledge", 0.8, "knowledge", "2026-07-30T00:00:00"))
        parser_fields = trail.get_by_source("parser")
        assert len(parser_fields) == 1

    def test_summary(self):
        trail = AuditTrail(
            document_id="test_001",
            country="PA",
            source_type="newspaper_images",
            pipeline_version="8.0.0",
            timestamp="2026-07-30T00:00:00",
        )
        trail.add_field(FieldProvenance("a", "a", "1", "parser", 0.9, "parser", "2026-07-30T00:00:00"))
        trail.add_field(FieldProvenance("b", "b", "2", "knowledge", 0.8, "knowledge", "2026-07-30T00:00:00"))
        summary = trail.summary()
        assert summary["total_fields"] == 2
        assert "parser" in summary["sources"]
        assert "knowledge" in summary["sources"]


class TestAuditTrailBuilder:
    def test_create_trail(self):
        builder = AuditTrailBuilder()
        trail = builder.create_trail("test_001", "PA", "newspaper_images")
        assert trail.document_id == "test_001"
        assert trail.country == "PA"

    def test_extract_from_pipeline_result(self):
        builder = AuditTrailBuilder()
        pipeline_result = {
            "document_id": "test_001",
            "country": "PA",
            "source_type": "newspaper_images",
            "version": "8.0.0",
            "timestamp": "2026-07-30T00:00:00",
            "fields": {
                "expediente": {"value": "123", "confidence": 0.95, "status": "FOUND", "source": "parser"},
                "demandante": {"value": "Test", "confidence": 0.90, "status": "FOUND", "source": "parser"},
            },
            "stages": {},
        }
        trail = builder.extract_from_pipeline_result(pipeline_result, "test_001")
        assert len(trail.fields) == 2
        assert trail.fields[0].field_name == "expediente"

    def test_save_trail(self, tmp_path):
        builder = AuditTrailBuilder()
        trail = builder.create_trail("test_001", "PA", "newspaper_images")
        trail.add_field(FieldProvenance("a", "a", "1", "parser", 0.9, "parser"))
        output_dir = str(tmp_path / "audit")
        builder.save_trail(trail, output_dir)
        assert os.path.exists(os.path.join(output_dir, "test_001_audit.json"))


# ─── Explainability Tests ─────────────────────────────────────────────────────


class TestExplanation:
    def test_init(self):
        exp = Explanation(
            decision="VALID",
            reason="All checks passed",
            confidence=0.95,
        )
        assert exp.decision == "VALID"
        assert exp.confidence == 0.95

    def test_to_dict(self):
        exp = Explanation(
            decision="VALID",
            reason="All checks passed",
            confidence=0.95,
        )
        d = exp.to_dict()
        assert d["decision"] == "VALID"
        assert d["confidence"] == 0.95


class TestFieldExplanation:
    def test_init(self):
        fe = FieldExplanation(
            field_name="expediente",
            v2_field_name="expediente",
            value="123",
            confidence=0.95,
            confidence_reason="Parser confidence",
            confidence_sources={},
            status="FOUND",
            source="parser",
            normalization_success=True,
            normalization_details={},
            evidence_count=0,
            explanation="Extracted by parser",
        )
        assert fe.field_name == "expediente"
        assert fe.confidence == 0.95

    def test_to_dict(self):
        fe = FieldExplanation(
            field_name="expediente",
            v2_field_name="expediente",
            value="123",
            confidence=0.95,
            confidence_reason="Parser confidence",
            confidence_sources={},
            status="FOUND",
            source="parser",
            normalization_success=True,
            normalization_details={},
            evidence_count=0,
            explanation="Extracted by parser",
        )
        d = fe.to_dict()
        assert d["field_name"] == "expediente"
        assert d["explanation"] == "Extracted by parser"


class TestExplainabilityEngine:
    def test_init(self):
        engine = ExplainabilityEngine()
        assert engine is not None

    def test_explain_validation_valid(self):
        engine = ExplainabilityEngine()
        validation = {
            "decision": "VALID",
            "score": 0.95,
            "header_detected": "AVISO DE REMATE",
            "header_valid": True,
            "inconsistencies": [],
            "rules_applied": [
                {"rule_name": "valid_header", "passed": True, "weight": 0.25},
            ],
            "rules_failed": [],
            "duplicate_info": {"level": "UNIQUE"},
        }
        exp = engine.explain_validation(validation)
        assert exp.decision == "VALID"
        assert exp.confidence == 0.95
        assert len(exp.contributing_factors) > 0

    def test_explain_validation_invalid(self):
        engine = ExplainabilityEngine()
        validation = {
            "decision": "INVALID",
            "score": 0.2,
            "header_detected": "",
            "header_valid": False,
            "inconsistencies": [],
            "rules_applied": [],
            "rules_failed": [],
            "duplicate_info": {"level": "UNIQUE"},
        }
        exp = engine.explain_validation(validation)
        assert exp.decision == "INVALID"
        assert any("header" in r for r in exp.recommendations)

    def test_explain_field(self):
        engine = ExplainabilityEngine()
        field_data = {
            "value": "123",
            "confidence": 0.95,
            "confidence_reason": "Parser confidence",
            "confidence_sources": {},
            "status": "FOUND",
            "source": "parser",
            "normalization": {"success": True},
            "evidence": [],
        }
        fe = engine.explain_field("expediente", field_data)
        assert fe.field_name == "expediente"
        assert fe.v2_field_name == "expediente"
        assert fe.confidence == 0.95

    def test_explain_pipeline_result(self):
        engine = ExplainabilityEngine()
        pipeline_result = {
            "document_id": "test_001",
            "country": "PA",
            "source_type": "newspaper_images",
            "version": "8.0.0",
            "timestamp": "2026-07-30T00:00:00",
            "total_time_ms": 1000,
            "fields": {
                "expediente": {"value": "123", "confidence": 0.95, "status": "FOUND", "source": "parser"},
            },
            "validation": {
                "decision": "VALID",
                "score": 0.95,
                "header_detected": "AVISO DE REMATE",
                "header_valid": True,
                "inconsistencies": [],
                "rules_applied": [{"rule_name": "valid_header", "passed": True, "weight": 0.25}],
                "rules_failed": [],
                "duplicate_info": {"level": "UNIQUE"},
            },
            "stages": {
                "parser": {"status": "success", "duration_ms": 10.0, "warnings": [], "errors": []},
            },
            "confidence": 0.95,
        }
        result = engine.explain_pipeline_result(pipeline_result)
        assert result["document_id"] == "test_001"
        assert "decision_explanation" in result
        assert "field_explanations" in result

    def test_generate_report(self):
        engine = ExplainabilityEngine()
        explanations = [
            engine.explain_pipeline_result({
                "document_id": "test_001",
                "country": "PA",
                "source_type": "test",
                "version": "8.0.0",
                "timestamp": "2026-07-30T00:00:00",
                "fields": {},
                "validation": {"decision": "VALID", "score": 0.95, "header_valid": True,
                              "inconsistencies": [], "rules_applied": [], "rules_failed": [],
                              "duplicate_info": {"level": "UNIQUE"}},
                "stages": {},
                "confidence": 0.95,
            }),
        ]
        report = engine.generate_report(explanations)
        assert report["total_documents"] == 1
        assert "VALID" in report["decision_distribution"]

    def test_save_report(self, tmp_path):
        engine = ExplainabilityEngine()
        report = {"test": True}
        output = str(tmp_path / "explainability.json")
        engine.save_report(report, output)
        assert os.path.exists(output)


# ─── Metrics Dashboard Tests ──────────────────────────────────────────────────


class TestMetricPoint:
    def test_init(self):
        m = MetricPoint(
            name="test_metric",
            value=42.0,
            unit="count",
            category="test",
            timestamp="2026-07-30T00:00:00",
        )
        assert m.name == "test_metric"
        assert m.value == 42.0

    def test_to_dict(self):
        m = MetricPoint(
            name="test_metric",
            value=42.0,
            unit="count",
            category="test",
            timestamp="2026-07-30T00:00:00",
            tags={"key": "value"},
        )
        d = m.to_dict()
        assert d["name"] == "test_metric"
        assert d["tags"]["key"] == "value"


class TestMetricsDashboard:
    def test_init(self):
        dash = MetricsDashboard()
        assert dash.metrics == []

    def test_add_metric(self):
        dash = MetricsDashboard()
        dash.add_metric("test", 42.0, "count", "test_cat", {"key": "val"})
        assert len(dash.metrics) == 1
        assert dash.metrics[0].name == "test"

    def test_add_from_regression(self):
        dash = MetricsDashboard()
        report = {
            "overall_match_rate": 95.0,
            "avg_processing_time_ms": 10.0,
            "summary": {
                "field_accuracy": {
                    "expediente": {"accuracy": 98.0},
                    "base": {"accuracy": 90.0},
                }
            },
        }
        dash.add_from_regression(report)
        assert len(dash.metrics) >= 3

    def test_add_from_stress(self):
        dash = MetricsDashboard()
        result = {
            "throughput_tasks_per_sec": 100.0,
            "successful_tasks": 95,
            "total_tasks": 100,
        }
        dash.add_from_stress(result)
        assert len(dash.metrics) >= 2

    def test_add_from_benchmark(self):
        dash = MetricsDashboard()
        results = {
            "pipeline_version": "8.0.0",
            "results": {
                "parser": {
                    "throughput_records_per_sec": 100.0,
                    "memory_peak_mb": 5.0,
                    "success_rate": 95.0,
                }
            },
        }
        dash.add_from_benchmark(results)
        assert len(dash.metrics) >= 3

    def test_generate_dashboard(self):
        dash = MetricsDashboard()
        dash.add_metric("test1", 10.0, "count", "cat1")
        dash.add_metric("test2", 20.0, "count", "cat1")
        dash.add_metric("test3", 30.0, "count", "cat2")
        dashboard = dash.generate_dashboard()
        assert dashboard["total_metrics"] == 3
        assert "cat1" in dashboard["categories"]
        assert "cat2" in dashboard["categories"]

    def test_generate_summary(self):
        dash = MetricsDashboard()
        dash.add_metric("match_rate", 95.0, "percent", "accuracy")
        dash.add_metric("throughput", 100.0, "records/sec", "performance")
        dash.add_metric("success_rate", 98.0, "percent", "reliability")
        dash.add_metric("memory", 5.0, "MB", "resource")
        summary = dash.generate_summary()
        assert "accuracy" in summary
        assert "performance" in summary
        assert "reliability" in summary

    def test_save_dashboard(self, tmp_path):
        dash = MetricsDashboard()
        dash.add_metric("test", 1.0, "count", "test")
        output = str(tmp_path / "dashboard.json")
        dash.save_dashboard(output)
        assert os.path.exists(output)

    def test_save_summary(self, tmp_path):
        dash = MetricsDashboard()
        dash.add_metric("test", 1.0, "count", "test")
        output = str(tmp_path / "summary.json")
        dash.save_summary(output)
        assert os.path.exists(output)


# ─── Production Report Tests ───────────────────────────────────────────────────


class TestProductionReport:
    def test_init(self):
        report = ProductionReport(
            timestamp="2026-07-30T00:00:00",
            pipeline_version="8.0.0",
            executive_summary={"total": 39},
            regression_analysis={},
            stress_test_results={},
            performance_benchmark={},
            audit_trail_summary={},
            explainability_summary={},
            certification_status={},
            recommendations=[],
            readiness_score=85.0,
            is_ready=True,
        )
        assert report.pipeline_version == "8.0.0"
        assert report.is_ready is True

    def test_to_dict(self):
        report = ProductionReport(
            timestamp="2026-07-30T00:00:00",
            pipeline_version="8.0.0",
            executive_summary={"total": 39},
            regression_analysis={},
            stress_test_results={},
            performance_benchmark={},
            audit_trail_summary={},
            explainability_summary={},
            certification_status={},
            recommendations=["Test recommendation"],
            readiness_score=85.0,
            is_ready=True,
        )
        d = report.to_dict()
        assert d["readiness_score"] == 85.0
        assert d["is_ready"] is True
        assert len(d["recommendations"]) == 1

    def test_to_markdown(self):
        report = ProductionReport(
            timestamp="2026-07-30T00:00:00",
            pipeline_version="8.0.0",
            executive_summary={"total_records_evaluated": 39, "match_rate": 95.0},
            regression_analysis={"total_records": 39, "overall_match_rate": 95.0},
            stress_test_results={"throughput_tasks_per_sec": 100.0},
            performance_benchmark={"results": {}},
            audit_trail_summary={"total_fields": 10},
            explainability_summary={"total_documents": 1},
            certification_status={"certified": True},
            recommendations=["Test recommendation"],
            readiness_score=85.0,
            is_ready=True,
        )
        md = report.to_markdown()
        assert "Production Readiness Report" in md
        assert "85.0/100" in md


class TestProductionReportGenerator:
    def test_init(self):
        gen = ProductionReportGenerator()
        assert gen.sections == {}

    def test_add_section(self):
        gen = ProductionReportGenerator()
        gen.add_section("test", {"key": "value"})
        assert "test" in gen.sections

    def test_generate(self):
        gen = ProductionReportGenerator()
        gen.add_section("regression", {
            "total_records": 39,
            "total_matches": 37,
            "overall_match_rate": 95.0,
            "avg_processing_time_ms": 10.0,
            "summary": {"field_accuracy": {"expediente": {"accuracy": 98.0}}},
        })
        gen.add_section("stress_test", {
            "total_tasks": 78,
            "successful_tasks": 75,
            "throughput_tasks_per_sec": 100.0,
            "thread_safe": True,
        })
        gen.add_section("benchmark", {
            "pipeline_version": "8.0.0",
            "results": {
                "parser": {
                    "throughput_records_per_sec": 100.0,
                    "memory_peak_mb": 5.0,
                    "success_rate": 95.0,
                }
            },
        })
        gen.add_section("certification", {
            "valid_count": 1,
            "invalid_count": 0,
            "total_avisos": 1,
        })
        report = gen.generate()
        assert report.pipeline_version == "8.0.0"
        assert isinstance(report.readiness_score, float)
        assert isinstance(report.recommendations, list)

    def test_calculate_readiness_high(self):
        gen = ProductionReportGenerator()
        regression = {"overall_match_rate": 95.0}
        stress = {"successful_tasks": 75, "total_tasks": 75, "thread_safe": True}
        benchmark = {"results": {"parser": {"success_rate": 95.0}}}
        certification = {"valid_count": 10, "invalid_count": 0}
        score = gen._calculate_readiness(regression, stress, benchmark, certification)
        assert score > 70.0

    def test_calculate_readiness_low(self):
        gen = ProductionReportGenerator()
        regression = {"overall_match_rate": 30.0}
        stress = {"successful_tasks": 50, "total_tasks": 100, "thread_safe": False}
        benchmark = {"results": {"parser": {"success_rate": 50.0}}}
        certification = {"valid_count": 0, "invalid_count": 10}
        score = gen._calculate_readiness(regression, stress, benchmark, certification)
        assert score < 70.0


# ─── Certification Engine Tests ───────────────────────────────────────────────


class TestCertificationCriterion:
    def test_init(self):
        c = CertificationCriterion(
            name="test_criterion",
            description="Test description",
            threshold=0.9,
            operator=">=",
            unit="score",
        )
        assert c.name == "test_criterion"
        assert c.passed is False

    def test_to_dict(self):
        c = CertificationCriterion(
            name="test_criterion",
            description="Test description",
            threshold=0.9,
            operator=">=",
            unit="score",
            passed=True,
            actual_value=0.95,
            details="Passed",
        )
        d = c.to_dict()
        assert d["name"] == "test_criterion"
        assert d["passed"] is True
        assert d["actual_value"] == 0.95


class TestCertificationResult:
    def test_init(self):
        r = CertificationResult(
            certified=True,
            score=85.0,
            criteria=[],
            timestamp="2026-07-30T00:00:00",
            pipeline_version="8.0.0",
            details={},
        )
        assert r.certified is True
        assert r.score == 85.0

    def test_to_dict(self):
        r = CertificationResult(
            certified=True,
            score=85.0,
            criteria=[],
            timestamp="2026-07-30T00:00:00",
            pipeline_version="8.0.0",
            details={"key": "value"},
        )
        d = r.to_dict()
        assert d["certified"] is True
        assert d["score"] == 85.0
        assert d["details"]["key"] == "value"


class TestCertificationEngine:
    def test_init(self):
        engine = CertificationEngine(GOLDEN_PATH)
        assert engine.golden is not None
        assert engine.regression is not None
        assert engine.stress is not None
        assert engine.benchmark is not None

    def test_calculate_score(self):
        engine = CertificationEngine(GOLDEN_PATH)
        criteria = [
            CertificationCriterion("parser_accuracy", "desc", 85, ">=", "%", passed=True, actual_value=95),
            CertificationCriterion("stress_test_reliability", "desc", 95, ">=", "%", passed=True, actual_value=100),
            CertificationCriterion("golden_dataset_integrity", "desc", 1, "==", "bool", passed=True, actual_value=1),
        ]
        score = engine._calculate_score(criteria)
        assert score > 0

    def test_calculate_score_all_fail(self):
        engine = CertificationEngine(GOLDEN_PATH)
        criteria = [
            CertificationCriterion("parser_accuracy", "desc", 85, ">=", "%", passed=False, actual_value=50),
            CertificationCriterion("stress_test_reliability", "desc", 95, ">=", "%", passed=False, actual_value=50),
            CertificationCriterion("golden_dataset_integrity", "desc", 1, "==", "bool", passed=False, actual_value=0),
        ]
        score = engine._calculate_score(criteria)
        assert score == 0

    def test_generate_recommendations_good(self):
        gen = ProductionReportGenerator()
        regression = {"overall_match_rate": 95.0, "summary": {"field_accuracy": {"expediente": {"accuracy": 98.0}}}}
        stress = {"successful_tasks": 75, "total_tasks": 75}
        benchmark = {"results": {"parser": {"memory_peak_mb": 5.0}}}
        certification = {"invalid_count": 0}
        recs = gen._generate_recommendations(regression, stress, benchmark, certification)
        assert isinstance(recs, list)

    def test_generate_recommendations_poor(self):
        gen = ProductionReportGenerator()
        regression = {"overall_match_rate": 30.0, "summary": {"field_accuracy": {"expediente": {"accuracy": 30.0}}}}
        stress = {"successful_tasks": 50, "total_tasks": 100}
        benchmark = {"results": {"parser": {"memory_peak_mb": 200.0}}}
        certification = {"invalid_count": 5}
        recs = gen._generate_recommendations(regression, stress, benchmark, certification)
        assert len(recs) > 0
        assert any("accuracy" in r.lower() for r in recs)

    def test_print_summary(self):
        engine = CertificationEngine(GOLDEN_PATH)
        result = CertificationResult(
            certified=True,
            score=85.0,
            criteria=[
                CertificationCriterion("test", "desc", 1, ">=", "%", passed=True, actual_value=100),
            ],
            timestamp="2026-07-30T00:00:00",
            pipeline_version="8.0.0",
            details={},
        )
        engine.print_summary(result)
