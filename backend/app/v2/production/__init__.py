"""FASE 10 — Production Readiness & Operational Validation package."""

from backend.app.v2.production.config import (
    ProductionConfig,
    DEFAULT_CONFIG,
    get_default,
    load_config,
)
from backend.app.v2.production.logging import (
    StructuredLogEntry,
    StructuredLogger,
    log_document,
)
from backend.app.v2.production.profiler import (
    PipelineProfiler,
    profile_result,
    CANONICAL_STAGES,
)
from backend.app.v2.production.memory import MemoryProfiler, profile_memory_stage
from backend.app.v2.production.metrics import PipelineMetrics, collect_metrics
from backend.app.v2.production.health import HealthChecker, run_health_check
from backend.app.v2.production.benchmark import PipelineBenchmark, run_benchmark
from backend.app.v2.production.batch_runner import BatchRunner, run_batch_directory
from backend.app.v2.production.smoke import SmokeTest, run_smoke_test, run_text_pipeline
from backend.app.v2.production.report import OperationalReportGenerator, generate_reports

PRODUCTION_VERSION = "10.0.0"

__all__ = [
    "ProductionConfig",
    "DEFAULT_CONFIG",
    "get_default",
    "load_config",
    "StructuredLogEntry",
    "StructuredLogger",
    "log_document",
    "PipelineProfiler",
    "profile_result",
    "CANONICAL_STAGES",
    "MemoryProfiler",
    "profile_memory_stage",
    "PipelineMetrics",
    "collect_metrics",
    "HealthChecker",
    "run_health_check",
    "PipelineBenchmark",
    "run_benchmark",
    "BatchRunner",
    "run_batch_directory",
    "SmokeTest",
    "run_smoke_test",
    "run_text_pipeline",
    "OperationalReportGenerator",
    "generate_reports",
    "PRODUCTION_VERSION",
]
