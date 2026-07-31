from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class EvidenceType(str, Enum):
    OCR_TEXT = "ocr_text"
    OCR_POSITION = "ocr_position"
    SEGMENT_CONTEXT = "segment_context"
    LABEL_VALUE_RELATION = "label_value_relation"
    PARSER_PATTERN = "parser_pattern"
    NORMALIZATION = "normalization"
    KNOWLEDGE_RULE = "knowledge_rule"
    MANUAL_CORRECTION = "manual_correction"
    USER_APPROVED = "user_approved"


class ExtractionState(str, Enum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    REQUIRES_REVIEW = "requires_review"


@dataclass
class Evidence:
    id: Optional[int] = None
    field_name: str = ""
    value: Any = None
    raw_value: Any = None
    state: ExtractionState = ExtractionState.NOT_FOUND
    evidence_type: EvidenceType = EvidenceType.OCR_TEXT
    confidence: float = 0.0
    source: str = ""
    transformation_log: list[str] = field(default_factory=list)
    document_id: Optional[int] = None
    page: int = 0
    block_id: Optional[int] = None
    bounding_box: Optional[dict] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def with_field(self, field_name: str) -> "Evidence":
        self.field_name = field_name
        return self

    def with_value(self, value: Any, raw_value: Any = None) -> "Evidence":
        self.value = value
        self.raw_value = raw_value or value
        if value is not None:
            self.state = ExtractionState.FOUND
        return self

    def with_confidence(self, confidence: float) -> "Evidence":
        self.confidence = confidence
        if confidence is not None and float(confidence) < 0.5 and self.value is not None:
            self.state = ExtractionState.REQUIRES_REVIEW
        return self

    def at_position(self, page: int, x0: int = 0, y0: int = 0, x1: int = 0, y1: int = 0) -> "Evidence":
        self.page = page
        self.bounding_box = {"x0": x0, "y0": y0, "x1": x1, "y1": y1}
        return self

    def from_source(self, source: str) -> "Evidence":
        self.source = source
        return self

    def of_type(self, evidence_type: EvidenceType) -> "Evidence":
        self.evidence_type = evidence_type
        return self

    def add_transformation(self, transformation: str) -> "Evidence":
        self.transformation_log.append(transformation)
        return self

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "field_name": self.field_name,
            "value": self.value,
            "raw_value": self.raw_value,
            "state": self.state.value,
            "evidence_type": self.evidence_type.value,
            "confidence": self.confidence,
            "source": self.source,
            "transformation_log": self.transformation_log,
            "document_id": self.document_id,
            "page": self.page,
            "block_id": self.block_id,
            "bounding_box": self.bounding_box,
        }

    @staticmethod
    def builder() -> "Evidence":
        return Evidence()


@dataclass
class ExtractedField:
    field_name: str
    value: Any
    raw_value: Any
    state: ExtractionState
    evidence: list[Evidence]
    confidence: float
    normalized_value: Any = None

    @property
    def is_found(self) -> bool:
        return self.state == ExtractionState.FOUND

    @property
    def is_not_found(self) -> bool:
        return self.state == ExtractionState.NOT_FOUND

    @property
    def requires_review(self) -> bool:
        return self.state == ExtractionState.REQUIRES_REVIEW

    @property
    def best_evidence(self) -> Optional[Evidence]:
        if not self.evidence:
            return None
        return max(self.evidence, key=lambda e: e.confidence)

    @property
    def evidence_summary(self) -> str:
        if not self.evidence:
            return "No evidence"
        types = [e.evidence_type.value for e in self.evidence]
        return f"{len(self.evidence)} sources: {', '.join(set(types))}"

    def to_dict(self) -> dict:
        return {
            "field_name": self.field_name,
            "value": self.value,
            "raw_value": self.raw_value,
            "state": self.state.value,
            "confidence": self.confidence,
            "evidence_count": len(self.evidence),
            "normalized_value": self.normalized_value,
            "evidence_summary": self.evidence_summary,
        }

    @staticmethod
    def not_found(field_name: str) -> "ExtractedField":
        return ExtractedField(
            field_name=field_name,
            value=None,
            raw_value=None,
            state=ExtractionState.NOT_FOUND,
            evidence=[],
            confidence=0.0,
        )

    @staticmethod
    def found(field_name: str, value: Any, confidence: float = 1.0,
              evidence: Optional[list[Evidence]] = None) -> "ExtractedField":
        return ExtractedField(
            field_name=field_name,
            value=value,
            raw_value=value,
            state=ExtractionState.FOUND,
            evidence=evidence or [],
            confidence=confidence,
        )
