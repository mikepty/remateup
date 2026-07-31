"""FASE 8.4 — Performance Benchmark.

Measures pipeline performance metrics including processing time,
memory usage, and resource consumption.
"""

import json
import os
import sys
import time
import tracemalloc
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from backend.app.v2.fase8.golden_dataset import GoldenDatasetManager
from backend.app.v2.pipeline.runner import PipelineRunner, PIPELINE_VERSION


@dataclass
class BenchmarkResult:
    test_name: str
    records_tested: int
    total_time_ms: float
    avg_time_per_record_ms: float
    max_time_ms: float
    min_time_ms: float
    memory_peak_mb: float
    memory_current_mb: float
    throughput_records_per_sec: float
    pipeline_version: str
    timestamp: str
    stage_times: dict[str, float] = field(default_factory=dict)
    success_rate: float = 0.0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "test_name": self.test_name,
            "pipeline_version": self.pipeline_version,
            "timestamp": self.timestamp,
            "records_tested": self.records_tested,
            "total_time_ms": round(self.total_time_ms, 2),
            "avg_time_per_record_ms": round(self.avg_time_per_record_ms, 2),
            "max_time_ms": round(self.max_time_ms, 2),
            "min_time_ms": round(self.min_time_ms, 2),
            "throughput_records_per_sec": round(self.throughput_records_per_sec, 2),
            "memory_peak_mb": round(self.memory_peak_mb, 2),
            "memory_current_mb": round(self.memory_current_mb, 2),
            "stage_times_ms": {k: round(v, 2) for k, v in self.stage_times.items()},
            "success_rate": self.success_rate,
            "errors": self.errors,
        }


