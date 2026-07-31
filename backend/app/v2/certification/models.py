from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class CertDecision(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    DUPLICATED = "DUPLICATED"
    LIKELY_DUPLICATED = "LIKELY_DUPLICATED"
    INCOMPLETE = "INCOMPLETE"
    INCONSISTENT = "INCONSISTENT"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"


@dataclass
class CertField:
    name: str = ""
    value: Any = None
    raw_value: Any = None
    normalized_value: Any = None
    confidence: float = 0.0
    confidence_reason: str = ""
    confidence_sources: dict = field(default_factory=dict)
    status: str = "not_found"
    source: str = "unknown"
    evidence: list = field(default_factory=list)
    normalization: dict = field(default_factory=dict)


@dataclass
class CertAviso:
    id: str = ""
    fields: list[CertField] = field(default_factory=list)
    decision: CertDecision = CertDecision.REQUIRES_REVIEW
    score: float = 0.0
    confidence: float = 0.0
    header_detected: str = ""
    header_valid: bool = False
    inconsistencies: list = field(default_factory=list)
    duplicate_info: Optional[dict] = None
    rules_applied: list = field(default_factory=list)
    rules_failed: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    fields_missing: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "fields": [f.__dict__ for f in self.fields],
            "decision": self.decision.value,
            "score": self.score,
            "confidence": self.confidence,
            "header_detected": self.header_detected,
            "header_valid": self.header_valid,
            "inconsistencies": self.inconsistencies,
            "duplicate_info": self.duplicate_info,
            "rules_applied": self.rules_applied,
            "rules_failed": self.rules_failed,
            "warnings": self.warnings,
        }


@dataclass
class CertPage:
    page_number: int = 0
    width: int = 0
    height: int = 0
    ocr_text: str = ""
    avisos: list[CertAviso] = field(default_factory=list)


@dataclass
class CertDocument:
    document_id: str = ""
    source_type: str = ""
    country: str = ""
    pages: list[CertPage] = field(default_factory=list)
    all_avisos: list[CertAviso] = field(default_factory=list)
    valid_count: int = 0
    invalid_count: int = 0
    duplicated_count: int = 0
    incomplete_count: int = 0
    inconsistent_count: int = 0
    review_count: int = 0
    total_time_ms: float = 0.0
    version: str = ""
    knowledge_version: str = ""
    validator_version: str = ""
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    statistics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "document_id": self.document_id,
            "source_type": self.source_type,
            "country": self.country,
            "pages": [p.__dict__ for p in self.pages],
            "all_avisos": [a.to_dict() for a in self.all_avisos],
            "summary": {
                "total_avisos": len(self.all_avisos),
                "valid": self.valid_count,
                "invalid": self.invalid_count,
                "duplicated": self.duplicated_count,
                "incomplete": self.incomplete_count,
                "inconsistent": self.inconsistent_count,
                "review": self.review_count,
            },
            "total_time_ms": self.total_time_ms,
            "version": self.version,
            "knowledge_version": self.knowledge_version,
            "validator_version": self.validator_version,
            "errors": self.errors,
            "warnings": self.warnings,
            "statistics": self.statistics,
        }
