"""Tests for FASE 9 — Parser Completion & Canonical Type Resolution."""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from backend.app.v2.parser.context import ParserContext
from backend.app.v2.parser.documents.colombia_remate import ColombiaRemateParser
from backend.app.v2.normalization.normalizer import FieldNormalizer
from backend.app.v2.normalization.numbers import PercentageNormalizer, words_to_number
from backend.app.v2.schema.completion import (
    AlignmentScorer,
    CanonicalMatrixBuilder,
    CompletionAuditor,
)
from backend.app.v2.schema.coverage import CoverageAnalyzer
from backend.app.v2.fase8.certification_engine import CertificationEngine

GOLDEN_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..",
    "evaluation", "golden_dataset", "records.json"
))

PARSER = ColombiaRemateParser()

FIANZA_VARIANTS = [
    ("FIANZA: 40%", 40, "40%"),
    ("FIANZA 40 %", 40, "40%"),
    ("FIANZA DEL POSTOR 40%", 40, "40%"),
    ("PORCENTAJE DE FIANZA 40%", 40, "40%"),
    ("FIANZA: CUARENTA POR CIENTO", 40, "CUARENTA POR CIENTO"),
    ("FIANZA\n40%", 40, "40%"),
]

MINIMO_VARIANTS = [
    ("MÍNIMO 70%", 70, "70%"),
    ("MÍNIMO: 70 %", 70, "70%"),
    ("MINIMO 70%", 70, "70%"),
    ("POSTURA ADMISIBLE 70%", 70, "70%"),
    ("PORCENTAJE MÍNIMO 70%", 70, "70%"),
    ("PORCENTAJE MÍNIMO DE LA POSTURA: 70%", 70, "70%"),
    ("BASE MÍNIMA 70%", 70, "70%"),
    ("MINIMO\n70%", 70, "70%"),
]


def _parse(text: str):
    return PARSER.parse(ParserContext(country="CO", document_type="REMATE", text=text))


class TestFianzaPorcentajeExtraction:
    @pytest.mark.parametrize("text,expected,original", FIANZA_VARIANTS)
    def test_extraction(self, text, expected, original):
        result = _parse(text)["fianza_porcentaje"]
        assert result.status == "FOUND"
        assert result.value == expected
        assert result.original_value == original

    def test_not_invented_when_absent(self):
        result = _parse("AVISO DE REMATE SIN DATOS")["fianza_porcentaje"]
        assert result.status == "NOT_FOUND"
        assert result.value is None


class TestMinimoPorcentajeExtraction:
    @pytest.mark.parametrize("text,expected,original", MINIMO_VARIANTS)
    def test_extraction(self, text, expected, original):
        result = _parse(text)["minimo_porcentaje"]
        assert result.status == "FOUND"
        assert result.value == expected
        assert result.original_value == original

    def test_not_invented_when_absent(self):
        result = _parse("AVISO DE REMATE SIN DATOS")["minimo_porcentaje"]
        assert result.status == "NOT_FOUND"
        assert result.value is None


class TestPercentageVariants:
    def test_fianza_does_not_leak_into_minimo(self):
        results = _parse("FIANZA: 40%")
        assert results["fianza_porcentaje"].is_found
        assert not results["minimo_porcentaje"].is_found

    def test_minimo_does_not_leak_into_fianza(self):
        results = _parse("MINIMO: 70%")
        assert results["minimo_porcentaje"].is_found
        assert not results["fianza_porcentaje"].is_found

    def test_both_fields_in_same_aviso(self):
        results = _parse("FIANZA DEL POSTOR: 40%\nPORCENTAJE MÍNIMO DE LA POSTURA: 70%")
        assert results["fianza_porcentaje"].value == 40
        assert results["minimo_porcentaje"].value == 70

    def test_decimal_percentage_input(self):
        result = _parse("FIANZA: 0.40")["fianza_porcentaje"]
        assert result.status == "FOUND"
        assert result.value == 0.4

    def test_percentage_with_spaces(self):
        result = _parse("FIANZA  40  %")["fianza_porcentaje"]
        assert result.value == 40
        assert result.original_value == "40%"

    def test_words_compound(self):
        result = _parse("FIANZA: SESENTA Y CINCO POR CIENTO")["fianza_porcentaje"]
        assert result.value == 65
        assert result.original_value == "SESENTA Y CINCO POR CIENTO"


class TestEvidenceAndConfidence:
    def test_evidence_present(self):
        result = _parse("FIANZA DEL POSTOR: 40%")["fianza_porcentaje"]
        assert result.evidence
        ev = result.evidence[0]
        assert ev["method"] == "regex:fianza_porcentaje"
        assert "FIANZA" in ev["snippet"]
        assert ev["confidence"] == 0.95

    def test_confidence(self):
        result = _parse("MINIMO: 70%")["minimo_porcentaje"]
        assert result.confidence == 0.95

    def test_to_dict_exposes_original_and_normalized(self):
        data = _parse("FIANZA: 40%")["fianza_porcentaje"].to_dict()
        assert data["valor_original"] == "40%"
        assert data["valor_normalizado"] == 40
        assert data["status"] == "FOUND"


