from typing import Any, Optional


class NormalizationConfidenceScorer:
    def score(self, normalization_result: dict) -> float:
        if not normalization_result:
            return 0.0
        if isinstance(normalization_result, dict):
            success_count = sum(1 for v in normalization_result.values() if isinstance(v, dict) and v.get("success"))
            total_count = len(normalization_result)
            if total_count == 0:
                return 0.0
            return round(success_count / total_count, 4)
        return 0.0
