from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class RuleStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    INACTIVE = "INACTIVE"


class RuleType(str, Enum):
    REGEX = "regex"
    ALIAS = "alias"
    FORMAT = "format"
    CONTEXTUAL = "contextual"


class KnowledgeCategory(str, Enum):
    LABEL = "label"
    MONEY = "money"
    DATE = "date"
    PERSON = "person"
    PROPERTY = "property"
    CASE_NUMBER = "case_number"


@dataclass
class KnowledgeEvidence:
    text_snippet: str = ""
    source_document: str = ""
    field_name: str = ""
    confidence: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "text_snippet": self.text_snippet[:200],
            "source_document": self.source_document,
            "field_name": self.field_name,
            "confidence": self.confidence,
        }


@dataclass
class KnowledgeRule:
    rule_id: str = ""
    rule_type: str = "regex"
    category: str = ""
    field_name: str = ""
    pattern: str = ""
    confidence: float = 0.0
    status: str = "PENDING"
    version: int = 1
    rollback_version: Optional[int] = None
    created_from_correction: str = ""
    approved_by: str = ""
    evidence: list[KnowledgeEvidence] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    usage_count: int = 0
    success_count: int = 0
    fail_count: int = 0

    @property
    def is_approved(self) -> bool:
        return self.status == "APPROVED"

    @property
    def is_pending(self) -> bool:
        return self.status == "PENDING"

    @property
    def is_rejected(self) -> bool:
        return self.status == "REJECTED"

    @property
    def is_inactive(self) -> bool:
        return self.status == "INACTIVE"

    @property
    def accuracy(self) -> float:
        if self.usage_count == 0:
            return 0.0
        return round(self.success_count / self.usage_count, 4)

    def approve(self, approved_by: str = ""):
        self.status = "APPROVED"
        if approved_by:
            self.approved_by = approved_by
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def reject(self):
        self.status = "REJECTED"
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def mark_inactive(self):
        self.status = "INACTIVE"
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def record_usage(self, success: bool):
        self.usage_count += 1
        if success:
            self.success_count += 1
        else:
            self.fail_count += 1

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "rule_type": self.rule_type,
            "category": self.category,
            "field": self.field_name,
            "pattern": self.pattern,
            "confidence": self.confidence,
            "status": self.status,
            "version": self.version,
            "rollback_version": self.rollback_version,
            "created_from_correction": self.created_from_correction,
            "approved_by": self.approved_by,
            "usage_count": self.usage_count,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "accuracy": self.accuracy,
            "evidence_count": len(self.evidence),
        }


@dataclass
class KnowledgeAlias:
    source: str = ""
    target: str = ""
    field_name: str = ""
    confidence: float = 0.0
    is_builtin: bool = False
    status: str = "PENDING"
    evidence: list[KnowledgeEvidence] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    usage_count: int = 0

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "field": self.field_name,
            "confidence": self.confidence,
            "is_builtin": self.is_builtin,
            "status": self.status,
            "usage_count": self.usage_count,
        }


@dataclass
class RuleHistory:
    history_id: Optional[int] = None
    rule_id: str = ""
    version: int = 0
    previous_status: str = ""
    new_status: str = ""
    accuracy_before: float = 0.0
    accuracy_after: float = 0.0
    reason: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "history_id": self.history_id,
            "rule_id": self.rule_id,
            "version": self.version,
            "previous_status": self.previous_status,
            "new_status": self.new_status,
            "accuracy_before": self.accuracy_before,
            "accuracy_after": self.accuracy_after,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


@dataclass
class ShadowComparison:
    comparison_id: Optional[int] = None
    document_id: str = ""
    field_name: str = ""
    parser_value: Any = None
    parser_confidence: float = 0.0
    knowledge_value: Any = None
    knowledge_confidence: float = 0.0
    knowledge_rule_id: str = ""
    knowledge_rule_version: int = 0
    winner: str = ""
    difference: bool = False
    evidence_text: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "comparison_id": self.comparison_id,
            "document_id": self.document_id,
            "field_name": self.field_name,
            "parser_value": self.parser_value,
            "parser_confidence": self.parser_confidence,
            "knowledge_value": self.knowledge_value,
            "knowledge_confidence": self.knowledge_confidence,
            "knowledge_rule_id": self.knowledge_rule_id,
            "winner": self.winner,
            "difference": self.difference,
            "evidence_text": self.evidence_text,
        }


@dataclass
class CorrectionEvent:
    document_id: str = ""
    country: str = ""
    field_name: str = ""
    previous_value: Any = None
    corrected_value: Any = None
    evidence_text: str = ""
    confidence: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "document_id": self.document_id,
            "country": self.country,
            "field_name": self.field_name,
            "previous_value": self.previous_value,
            "corrected_value": self.corrected_value,
            "evidence_text": self.evidence_text[:200],
            "confidence": self.confidence,
        }
