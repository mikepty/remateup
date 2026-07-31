"""FASE 8.3 — Stress Test.

Tests concurrent and batch processing of the pipeline to verify
stability under load.
"""

import json
import os
import sys
import time
import threading
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from backend.app.v2.fase8.golden_dataset import GoldenDatasetManager
from backend.app.v2.parser.factory import ParserFactory
from backend.app.v2.parser.context import ParserContext


@dataclass
class StressTestResult:
    total_tasks: int
    successful_tasks: int
    failed_tasks: int
    total_duration_ms: float
    avg_task_duration_ms: float
    max_task_duration_ms: float
    min_task_duration_ms: float
    throughput_tasks_per_sec: float
    errors: list[dict] = field(default_factory=list)
    thread_safe: bool = True

    def to_dict(self) -> dict:
        return {
            "total_tasks": self.total_tasks,
            "successful_tasks": self.successful_tasks,
            "failed_tasks": self.failed_tasks,
            "total_duration_ms": round(self.total_duration_ms, 2),
            "avg_task_duration_ms": round(self.avg_task_duration_ms, 2),
            "max_task_duration_ms": round(self.max_task_duration_ms, 2),
            "min_task_duration_ms": round(self.min_task_duration_ms, 2),
            "throughput_tasks_per_sec": round(self.throughput_tasks_per_sec, 2),
            "thread_safe": self.thread_safe,
            "errors": self.errors,
        }


class StressTest:
    def __init__(self, golden_path: Optional[str] = None):
        self.golden = GoldenDatasetManager(golden_path)
        self.factory = ParserFactory()

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

    def _run_single(self, record, country: str) -> tuple[bool, float, Optional[str]]:
        start = time.perf_counter()
        try:
            parser = self.factory.get_parser(country.upper(), "REMATE")
            if parser is None:
                return False, (time.perf_counter() - start) * 1000, f"No parser for {country}"
            text = self._build_test_text(record)
            ctx = ParserContext(country=country.upper(), document_type="REMATE", text=text)
            parser.parse(ctx)
            elapsed = (time.perf_counter() - start) * 1000
            return True, elapsed, None
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            return False, elapsed, str(e)

    def run_concurrent(self, num_threads: int = 4, iterations: int = 1) -> StressTestResult:
        records = self.golden.get_all_records()
        if not records:
            return StressTestResult(
                total_tasks=0, successful_tasks=0, failed_tasks=0,
                total_duration_ms=0, avg_task_duration_ms=0,
                max_task_duration_ms=0, min_task_duration_ms=0,
                throughput_tasks_per_sec=0,
            )

        tasks = []
        for _ in range(iterations):
            for record in records:
                country = self._find_country(record)
                tasks.append((record, country))

        errors: list[dict] = []
        durations: list[float] = []
        success_count = 0
        fail_count = 0
        lock = threading.Lock()

        start_total = time.perf_counter()

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = {
                executor.submit(self._run_single, record, country): (record.id, country)
                for record, country in tasks
            }
            for future in as_completed(futures):
                record_id, country = futures[future]
                try:
                    success, duration, error = future.result()
                    with lock:
                        durations.append(duration)
                        if success:
                            success_count += 1
                        else:
                            fail_count += 1
                            if error:
                                errors.append({
                                    "record_id": record_id,
                                    "country": country,
                                    "error": error,
                                })
                except Exception as e:
                    with lock:
                        fail_count += 1
                        errors.append({
                            "record_id": record_id,
                            "country": country,
                            "error": f"Thread exception: {e}",
                        })

        total_duration = (time.perf_counter() - start_total) * 1000
        total_tasks = len(tasks)

        avg_duration = sum(durations) / max(len(durations), 1)
        max_duration = max(durations) if durations else 0
        min_duration = min(durations) if durations else 0
        throughput = total_tasks / max(total_duration / 1000, 0.001)

        return StressTestResult(
            total_tasks=total_tasks,
            successful_tasks=success_count,
            failed_tasks=fail_count,
            total_duration_ms=total_duration,
            avg_task_duration_ms=avg_duration,
            max_task_duration_ms=max_duration,
            min_task_duration_ms=min_duration,
            throughput_tasks_per_sec=throughput,
            errors=errors[:20],
            thread_safe=fail_count == 0 or all(
                "Thread exception" not in e.get("error", "") for e in errors
            ),
        )

    def run_batch(self, batch_size: int = 10, batches: int = 3) -> dict:
        records = self.golden.get_all_records()
        batch_results = []

        for i in range(batches):
            batch_records = records[i * batch_size:(i + 1) * batch_size]
            if not batch_records:
                break

            start = time.perf_counter()
            success = 0
            fail = 0
            errors = []

            for record in batch_records:
                country = self._find_country(record)
                ok, _, err = self._run_single(record, country)
                if ok:
                    success += 1
                else:
                    fail += 1
                    if err:
                        errors.append({"record_id": record.id, "error": err})

            elapsed = (time.perf_counter() - start) * 1000
            batch_results.append({
                "batch": i + 1,
                "records": len(batch_records),
                "success": success,
                "fail": fail,
                "duration_ms": round(elapsed, 2),
                "errors": errors[:10],
            })

        return {
            "total_batches": len(batch_results),
            "total_records": sum(b["records"] for b in batch_results),
            "total_success": sum(b["success"] for b in batch_results),
            "total_fail": sum(b["fail"] for b in batch_results),
            "total_duration_ms": round(sum(b["duration_ms"] for b in batch_results), 2),
            "batches": batch_results,
        }

    def _find_country(self, record) -> str:
        suites = self.golden.get_suites()
        for s in suites:
            for r in s.expected_avisos:
                if r.id == record.id:
                    return s.pais
        return "PA"

    def save_result(self, result: StressTestResult, output_path: str):
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)

    def save_batch_result(self, result: dict, output_path: str):
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
