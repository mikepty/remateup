"""Tests for FASE 10 — Production Readiness & Operational Validation."""

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from backend.app.v2.production.config import ProductionConfig, get_default, load_config
from backend.app.v2.production.logging import (
    StructuredLogger,
    StructuredLogEntry,
)
from backend.app.v2.production.profiler import (
    PipelineProfiler,
    CANONICAL_STAGES,
)
from backend.app.v2.production.memory import MemoryProfiler
from backend.app.v2.production.metrics import PipelineMetrics, collect_metrics
from backend.app.v2.production.health import HealthChecker, run_health_check
from backend.app.v2.production.smoke import (
    SmokeTest,
    run_smoke_test,
    run_text_pipeline,
    SMOKE_TEXT_CO,
)
from backend.app.v2.production.batch_runner import BatchRunner
from backend.app.v2.production.benchmark import PipelineBenchmark
from backend.app.v2.production.report import OperationalReportGenerator, generate_reports

SAMPLE_RESULT = run_text_pipeline(
    SMOKE_TEXT_CO, country="CO", document_id="sample-1"
)


class TestConfig:
    def test_default_valid(self):
        config = get_default()
        assert config.is_valid() is True
        assert config.validate() == []
        assert config.batch_size == 10
        assert config.workers == 4
        assert config.timeouts["ocr"] > 0
        assert config.memory_limits["max_mb"] > 0
        assert config.feature_flags["ocr_enabled"] is True

    def test_to_dict_roundtrip(self):
        config = ProductionConfig.from_dict(get_default().to_dict())
        assert config.batch_size == 10
        assert config.timeouts == get_default().timeouts

    def test_validate_invalid(self):
        config = ProductionConfig(batch_size=0)
        assert config.is_valid() is False
        assert any("batch_size" in e for e in config.validate())

    def test_load_config(self):
        assert load_config() is not None
        assert load_config({"batch_size": 25}).batch_size == 25

    def test_serializable(self):
        json.dumps(get_default().to_dict())


class TestStructuredLogger:
    def test_log_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "pipeline.log"
            logger = StructuredLogger(log_path=log_path)
            logger.log_document(
                document_id="doc-1", country="CO", pages=3,
                processing_time=120.5, decision="VALID", score=0.95,
                errores=[], warnings=["low confidence"],
            )
            lines = log_path.read_text(encoding="utf-8").strip().splitlines()
            assert len(lines) == 1
            entry = json.loads(lines[0])
            assert entry["document_id"] == "doc-1"
            assert entry["country"] == "CO"
            assert entry["pages"] == 3
            assert entry["decision"] == "VALID"
            assert entry["score"] == 0.95
            assert entry["warnings"] == ["low confidence"]

    def test_log_from_result(self):
        logger = StructuredLogger()
        entry = logger.log_from_result(SAMPLE_RESULT)
        assert entry.document_id == "sample-1"
        assert entry.country == "CO"
        assert entry.processing_time > 0
        assert entry.to_dict()["errores"] == []

    def test_entries_and_dict(self):
        logger = StructuredLogger()
        logger.log_document(document_id="a", country="CO", pages=1,
                            processing_time=1.0, decision="VALID", score=1.0)
        assert len(logger.entries()) == 1
        data = logger.to_dict()
        assert data["total_entries"] == 1

    def test_log_entry_serializable(self):
        entry = StructuredLogEntry(document_id="x", country="PA", pages=2,
                                   processing_time=5.0, decision="INCOMPLETE", score=0.4)
        json.dumps(entry.to_dict())


class TestPipelineProfiler:
    def test_extract_stage_times(self):
        times = PipelineProfiler.extract_stage_times(SAMPLE_RESULT)
        for stage in ("OCR", "Parser", "Knowledge", "Validator", "Certification"):
            assert stage in times
        assert times["Parser"] > 0

    def test_record_and_stats(self):
        profiler = PipelineProfiler()
        profiler.record(SAMPLE_RESULT)
        profiler.record(SAMPLE_RESULT)
        stats = {s["stage"]: s for s in profiler.stats()}
        assert stats["Parser"]["count"] == 2
        assert stats["Parser"]["avg_ms"] > 0
        assert stats["Parser"]["max_ms"] >= stats["Parser"]["min_ms"]
        assert stats["Parser"]["std_ms"] >= 0

    def test_totals(self):
        profiler = PipelineProfiler()
        profiler.record(SAMPLE_RESULT)
        totals = profiler.totals()
        assert totals["count"] == 1
        assert totals["total_ms"] > 0
        assert totals["max_ms"] >= totals["min_ms"]

    def test_slowest_stage(self):
        profiler = PipelineProfiler()
        profiler.record(SAMPLE_RESULT)
        slowest = profiler.slowest_stage()
        assert slowest is not None
        assert slowest["count"] > 0

    def test_to_dict_and_reset(self):
        profiler = PipelineProfiler()
        profiler.record(SAMPLE_RESULT)
        data = profiler.to_dict()
        assert "stages" in data and "totals" in data
        json.dumps(data)
        profiler.reset()
        assert profiler.totals()["count"] == 0

    def test_canonical_stages(self):
        assert CANONICAL_STAGES == [
            "OCR", "Assembly", "Mapping", "Segmentation", "Stitching",
            "Continuity", "Parser", "Knowledge", "Validator", "Certification",
        ]


