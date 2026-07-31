from typing import Any, Optional


class SegmentationConfidenceScorer:
    def score(self, segmentation_result: dict) -> float:
        if not segmentation_result:
            return 0.0
        avisos = segmentation_result.get("avisos", [])
        if not isinstance(avisos, list) or len(avisos) == 0:
            return 0.0
        confidences = []
        for aviso in avisos:
            if isinstance(aviso, dict):
                c = aviso.get("confidence", 0)
                if c is not None:
                    confidences.append(float(c))
            elif hasattr(aviso, "confidence"):
                c = aviso.confidence or 0
                if c > 0:
                    confidences.append(float(c))
        if not confidences:
            return 0.0
        return round(sum(confidences) / len(confidences), 4)
