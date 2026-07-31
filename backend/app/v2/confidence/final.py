from typing import Any, Optional

from backend.app.v2.confidence.ocr import OCRConfidenceScorer
from backend.app.v2.confidence.segment import SegmentationConfidenceScorer
from backend.app.v2.confidence.parser import ParserConfidenceScorer
from backend.app.v2.confidence.normalization import NormalizationConfidenceScorer
from backend.app.v2.confidence.knowledge import KnowledgeConfidenceAdjuster


class FinalConfidenceCalculator:
    WEIGHTS = {
        "ocr": 0.20,
        "segmentation": 0.15,
        "parser": 0.25,
        "normalization": 0.10,
        "validation": 0.15,
        "knowledge": 0.15,
    }

    def __init__(self):
        self._ocr = OCRConfidenceScorer()
        self._segment = SegmentationConfidenceScorer()
        self._parser = ParserConfidenceScorer()
        self._norm = NormalizationConfidenceScorer()
        self._knowledge = KnowledgeConfidenceAdjuster()

    def calculate(self, scores: dict[str, float]) -> float:
        total = 0.0
        for component, weight in self.WEIGHTS.items():
            val = scores.get(component, 0.0)
            if val is not None:
                total += float(val) * weight
        return round(min(max(total, 0.0), 1.0), 4)

    def per_field_final(self, field_scores: dict[str, dict]) -> dict[str, float]:
        result = {}
        for fname, scores in field_scores.items():
            if not isinstance(scores, dict):
                result[fname] = 0.0
                continue
            total = 0.0
            for component, weight in self.WEIGHTS.items():
                val = scores.get(component, 0.0)
                if val is not None:
                    total += float(val) * weight
            result[fname] = round(min(max(total, 0.0), 1.0), 4)
        return result

    def build_field_confidence(
        self,
        field_name: str,
        parser_confidence: float,
        ocr_confidence: float,
        normalization_result: dict,
        knowledge_boost: float,
        validator_passed: bool,
    ) -> dict:
        norm_conf = 1.0 if normalization_result.get("success") else 0.5 if normalization_result else 0.0
        validation_conf = 1.0 if validator_passed else 0.0

        sources = {
            "parser": round(parser_confidence, 4),
            "ocr": round(ocr_confidence, 4),
            "normalization": round(norm_conf, 4),
            "knowledge": round(knowledge_boost, 4),
            "validation": round(validation_conf, 4),
        }

        weights = {
            "parser": 0.40,
            "ocr": 0.20,
            "normalization": 0.15,
            "knowledge": 0.15,
            "validation": 0.10,
        }

        total = sum(sources[k] * weights[k] for k in weights)
        reasons = []
        if parser_confidence >= 0.9:
            reasons.append("parser_high_confidence")
        if ocr_confidence >= 0.8:
            reasons.append("ocr_high_quality")
        if normalization_result.get("success"):
            reasons.append("normalization_success")
        if validator_passed:
            reasons.append("validator_passed")

        return {
            "confidence": round(total, 4),
            "confidence_reason": ", ".join(reasons) if reasons else "low_confidence",
            "confidence_sources": sources,
        }
