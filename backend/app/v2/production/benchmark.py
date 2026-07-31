"""FASE 10 — Benchmark.

Runs throughput benchmarks over document batches of
1, 10, 50 and 100 documents, recording throughput,
average time and memory usage.
"""

import time
from typing import Callable, Optional

from backend.app.v2.production.config import ProductionConfig, get_default
from backend.app.v2.production.memory import MemoryProfiler

_DEFAULT_TEXT = (
    "AVISO DE REMATE\n"
    "EXPEDIENTE N° 2025-00{batch}\n"
    "MATRÍCULA INMOBILIARIA N° 050-123456\n"
    "AVALÚO COMERCIAL: $500,000,000\n"
    "FECHA DE REMATE: 20 DE DICIEMBRE DE 2026\n"
    "DEMANDANTE: BANCO DE BOGOTA\n"
    "DEMANDADO: PEDRO PABLO PEREZ LOPEZ\n"
    "FIANZA DEL POSTOR: 40%\n"
    "PORCENTAJE MÍNIMO DE LA POSTURA: 70%\n"
)


class PipelineBenchmark:
    def __init__(self, config: Optional[ProductionConfig] = None,
                 process_fn: Optional[Callable[[str, str], dict]] = None):
        self.config = config or get_default()
        self.process_fn = process_fn

    def run(self, batch_sizes: tuple[int, ...] = (1, 10, 50, 100),
            country: str = "CO") -> dict:
        from backend.app.v2.production.smoke import run_text_pipeline
        process = self.process_fn or (lambda text, c: run_text_pipeline(text, country=c))
        results = []
        for size in batch_sizes:
            results.append(self._benchmark_size(size, country, process))
        return {
            "country": country,
            "batch_sizes": results,
            "best_throughput_docs_per_sec": max(
                (r["throughput_docs_per_sec"] for r in results), default=0.0
            ),
        }

    def _benchmark_size(self, size: int, country: str, process: Callable) -> dict:
        documents = [
            _DEFAULT_TEXT.format(batch=str(i).zfill(3)) for i in range(size)
        ]
        start = time.perf_counter()
        memory = MemoryProfiler()
        memory_records = memory.profile_stage(
            f"batch_{size}",
            lambda: [process(doc, country) for doc in documents],
        )
        elapsed = time.perf_counter() - start
        total_ms = round(elapsed * 1000, 2)
        avg_ms = round(total_ms / max(size, 1), 2)
        throughput = round(size / elapsed, 2) if elapsed > 0 else 0.0
        return {
            "batch_size": size,
            "total_time_ms": total_ms,
            "avg_time_ms": avg_ms,
            "throughput_docs_per_sec": throughput,
            "memory": memory_records,
        }

    def to_dict(self) -> dict:
        return self.run()


def run_benchmark(batch_sizes: tuple[int, ...] = (1, 10, 50, 100),
                  country: str = "CO") -> dict:
    return PipelineBenchmark().run(batch_sizes=batch_sizes, country=country)
