from dataclasses import dataclass, field
from typing import Any, Optional


PARSER_ALLOWED_STATES = ["FOUND", "NOT_FOUND", "REQUIRES_REVIEW"]


@dataclass
class ParseResult:
    field_name: str = ""
    value: Any = None
    status: str = "NOT_FOUND"
    confidence: float = 0.0
    evidence: list[dict] = field(default_factory=list)
    original_value: Any = None

    def __post_init__(self):
        if self.status not in PARSER_ALLOWED_STATES:
            raise ValueError(f"Invalid status: {self.status}. Allowed: {PARSER_ALLOWED_STATES}")

    @property
    def is_found(self) -> bool:
        return self.status == "FOUND"

    @property
    def is_not_found(self) -> bool:
        return self.status == "NOT_FOUND"

    @property
    def requires_review(self) -> bool:
        return self.status == "REQUIRES_REVIEW"

    def set_found(self, value: Any, confidence: float = 1.0, evidence: Optional[list[dict]] = None,
                  original_value: Any = None):
        self.value = value
        self.status = "FOUND"
        self.confidence = confidence
        if original_value is not None:
            self.original_value = original_value
        if evidence:
            self.evidence.extend(evidence)

    def set_not_found(self):
        self.value = None
        self.status = "NOT_FOUND"
        self.confidence = 0.0

    def set_requires_review(self, value: Any, confidence: float = 0.0):
        self.value = value
        self.status = "REQUIRES_REVIEW"
        self.confidence = confidence

    def add_evidence(self, source: str, method: str, snippet: str, confidence: float = 1.0):
        self.evidence.append({
            "source": source,
            "method": method,
            "snippet": snippet,
            "confidence": confidence,
        })

    def to_dict(self) -> dict:
        return {
            "field_name": self.field_name,
            "value": self.value,
            "valor_original": self.original_value,
            "valor_normalizado": self.value,
            "status": self.status,
            "confidence": self.confidence,
            "evidence_count": len(self.evidence),
            "evidence": self.evidence,
        }
