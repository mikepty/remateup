"""FASE 8.10 — Certification Alignment & Schema Registry.

Single source of truth for field definitions and automated alignment
analysis across Parser, Knowledge, Validator, Normalizer, Confidence,
Golden Dataset, Regression and Certification.
"""

from backend.app.v2.schema.models import (
    CompatibilityReport,
    ConsistencyIssue,
    DependencyEdge,
    FieldCoverage,
    FieldDefinition,
    MODULES,
)
from backend.app.v2.schema.field_registry import FieldRegistry, REGISTRY
from backend.app.v2.schema.definitions import FIELD_CATALOG, get_definitions
from backend.app.v2.schema.coverage import (
    ConsistencyReportGenerator,
    CoverageAnalyzer,
    FieldMatrixGenerator,
)
from backend.app.v2.schema.validation import (
    AutoFixSuggestions,
    CompatibilityChecker,
    DependencyValidator,
)

__all__ = [
    "AutoFixSuggestions",
    "CompatibilityChecker",
    "CompatibilityReport",
    "ConsistencyIssue",
    "ConsistencyReportGenerator",
    "CoverageAnalyzer",
    "DependencyEdge",
    "DependencyValidator",
    "FIELD_CATALOG",
    "FieldCoverage",
    "FieldDefinition",
    "FieldMatrixGenerator",
    "FieldRegistry",
    "MODULES",
    "REGISTRY",
    "get_definitions",
]
