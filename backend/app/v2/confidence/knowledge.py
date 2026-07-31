from typing import Any, Optional


class KnowledgeConfidenceAdjuster:
    def adjust(self, field_name: str, base_confidence: float, evidence: list[dict]) -> float:
        if not evidence:
            return base_confidence
        knowledge_evidence = [e for e in evidence if isinstance(e, dict) and e.get("source") == "knowledge"]
        if knowledge_evidence:
            boost = 0.1 * len(knowledge_evidence)
            return round(min(base_confidence + boost, 1.0), 4)
        return base_confidence

    def per_field_adjustment(self, field_confidences: dict[str, float], evidence_map: dict[str, list[dict]]) -> dict[str, float]:
        result = {}
        for fname, conf in field_confidences.items():
            evidence = evidence_map.get(fname, [])
            result[fname] = self.adjust(fname, conf, evidence)
        return result