class TestNormalization:
    def test_percentage_normalizer(self):
        normalizer = PercentageNormalizer()
        assert normalizer.normalize("40%")["valor_normalizado"] == 40
        assert normalizer.normalize("70 %")["valor_normalizado"] == 70
        assert normalizer.normalize("0.40")["valor_normalizado"] == 40
        assert normalizer.normalize("CUARENTA POR CIENTO")["valor_normalizado"] == 40
        assert normalizer.normalize("40%")["valor_original"] == "40%"
        assert normalizer.normalize("")["success"] is False

    def test_words_to_number(self):
        assert words_to_number("CUARENTA") == 40.0
        assert words_to_number("SESENTA Y CINCO") == 65.0
        assert words_to_number("CIENTO") is None
        assert words_to_number("CERO") == 0.0
        assert words_to_number("40") is None

    def test_field_normalizer_routes_percentages(self):
        field_normalizer = FieldNormalizer()
        result = field_normalizer.normalize_field("fianza_porcentaje", "0.40")
        assert result["valor_original"] == "0.40"
        assert result["valor_normalizado"] == 40
        assert result["success"] is True

    def test_field_normalizer_keeps_original_text(self):
        field_normalizer = FieldNormalizer()
        result = field_normalizer.normalize_field("minimo_porcentaje", "70 %")
        assert result["valor_original"] == "70 %"
        assert result["valor_normalizado"] == 70


class TestCertificationIntegration:
    def test_alignment_no_missing_producers(self):
        engine = CertificationEngine(GOLDEN_PATH)
        alignment = engine.run_alignment_check()
        assert alignment["missing_producers"] == []
        assert alignment["golden_fields_without_parser"] == []
        assert alignment["blocked"] is False

    def test_percentage_fields_certified(self):
        engine = CertificationEngine(GOLDEN_PATH)
        alignment = engine.run_alignment_check()
        certified = set(alignment["certified_fields"])
        assert {"fianza_porcentaje", "minimo_porcentaje"} <= certified
        assert "fianza_porcentaje" not in set(alignment["blocked_fields"])

    def test_auditor_no_blockers(self):
        auditor = CompletionAuditor()
        assert auditor.detect_missing_producers() == []
        assert auditor.check_field("fianza_porcentaje")["has_producer"] is True
        assert auditor.check_field("minimo_porcentaje")["has_producer"] is True

    def test_scorer_100(self):
        scorer = AlignmentScorer()
        assert scorer.score_field("fianza_porcentaje")["score"] == 100
        assert scorer.score_field("minimo_porcentaje")["score"] == 100


class TestCoverageIntegration:
    def test_parser_coverage_true(self):
        coverage = CoverageAnalyzer().analyze_field("fianza_porcentaje")
        assert coverage.by_module["parser"] is True
        assert coverage.by_module["normalizer"] is True
        assert coverage.coverage_pct > 0

    def test_never_produced_excludes_percentages(self):
        never = CoverageAnalyzer().detect_never_produced()
        assert "fianza_porcentaje" not in never
        assert "minimo_porcentaje" not in never


class TestCanonicalMatrixIntegration:
    def test_percentage_fields_certified_in_matrix(self):
        rows = {r["campo"]: r for r in CanonicalMatrixBuilder().build()}
        assert rows["fianza_porcentaje"]["estado"] == "CERTIFIED"
        assert rows["fianza_porcentaje"]["productor"] == "parser"
        assert rows["minimo_porcentaje"]["estado"] == "CERTIFIED"
        assert rows["minimo_porcentaje"]["productor"] == "parser"


class TestColombiaParserFullRegression:
    def test_all_supported_fields_parse_aviso(self):
        text = """
        AVISO DE REMATE
        EXPEDIENTE N° 2025-00456
        MATRÍCULA INMOBILIARIA N° 050-123456
        AVALÚO COMERCIAL: $500,000,000
        FECHA DE REMATE: 20 DE DICIEMBRE DE 2026
        DEMANDANTE: BANCO DE BOGOTA
        DEMANDADO: PEDRO PABLO PEREZ LOPEZ
        FIANZA DEL POSTOR: 40%
        PORCENTAJE MÍNIMO DE LA POSTURA: 70%
        """
        results = _parse(text)
        for field in PARSER.supported_fields:
            assert results[field].is_found, f"{field} should be FOUND"

    def test_supported_fields_are_eight(self):
        assert set(PARSER.supported_fields) == {
            "expediente", "finca", "precio_base", "fecha_remate",
            "demandante", "demandado", "fianza_porcentaje", "minimo_porcentaje",
        }

    def test_no_cross_field_pollution(self):
        results = _parse("DEMANDANTE: JUAN\nDEMANDADO: PEDRO\nFIANZA: 40%")
        assert results["demandante"].value == "JUAN"
        assert results["demandado"].value == "PEDRO"
        assert results["fianza_porcentaje"].value == 40
        assert not results["minimo_porcentaje"].is_found
