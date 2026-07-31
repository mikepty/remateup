"""FASE 8.10.1 — Schema Registry models.

Single source of truth for field definitions shared by Parser, Knowledge,
Validator, Normalizer, Confidence, Golden Dataset, Regression and Certification.
No field definition lives in more than one place.
"""

from dataclasses import dataclass, field
from typing import Any, Optional


MODULES = [
    "parser",
    "knowledge",
    "validator",
    "normalizer",
    "confidence",
    "golden_dataset",
    "certification",
    "regression",
]

COUNTRY_CO = "CO"
COUNTRY_PA = "PA"

DOC_TYPES = ["pdf_tabular", "newspaper_images", "individual_images"]

DATA_TYPES = ("text", "number", "currency", "date", "name", "location")

PRIORITIES = ("critical", "high", "medium", "low")


@dataclass
class FieldDefinition:
    """Canonical definition of a single extraction field."""

    field_name: str
    display_name: str
    description: str
    data_type: str = "text"
    country: set = field(default_factory=set)
    document_type: set = field(default_factory=set)
    required: bool = False
    priority: str = "medium"
    parser_supported: bool = False
    knowledge_supported: bool = True
    validator_supported: bool = False
    normalizer_supported: bool = False
    confidence_supported: bool = True
    golden_dataset_supported: bool = False
    certification_supported: bool = False
    regression_supported: bool = False
    aliases: list = field(default_factory=list)
    regex_patterns: list = field(default_factory=list)
    examples: list = field(default_factory=list)
    depends_on: list = field(default_factory=list)
    deprecated: bool = False
    version: str = "1.0"

    def __post_init__(self):
        if self.data_type not in DATA_TYPES:
            raise ValueError(f"Invalid data_type '{self.data_type}' for field '{self.field_name}'")
        if self.priority not in PRIORITIES:
            raise ValueError(f"Invalid priority '{self.priority}' for field '{self.field_name}'")

    def is_supported_by(self, module: str) -> bool:
        flag = f"{module}_supported"
        return bool(getattr(self, flag, False))

    def to_dict(self) -> dict:
        return {
            "field_name": self.field_name,
            "display_name": self.display_name,
            "description": self.description,
            "data_type": self.data_type,
            "country": sorted(self.country),
            "document_type": sorted(self.document_type),
            "required": self.required,
            "priority": self.priority,
            "parser_supported": self.parser_supported,
            "knowledge_supported": self.knowledge_supported,
            "validator_supported": self.validator_supported,
            "normalizer_supported": self.normalizer_supported,
            "confidence_supported": self.confidence_supported,
            "golden_dataset_supported": self.golden_dataset_supported,
            "certification_supported": self.certification_supported,
            "regression_supported": self.regression_supported,
            "aliases": list(self.aliases),
            "regex_patterns": list(self.regex_patterns),
            "examples": list(self.examples),
            "depends_on": list(self.depends_on),
            "deprecated": self.deprecated,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FieldDefinition":
        d = dict(d)
        d["country"] = set(d.get("country", []))
        d["document_type"] = set(d.get("document_type", []))
        return cls(**d)


@dataclass
class FieldCoverage:
    """Coverage of a single field across all modules (8.10.3)."""

    field_name: str
    by_module: dict = field(default_factory=dict)
    coverage_pct: float = 0.0

    def to_dict(self) -> dict:
        return {
            "field_name": self.field_name,
            "by_module": dict(self.by_module),
            "coverage_pct": self.coverage_pct,
        }

    def to_markdown(self, modules: Optional[list] = None) -> str:
        mods = modules or list(self.by_module.keys())
        checks = "".join(
            "✔" if self.by_module.get(m) else "✘" for m in mods
        )
        return f"`{self.field_name}` {checks} Coverage {self.coverage_pct:.0f}%"


@dataclass
class DependencyEdge:
    """Serializable edge in the field dependency graph (8.10.4)."""

    field_name: str
    producer: str
    consumer: str
    action: str = "consume"

    def to_dict(self) -> dict:
        return {
            "field_name": self.field_name,
            "producer": self.producer,
            "consumer": self.consumer,
            "action": self.action,
        }


@dataclass
class ConsistencyIssue:
    """A single consistency problem found by the analyzers (8.10.8)."""

    issue_type: str
    module: str
    field: str
    problem: str
    solution: str = ""

    def to_dict(self) -> dict:
        return {
            "issue_type": self.issue_type,
            "module": self.module,
            "field": self.field,
            "problem": self.problem,
            "solution": self.solution,
        }


@dataclass
class CompatibilityReport:
    """Per-module compatibility result (8.10.6)."""

    module: str
    compatible: bool
    issues: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "module": self.module,
            "compatible": self.compatible,
            "issues": [i.to_dict() if isinstance(i, ConsistencyIssue) else i for i in self.issues],
        }

    def to_markdown(self) -> str:
        status = "TRUE" if self.compatible else "FALSE"
        lines = [f"### {self.module}: compatible = {status}"]
        for i in self.issues:
            lines.append(
                f"- **{i.module}** / `{i.field}` — {i.problem}"
                + (f" → **Solución:** {i.solution}" if i.solution else "")
            )
        return "\n".join(lines)
