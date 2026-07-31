from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Decision(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    DUPLICATED = "DUPLICATED"
    LIKELY_DUPLICATED = "LIKELY_DUPLICATED"
    INCOMPLETE = "INCOMPLETE"
    INCONSISTENT = "INCONSISTENT"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"


class DuplicateLevel(str, Enum):
    UNIQUE = "UNIQUE"
    DUPLICATED = "DUPLICATED"
    LIKELY_DUPLICATED = "LIKELY_DUPLICATED"


@dataclass
class RuleResult:
    rule_name: str = ""
    passed: bool = False
    details: str = ""
    weight: float = 0.0

    def to_dict(self) -> dict:
        return {
            "rule_name": self.rule_name,
            "passed": self.passed,
            "details": self.details,
            "weight": self.weight,
        }


@dataclass
class Inconsistency:
    field_1: str = ""
    field_2: str = ""
    description: str = ""
    severity: str = "low"

    def to_dict(self) -> dict:
        return {
            "field_1": self.field_1,
            "field_2": self.field_2,
            "description": self.description,
            "severity": self.severity,
        }


@dataclass
class DuplicateInfo:
    level: DuplicateLevel = DuplicateLevel.UNIQUE
    matched_on: list[str] = field(default_factory=list)
    matched_notice_id: Optional[str] = None
    similarity: float = 0.0

    def to_dict(self) -> dict:
        return {
            "level": self.level.value,
            "matched_on": self.matched_on,
            "matched_notice_id": self.matched_notice_id,
            "similarity": self.similarity,
        }


@dataclass
class NoticeDecision:
    aviso_id: str = ""
    decision: Decision = Decision.REQUIRES_REVIEW
    score: float = 0.0
    rules_applied: list[RuleResult] = field(default_factory=list)
    rules_failed: list[RuleResult] = field(default_factory=list)
    fields_found: list[str] = field(default_factory=list)
    fields_missing: list[str] = field(default_factory=list)
    inconsistencies: list[Inconsistency] = field(default_factory=list)
    duplicate_info: Optional[DuplicateInfo] = None
    header_detected: str = ""
    header_valid: bool = False
    structural_valid: bool = False

    def to_dict(self) -> dict:
        return {
            "aviso_id": self.aviso_id,
            "decision": self.decision.value,
            "score": self.score,
            "rules_applied": [r.to_dict() for r in self.rules_applied],
            "rules_failed": [r.to_dict() for r in self.rules_failed],
            "fields_found": self.fields_found,
            "fields_missing": self.fields_missing,
            "inconsistencies": [i.to_dict() for i in self.inconsistencies],
            "duplicate_info": self.duplicate_info.to_dict() if self.duplicate_info else None,
            "header_detected": self.header_detected,
            "header_valid": self.header_valid,
            "structural_valid": self.structural_valid,
        }


@dataclass
class ValidationResult:
    decisions: list[NoticeDecision] = field(default_factory=list)
    total_avisos: int = 0
    valid_count: int = 0
    invalid_count: int = 0
    duplicated_count: int = 0
    incomplete_count: int = 0
    inconsistent_count: int = 0
    review_count: int = 0
    avg_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "total_avisos": self.total_avisos,
            "valid_count": self.valid_count,
            "invalid_count": self.invalid_count,
            "duplicated_count": self.duplicated_count,
            "incomplete_count": self.incomplete_count,
            "inconsistent_count": self.inconsistent_count,
            "review_count": self.review_count,
            "avg_score": self.avg_score,
            "decisions": [d.to_dict() for d in self.decisions],
        }