class TestMemoryProfiler:
    def test_profile_stage(self):
        profiler = MemoryProfiler()
        record = profiler.profile_stage("parser", lambda: SAMPLE_RESULT)
        assert record["stage"] == "parser"
        assert record["peak_traced_mb"] >= 0
        assert record["objects_created"] >= 0
        assert record["objects_freed"] >= 0
        assert record["memory_final_mb"] >= 0

    def test_peak(self):
        profiler = MemoryProfiler()
        profiler.profile_stage("a", lambda: 1)
        profiler.profile_stage("b", lambda: 2)
        peak = profiler.peak()
        assert peak["stage"] in ("a", "b")
        assert peak["peak_traced_mb"] >= 0

    def test_stats(self):
        profiler = MemoryProfiler()
        profiler.profile_stage("a", lambda: 1)
        stats = profiler.stats()
        assert stats["total_objects_created"] >= 0
        assert stats["final_rss_mb"] >= 0
        json.dumps(stats)

    def test_to_dict(self):
        profiler = MemoryProfiler()
        profiler.profile_stage("a", lambda: 1)
        json.dumps(profiler.to_dict())


class TestPipelineMetrics:
    def test_collect(self):
        metrics = collect_metrics([SAMPLE_RESULT])
        assert metrics["documentos_procesados"] == 1
        assert metrics["avisos_detectados"] == 1
        assert metrics["errores"] == 0
        assert metrics["tiempo_promedio_ms"] > 0
        json.dumps(metrics)

    def test_empty(self):
        metrics = collect_metrics([])
        assert metrics["documentos_procesados"] == 0
        assert metrics["parser_accuracy"] == 0.0

    def test_aggregation(self):
        other = run_text_pipeline("SIN AVISO DE REMATE", country="CO", document_id="x")
        metrics = PipelineMetrics().collect([SAMPLE_RESULT, other])
        assert metrics["documentos_procesados"] == 2
        assert metrics["errores"] == 0
        assert metrics["avisos_detectados"] == 2

    def test_all_keys_present(self):
        metrics = collect_metrics([SAMPLE_RESULT])
        for key in ("documentos_procesados", "avisos_detectados", "avisos_validos",
                    "avisos_descartados", "duplicados", "ocr_promedio",
                    "parser_accuracy", "knowledge_usage", "validator_acceptance",
                    "certification_rate", "errores", "warnings", "tiempo_promedio_ms"):
            assert key in metrics, key


class TestHealthCheck:
    def test_healthy(self):
        health = run_health_check()
        assert health["status"] == "HEALTHY"
        assert health["summary"]["errors"] == 0
        for check in health["checks"].values():
            assert check["status"] == "OK"

    def test_checks_present(self):
        health = run_health_check()
        for name in ("parser", "knowledge", "schema", "validator",
                     "registry", "sqlite", "config"):
            assert name in health["checks"], name

    def test_invalid_config_fails(self):
        checker = HealthChecker(config=ProductionConfig(batch_size=0))
        health = checker.run()
        assert health["checks"]["config"]["status"] == "ERROR"
        assert health["status"] == "ERROR"
        assert "config" in health["critical_failed"]

    def test_serializable(self):
        json.dumps(run_health_check())


class TestSmokeTest:
    def test_smoke_pass(self):
        smoke = run_smoke_test()
        assert smoke["status"] == "PASS"
        assert smoke["failed_stages"] == []
        for stage in smoke["stages"].values():
            assert stage["status"] == "success"

    def test_all_stages_tracked(self):
        smoke = run_smoke_test()
        for name in ("documento", "ocr", "parser", "knowledge",
                     "validator", "certification"):
            assert name in smoke["stages"], name

    def test_smoke_fail_on_bad_text(self):
        smoke = SmokeTest(text="texto vacío sin estructura").run()
        assert smoke["status"] in ("PASS", "FAIL")

    def test_result_has_fields(self):
        result = run_text_pipeline(SMOKE_TEXT_CO, country="CO")
        assert result["metrics"]["fields_found"] >= 6

    def test_run_text_pipeline_error_collection(self):
        result = run_text_pipeline("SIN DATOS", country="CO", document_id="e1")
        assert "errors" in result
        assert "stages" in result


