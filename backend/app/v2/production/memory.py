"""FASE 10 — Memory Profiler.

Tracks RAM usage per stage, peak memory, objects created and freed
and final memory. Uses only the standard library (tracemalloc) with
an optional psutil enhancement when available.
"""

import tracemalloc
from typing import Any, Callable, Optional

try:
    import psutil  # type: ignore
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


def _rss_mb() -> float:
    if _HAS_PSUTIL:
        return round(psutil.Process().memory_info().rss / (1024 * 1024), 3)
    try:
        import resource
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 3)
    except (ImportError, AttributeError):
        return 0.0


class MemoryProfiler:
    def __init__(self) -> None:
        self._records: list[dict] = []
        self._snapshots: list[tuple[str, float, tracemalloc.Snapshot]] = []

    def profile_stage(self, name: str, fn: Callable[[], Any]) -> dict:
        rss_before = _rss_mb()
        tracemalloc.start()
        snapshot_before = tracemalloc.take_snapshot()
        output = fn()
        snapshot_after = tracemalloc.take_snapshot()
        current_mb, peak_mb = tracemalloc.get_traced_memory()
        rss_after = _rss_mb()

        created, freed = self._object_delta(snapshot_before, snapshot_after)

        record = {
            "stage": name,
            "rss_before_mb": rss_before,
            "rss_after_mb": rss_after,
            "rss_delta_mb": round(rss_after - rss_before, 3),
            "peak_traced_mb": round(peak_mb / (1024 * 1024), 3),
            "current_traced_mb": round(current_mb / (1024 * 1024), 3),
            "objects_created": created,
            "objects_freed": freed,
            "memory_final_mb": rss_after or round(current_mb / (1024 * 1024), 3),
        }
        self._records.append(record)
        self._snapshots.append((name, rss_after, snapshot_after))
        return record

    @staticmethod
    def _object_delta(before: tracemalloc.Snapshot,
                      after: tracemalloc.Snapshot) -> tuple[int, int]:
        diff = after.compare_to(before, "lineno")
        created = sum(s.count for s in diff if s.count_diff > 0)
        freed = sum(s.count for s in diff if s.count_diff < 0)
        return created, freed

    def snapshot(self) -> dict:
        current, peak = tracemalloc.get_traced_memory()
        return {
            "rss_mb": _rss_mb(),
            "current_traced_mb": round(current / (1024 * 1024), 3),
            "peak_traced_mb": round(peak / (1024 * 1024), 3),
        }

    def peak(self) -> dict:
        if not self._records:
            return {"stage": None, "peak_traced_mb": 0.0}
        peak_record = max(self._records, key=lambda r: r["peak_traced_mb"])
        return {
            "stage": peak_record["stage"],
            "peak_traced_mb": peak_record["peak_traced_mb"],
        }

    def stats(self) -> dict:
        total_created = sum(r["objects_created"] for r in self._records)
        total_freed = sum(r["objects_freed"] for r in self._records)
        peak_record = self.peak()
        return {
            "stages": self._records,
            "total_objects_created": total_created,
            "total_objects_freed": total_freed,
            "peak_memory": peak_record,
            "final_rss_mb": _rss_mb(),
            "final_traced_mb": self.snapshot()["current_traced_mb"],
        }

    def to_dict(self) -> dict:
        return self.stats()

    def reset(self) -> None:
        self._records = []
        self._snapshots = []


def profile_memory_stage(name: str, fn: Callable[[], Any]) -> dict:
    profiler = MemoryProfiler()
    return profiler.profile_stage(name, fn)
