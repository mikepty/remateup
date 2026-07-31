"""FASE 11 — Production dataset validation."""

from backend.app.v2.evaluation.production.runner import ProductionDatasetRunner, SUPPORTED_EXTENSIONS
from backend.app.v2.evaluation.production.comparison import (
    compare_corpus,
    load_golden_records,
    compare_document,
)
from backend.app.v2.evaluation.production.report import generate_production_validation

__all__ = [
    "ProductionDatasetRunner",
    "SUPPORTED_EXTENSIONS",
    "compare_corpus",
    "load_golden_records",
    "compare_document",
    "generate_production_validation",
]