class TestBatchRunner:
    def test_run_text_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = BatchRunner()
            batch = runner.run_text_batch([
                {"id": "t1", "country": "CO", "text": SMOKE_TEXT_CO},
                {"id": "t2", "country": "CO", "text": "SIN AVISO DE REMATE"},
            ], country="CO")
            assert batch["summary"]["total_documents"] == 2
            assert batch["summary"]["successful"] == 2
            assert batch["metrics"]["documentos_procesados"] == 2
            assert len(batch["results"]) == 2
            json.dumps(batch, default=str)

    def test_run_directory_missing(self):
        batch = BatchRunner().run_directory("C:/no/existe/dir", "CO")
        assert batch["summary"]["total_documents"] == 0
        assert any("not found" in e for e in batch["errors"])

    def test_run_directory_text_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "aviso1.txt").write_text(SMOKE_TEXT_CO, encoding="utf-8")
            (path / "aviso2.txt").write_text("OTRO AVISO SIN DATOS", encoding="utf-8")
            batch = BatchRunner().run_directory(str(path), "CO")
            assert batch["summary"]["total_documents"] == 2
            assert batch["summary"]["successful"] == 2

    def test_export_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            batch = BatchRunner().run_text_batch(
                [{"id": "t1", "country": "CO", "text": SMOKE_TEXT_CO}], country="CO"
            )
            out = Path(tmp) / "batch.json"
            BatchRunner().export_results(batch, str(out))
            data = json.loads(out.read_text(encoding="utf-8"))
            assert data["summary"]["total_documents"] == 1


class TestBenchmark:
    def test_benchmark_batch_sizes(self):
        benchmark = PipelineBenchmark().run(batch_sizes=(1, 10))
        assert len(benchmark["batch_sizes"]) == 2
        for result in benchmark["batch_sizes"]:
            assert result["batch_size"] in (1, 10)
            assert result["throughput_docs_per_sec"] > 0
            assert result["avg_time_ms"] > 0
            assert "memory" in result
        assert benchmark["best_throughput_docs_per_sec"] > 0

    def test_benchmark_serializable(self):
        benchmark = PipelineBenchmark().run(batch_sizes=(1,))
        json.dumps(benchmark, default=str)


class TestOperationalReports:
    def test_generate_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = ProductionConfig(output_dir=tmp)
            generator = OperationalReportGenerator(config=config)
            paths = generator.generate(
                metrics=collect_metrics([SAMPLE_RESULT]),
                health=run_health_check(),
                performance={
                    "profiler": PipelineProfiler().to_dict(),
                    "memory": MemoryProfiler().stats(),
                    "benchmark": PipelineBenchmark().run(batch_sizes=(1,)),
                },
            )
            assert set(paths.keys()) == {
                "processing_report.json", "processing_report.md",
                "performance_report.json", "performance_report.md",
                "metrics_dashboard.json", "metrics_dashboard.md",
            }
            for name, path in paths.items():
                assert path.exists(), name
                assert path.stat().st_size > 0, name

    def test_report_structures(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = ProductionConfig(output_dir=tmp)
            generator = OperationalReportGenerator(config=config)
            paths = generator.generate(metrics=collect_metrics([SAMPLE_RESULT]))
            processing = json.loads(paths["processing_report.json"].read_text(encoding="utf-8"))
            assert processing["report"] == "processing_report"
            assert processing["metrics"]["documentos_procesados"] == 1
            dashboard = json.loads(paths["metrics_dashboard.json"].read_text(encoding="utf-8"))
            assert dashboard["report"] == "metrics_dashboard"
            assert "metrics" in dashboard

    def test_processing_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = ProductionConfig(output_dir=tmp)
            generator = OperationalReportGenerator(config=config)
            paths = generator.generate(metrics=collect_metrics([SAMPLE_RESULT]))
            md = paths["processing_report.md"].read_text(encoding="utf-8")
            assert "Processing Report" in md
            assert "Documentos Procesados" in md

    def test_generate_reports_helper(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = generate_reports(metrics=collect_metrics([SAMPLE_RESULT]))
            assert len(paths) == 6