class PerformanceBenchmark:
    def __init__(self, golden_path: Optional[str] = None):
        self.golden = GoldenDatasetManager(golden_path)
        self.runner = PipelineRunner()

    def benchmark_parser(self, max_records: int = 39) -> BenchmarkResult:
        from backend.app.v2.parser.factory import ParserFactory
        from backend.app.v2.parser.context import ParserContext

        records = self.golden.get_all_records()[:max_records]
        factory = ParserFactory()
        stage_times: dict[str, float] = {}
        durations: list[float] = []
        errors: list[str] = []
        success = 0

        tracemalloc.start()
        start_total = time.perf_counter()

        for record in records:
            country = self._find_country(record)
            text = self._build_test_text(record)
            t0 = time.perf_counter()
            try:
                parser = factory.get_parser(country.upper(), "REMATE")
                if parser:
                    ctx = ParserContext(country=country.upper(), document_type="REMATE", text=text)
                    parser.parse(ctx)
                    success += 1
            except Exception as e:
                errors.append(f"{record.id}: {e}")
            elapsed = (time.perf_counter() - t0) * 1000
            durations.append(elapsed)

        total_duration = (time.perf_counter() - start_total) * 1000
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        avg = sum(durations) / max(len(durations), 1)
        throughput = len(records) / max(total_duration / 1000, 0.001)

        return BenchmarkResult(
            test_name="parser_benchmark",
            records_tested=len(records),
            total_time_ms=total_duration,
            avg_time_per_record_ms=avg,
            max_time_ms=max(durations) if durations else 0,
            min_time_ms=min(durations) if durations else 0,
            memory_peak_mb=peak / (1024 * 1024),
            memory_current_mb=current / (1024 * 1024),
            throughput_records_per_sec=throughput,
            pipeline_version=PIPELINE_VERSION,
            timestamp=datetime.utcnow().isoformat(),
            stage_times=stage_times,
            success_rate=round(success / max(len(records), 1) * 100, 1),
            errors=errors[:10],
        )

    def benchmark_full_pipeline(self, max_records: int = 5) -> BenchmarkResult:
        records = self.golden.get_all_records()[:max_records]
        durations: list[float] = []
        stage_times_accum: dict[str, list[float]] = {}
        errors: list[str] = []
        success = 0

        tracemalloc.start()
        start_total = time.perf_counter()

        for record in records:
            country = self._find_country(record)
            text = self._build_test_text(record)
            t0 = time.perf_counter()
            try:
                result = self.runner.process(
                    file_paths=[],
                    country=country,
                    document_id=record.id,
                    source_type="benchmark",
                )
                success += 1
                for stage_name, stage_info in result.get("stages", {}).items():
                    dur = stage_info.get("duration_ms", 0)
                    if stage_name not in stage_times_accum:
                        stage_times_accum[stage_name] = []
                    stage_times_accum[stage_name].append(dur)
            except Exception as e:
                errors.append(f"{record.id}: {e}")
            elapsed = (time.perf_counter() - t0) * 1000
            durations.append(elapsed)

        total_duration = (time.perf_counter() - start_total) * 1000
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        avg = sum(durations) / max(len(durations), 1)
        throughput = len(records) / max(total_duration / 1000, 0.001)

        stage_times = {}
        for name, times in stage_times_accum.items():
            stage_times[name] = sum(times) / max(len(times), 1)

        return BenchmarkResult(
            test_name="full_pipeline_benchmark",
            records_tested=len(records),
            total_time_ms=total_duration,
            avg_time_per_record_ms=avg,
            max_time_ms=max(durations) if durations else 0,
            min_time_ms=min(durations) if durations else 0,
            memory_peak_mb=peak / (1024 * 1024),
            memory_current_mb=current / (1024 * 1024),
            throughput_records_per_sec=throughput,
            pipeline_version=PIPELINE_VERSION,
            timestamp=datetime.utcnow().isoformat(),
            stage_times=stage_times,
            success_rate=round(success / max(len(records), 1) * 100, 1),
            errors=errors[:10],
        )

    def benchmark_normalization(self, max_records: int = 39) -> BenchmarkResult:
        from backend.app.v2.normalization.normalizer import FieldNormalizer

        records = self.golden.get_all_records()[:max_records]
        normalizer = FieldNormalizer()
        durations: list[float] = []
        errors: list[str] = []
        success = 0

        tracemalloc.start()
        start_total = time.perf_counter()

        for record in records:
            fields = {
                "fecha_remate": {"value": record.fecha or "", "confidence": 0.95},
                "precio_base": {"value": str(record.base), "confidence": 0.95},
                "finca": {"value": record.finca_matr or "", "confidence": 0.95},
                "demandante": {"value": record.demandante, "confidence": 0.95},
            }
            t0 = time.perf_counter()
            try:
                normalizer.normalize_all(fields)
                success += 1
            except Exception as e:
                errors.append(f"{record.id}: {e}")
            elapsed = (time.perf_counter() - t0) * 1000
            durations.append(elapsed)

        total_duration = (time.perf_counter() - start_total) * 1000
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        avg = sum(durations) / max(len(durations), 1)
        throughput = len(records) / max(total_duration / 1000, 0.001)

        return BenchmarkResult(
            test_name="normalization_benchmark",
            records_tested=len(records),
            total_time_ms=total_duration,
            avg_time_per_record_ms=avg,
            max_time_ms=max(durations) if durations else 0,
            min_time_ms=min(durations) if durations else 0,
            memory_peak_mb=peak / (1024 * 1024),
            memory_current_mb=current / (1024 * 1024),
            throughput_records_per_sec=throughput,
            pipeline_version=PIPELINE_VERSION,
            timestamp=datetime.utcnow().isoformat(),
            success_rate=round(success / max(len(records), 1) * 100, 1),
            errors=errors[:10],
        )

    def run_all_benchmarks(self) -> dict:
        results = {
            "parser": self.benchmark_parser().to_dict(),
            "normalization": self.benchmark_normalization().to_dict(),
        }

        try:
            results["full_pipeline"] = self.benchmark_full_pipeline(max_records=3).to_dict()
        except Exception as e:
            results["full_pipeline"] = {"error": str(e), "status": "skipped"}

        return {
            "benchmark_timestamp": datetime.utcnow().isoformat(),
            "pipeline_version": PIPELINE_VERSION,
            "results": results,
        }

    def _build_test_text(self, record) -> str:
        lines = ["AVISO DE REMATE"]
        if record.expediente:
            lines.append(f"EXPEDIENTE: {record.expediente}")
        if record.demandante:
            lines.append(f"DEMANDANTE: {record.demandante}")
        if record.demandado:
            lines.append(f"DEMANDADO: {record.demandado}")
        if record.finca_matr:
            lines.append(f"FINCA: {record.finca_matr}")
        if record.base:
            lines.append(f"BASE: {record.base}")
        if record.fecha:
            lines.append(f"FECHA: {record.fecha}")
        if record.lugar:
            lines.append(f"LUGAR: {record.lugar}")
        if record.proceso:
            lines.append(f"PROCESO: {record.proceso}")
        if record.provincia:
            lines.append(f"PROVINCIA: {record.provincia}")
        if record.categoria:
            lines.append(f"CATEGORIA: {record.categoria}")
        return "\n".join(lines)

    def _find_country(self, record) -> str:
        suites = self.golden.get_suites()
        for s in suites:
            for r in s.expected_avisos:
                if r.id == record.id:
                    return s.pais
        return "PA"

    def save_result(self, result: BenchmarkResult, output_path: str):
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)

    def save_all(self, results: dict, output_path: str):
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
