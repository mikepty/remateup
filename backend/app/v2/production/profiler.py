"""FASE 10 — Pipeline Profiler.

Measures per-stage processing time across pipeline executions:

OCR, Assembly, Mapping, Segmentation, Stitching, Continuity,
Parser, Knowledge, Validator, Certification.

Computes total, average, maximum, minimum and standard deviation.
"""

import statistics
from typing import Any, Optional


CANONICAL_STAGES = [
    "OCR",
    "Assembly",
    "Mapping",
    "Segmentation",
    "Stitching",
    "Continuity",
    "Parser",
    "Knowledge",
    "Validator",
    "Certification",
]

_STAGE_KEY = {
    "OCR": "ocr",
    "Assembly": "assembly",
    "Mapping": "mapping",
    "Segmentation": "segmentation",
    "Stitching": "stitching",
    "Continuity": "continuity",
    "Parser": "parser",
    "Knowledge": "knowledge",
    "Validator": "validator",
    "Certification": "certification",
}


class PipelineProfiler:
    def __init__(self) -> None:
        self._samples: dict[str, list[float]] = {s: [] for s in CANONICAL_STAGES}

    @staticmethod
    def extract_stage_times(result: dict) -> dict[str, float]:
        stages = result.get("stages", {}) if isinstance(result, dict) else {}
        times: dict[str, float] = {}
        for stage_name, key in _STAGE_KEY.items():
            stage = stages.get(key)
            if isinstance(stage, dict):
                times[stage_name] = float(stage.get("duration_ms", 0.0))
            elif isinstance(stage, dict) is False and stage is not None and hasattr(stage, "duration_ms"):
                times[stage_name] = float(stage.duration_ms)
        return times

    def record(self, result: dict) -> dict[str, float]:
        times = self.extract_stage_times(result)
        for stage_name, duration in times.items():
            self._samples[stage_name].append(duration)
        return times

    def record_stage_times(self, stage_times: dict[str, float]) -> None:
        for stage_name, duration in stage_times.items():
            if stage_name in self._samples:
                self._samples[stage_name].append(float(duration))

    def stage_stats(self, stage_name: str) -> dict:
        values = self._samples.get(stage_name, [])
        if not values:
            return {
                "stage": stage_name,
                "count": 0,
                "total_ms": 0.0,
                "avg_ms": 0.0,
                "max_ms": 0.0,
                "min_ms": 0.0,
                "std_ms": 0.0,
            }
        return {
            "stage": stage_name,
            "count": len(values),
            "total_ms": round(sum(values), 2),
            "avg_ms": round(statistics.fmean(values), 2),
            "max_ms": round(max(values), 2),
            "min_ms": round(min(values), 2),
            "std_ms": round(statistics.pstdev(values), 2),
        }

    def stats(self) -> list[dict]:
        return [self.stage_stats(s) for s in CANONICAL_STAGES]

    def totals(self) -> dict:
        per_run = []
        for i in range(self._max_samples()):
            run_total = sum(
                self._samples[s][i] for s in CANONICAL_STAGES if i < len(self._samples[s])
            )
            per_run.append(run_total)
        if not per_run:
            return {"count": 0, "total_ms": 0.0, "avg_ms": 0.0,
                    "max_ms": 0.0, "min_ms": 0.0, "std_ms": 0.0}
        return {
            "count": len(per_run),
            "total_ms": round(sum(per_run), 2),
            "avg_ms": round(statistics.fmean(per_run), 2),
            "max_ms": round(max(per_run), 2),
            "min_ms": round(min(per_run), 2),
            "std_ms": round(statistics.pstdev(per_run), 2),
        }

    def _max_samples(self) -> int:
        return max((len(v) for v in self._samples.values()), default=0)

    def slowest_stage(self) -> Optional[dict]:
        by_avg = sorted(self.stats(), key=lambda s: s["avg_ms"], reverse=True)
        return by_avg[0] if by_avg and by_avg[0]["count"] > 0 else None

    def to_dict(self) -> dict:
        return {
            "stages": self.stats(),
            "totals": self.totals(),
            "slowest_stage": self.slowest_stage(),
        }

    def reset(self) -> None:
        self._samples = {s: [] for s in CANONICAL_STAGES}


def profile_result(result: dict) -> dict:
    profiler = PipelineProfiler()
    profiler.record(result)
    return profiler.to_dict()
