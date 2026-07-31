"""Tests for FASE 8.10 — Certification Alignment & Schema Registry."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from backend.app.v2.schema import (
    AutoFixSuggestions,
    CompatibilityChecker,
    ConsistencyReportGenerator,
    CoverageAnalyzer,
    DependencyValidator,
    FIELD_CATALOG,
    FieldDefinition,
    FieldMatrixGenerator,
    FieldRegistry,
    MODULES,
    REGISTRY,
    get_definitions,
)
from backend.app.v2.schema.coverage import KNOWLEDGE_FIELDS_REAL, _probe_catalog
from backend.app.v2.schema.validation import PRODUCERS
from backend.app.v2.fase8.certification_engine import (
    CertificationEngine,
    CertificationCriterion,
)
from backend.app.v2.fase8.stress_test import StressTestResult

GOLDEN_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..",
    "evaluation", "golden_dataset", "records.json"
))


# ─── Schema Registry (8.10.1) ─────────────────────────────────────────────────


class TestFieldDefinition:
    def test_full_definition(self):
        d = FieldDefinition(
            field_name="expediente",
            display_name="Expediente",
            description="Case number",
            data_type="text",
            country={"PA", "CO"},
            required=True,
            priority="critical",
            parser_supported=True,
        )
        assert d.is_supported_by("parser") is True
        assert d.is_supported_by("validator") is False

    def test_invalid_data_type_raises(self):
        with pytest.raises(ValueError):
            FieldDefinition(field_name="x", display_name="X", description="",
                            data_type="bogus")

    def test_invalid_priority_raises(self):
        with pytest.raises(ValueError):
            FieldDefinition(field_name="x", display_name="X", description="",
                            priority="bogus")

    def test_to_dict_roundtrip(self):
        d = get_definitions()[0]
        restored = FieldDefinition.from_dict(d.to_dict())
        assert restored.field_name == d.field_name
        assert restored.country == d.country

    def test_catalog_non_empty(self):
        assert len(FIELD_CATALOG) >= 30

    def test_catalog_unique_names(self):
        names = [d.field_name for d in FIELD_CATALOG]
        assert len(names) == len(set(names))

    def test_catalog_all_modules_supported_by_some_field(self):
        for module in MODULES:
            assert any(d.is_supported_by(module) for d in FIELD_CATALOG), module

    def test_required_core_fields_present(self):
        names = {d.field_name for d in FIELD_CATALOG}
        assert {"expediente", "demandante", "demandado", "precio_base",
                "fianza_porcentaje", "minimo_porcentaje"} <= names


class TestFieldRegistry:
    def test_get_and_resolve(self):
        assert REGISTRY.get("expediente").field_name == "expediente"
        assert REGISTRY.resolve("base").field_name == "base"
        assert REGISTRY.resolve("precio_base").field_name == "precio_base"
        assert REGISTRY.resolve("fecha").field_name == "fecha"
        assert REGISTRY.resolve("finca_matr").field_name == "finca_matr"
        assert REGISTRY.resolve("numero_expediente").field_name == "expediente"
        assert REGISTRY.canonical_name("numero_expediente") == "expediente"
        assert REGISTRY.canonical_name("fianza_porcentaje") == "fianza_porcentaje"

    def test_resolve_unknown_returns_none(self):
        assert REGISTRY.resolve("no_existe") is None

    def test_by_module(self):
        assert "expediente" in REGISTRY.by_module("parser")
        assert "expediente" in REGISTRY.by_module("normalizer")
        assert "fianza_porcentaje" in REGISTRY.by_module("golden_dataset")

    def test_by_country(self):
        assert "fianza_porcentaje" in REGISTRY.by_country("CO")
        assert "fianza_porcentaje" not in REGISTRY.by_country("PA")
        assert "provincia" in REGISTRY.by_country("PA")

    def test_is_supported(self):
        assert REGISTRY.is_supported("expediente", "parser")
        assert REGISTRY.is_supported("fianza_porcentaje", "parser")

    def test_required_and_critical(self):
        critical = {d.field_name for d in REGISTRY.critical_fields()}
        assert {"expediente", "demandante", "demandado", "precio_base"} <= critical

    def test_registry_serializable(self):
        data = REGISTRY.to_dict()
        assert data["total_fields"] == len(FIELD_CATALOG)
        json.dumps(data)

    def test_custom_registry(self):
        d = FieldDefinition(field_name="custom", display_name="C", description="",
                            parser_supported=True)
        reg = FieldRegistry([d])
        assert reg.field_names() == ["custom"]


# ─── Coverage Analyzer (8.10.3) ───────────────────────────────────────────────


class TestCoverageAnalyzer:
    def test_analyze_expediente_full(self):
        coverage = CoverageAnalyzer().analyze_field("expediente")
        assert coverage.coverage_pct == 100.0
        for module in ("parser", "knowledge", "validator", "normalizer",
                       "confidence", "golden_dataset", "certification"):
            assert coverage.by_module[module] is True

    def test_analyze_fianza_porcentaje_partial(self):
        coverage = CoverageAnalyzer().analyze_field("fianza_porcentaje")
        assert coverage.by_module["parser"] is True
        assert coverage.by_module["knowledge"] is False
        assert coverage.by_module["validator"] is True
        assert coverage.by_module["normalizer"] is True
        assert coverage.by_module["golden_dataset"] is True
        assert coverage.by_module["certification"] is True
        assert 0 < coverage.coverage_pct < 100

    def test_analyze_unknown_field(self):
        coverage = CoverageAnalyzer().analyze_field("no_existe")
        assert coverage.coverage_pct == 0.0

    def test_analyze_all_covers_registry(self):
        results = CoverageAnalyzer().analyze_all()
        assert len(results) == len(REGISTRY.field_names())

    def test_coverage_by_country(self):
        by_country = CoverageAnalyzer().coverage_by_country("CO")
        assert by_country["expediente"] == 100.0
        assert by_country["fianza_porcentaje"] < 100.0

    def test_coverage_by_document_type(self):
        analyzer = CoverageAnalyzer()
        pdf = analyzer.coverage_by_document_type("pdf_tabular")
        assert "fianza_porcentaje" in pdf
        newspaper = analyzer.coverage_by_document_type("newspaper_images")
        assert "fianza_porcentaje" not in newspaper
        assert "periodico" in newspaper

    def test_coverage_by_stage(self):
        stages = CoverageAnalyzer().coverage_by_stage()
        assert set(stages.keys()) == {"produccion", "validacion",
                                      "normalizacion", "confianza", "certificacion"}
        assert stages["produccion"]["expediente"] == 100.0

    def test_never_produced_detects_known_gap(self):
        never = CoverageAnalyzer().detect_never_produced()
        assert "fianza_porcentaje" not in never
        assert "minimo_porcentaje" not in never
        assert "descripcion" in never
        assert "expediente" not in never

    def test_orphan_fields_empty(self):
        assert CoverageAnalyzer().detect_orphan_fields() == []

    def test_duplicated_v1_v2_pairs(self):
        duplicated = CoverageAnalyzer().detect_duplicated_fields()
        assert "base" in duplicated
        assert "precio_base" in duplicated

    def test_inconsistent_names(self):
        pairs = CoverageAnalyzer().detect_inconsistent_names()
        aliases = {(p["canonical"], p["alias"]) for p in pairs}
        assert ("precio_base", "base") in aliases
        assert ("finca", "finca_matr") in aliases

    def test_redundant_aliases(self):
        redundant = CoverageAnalyzer().detect_redundant_aliases()
        assert "base" in redundant
        assert "finca_matr" in redundant

    def test_broken_dependencies(self):
        broken = CoverageAnalyzer().detect_broken_dependencies()
        fields = {b["field"] for b in broken}
        assert {"descripcion", "finca_matr"} <= fields
        assert "fianza_porcentaje" not in fields

    def test_duplicate_regexes_empty(self):
        assert CoverageAnalyzer().detect_duplicate_regexes() == []

    def test_alignment_pct_below_100(self):
        assert CoverageAnalyzer().alignment_pct() < 100.0

    def test_run_full_analysis(self):
        report = CoverageAnalyzer().run_full_analysis()
        assert report["total_fields"] == len(REGISTRY.field_names())
        assert report["coverage_by_country"]["CO"]
        assert report["coverage_by_stage"]["produccion"]
        json.dumps(report)


# ─── Dependency Validation (8.10.4) ───────────────────────────────────────────


class TestDependencyValidator:
    def test_who_produces(self):
        assert DependencyValidator().who_produces("expediente") == ["parser", "knowledge"]
        assert DependencyValidator().who_produces("fianza_porcentaje") == ["parser"]

    def test_who_consumes(self):
        consumers = DependencyValidator().who_consumes("expediente")
        assert "validator" in consumers
        assert "normalizer" in consumers
        assert "confidence" in consumers
        assert "golden_dataset" in consumers

    def test_who_validates_normalizes_certifies(self):
        dv = DependencyValidator()
        assert "validator" in dv.who_validates("expediente")
        assert "normalizer" in dv.who_normalizes("expediente")
        assert "certification" in dv.who_certifies("expediente")
        assert dv.who_certifies("plano") == []

    def test_build_graph(self):
        graph = DependencyValidator().build_graph()
        assert graph["nodes"]
        assert graph["edges"]
        node = next(n for n in graph["nodes"] if n["id"] == "expediente")
        assert "parser" in node["produces"]
        assert "validator" in node["validates"]

    def test_graph_serializable(self):
        json.dumps(DependencyValidator().build_graph())

    def test_graph_markdown(self):
        md = DependencyValidator().to_markdown()
        assert "| Campo |" in md
        assert "expediente" in md


# ─── Compatibility Checker (8.10.6) ───────────────────────────────────────────


class TestCompatibilityChecker:
    def test_check_parser_not_compatible(self):
        report = CompatibilityChecker().check_module("parser")
        fields = {i.field for i in report.issues}
        assert {"descripcion", "finca_matr"} <= fields
        assert report.compatible is False

    def test_check_confidence_compatible(self):
        report = CompatibilityChecker().check_module("confidence")
        assert report.compatible is True

    def test_check_golden_not_compatible(self):
        report = CompatibilityChecker().check_module("golden_dataset")
        assert report.compatible is False

    def test_check_certification_compatible(self):
        report = CompatibilityChecker().check_module("certification")
        assert report.issues == []
        assert report.compatible is True

    def test_check_all_covers_modules(self):
        reports = CompatibilityChecker().check_all()
        assert [r.module for r in reports] == MODULES

    def test_all_compatible_false(self):
        assert CompatibilityChecker().all_compatible() is False

    def test_certification_blockers(self):
        blockers = CompatibilityChecker().find_certification_blockers()
        assert blockers == []
        assert "fianza_porcentaje" not in blockers
        assert "minimo_porcentaje" not in blockers

    def test_report_serializable(self):
        report = CompatibilityChecker().check_module("parser")
        json.dumps(report.to_dict())

    def test_report_markdown(self):
        md = CompatibilityChecker().check_module("parser").to_markdown()
        assert "compatible = FALSE" in md
        assert "fianza_porcentaje" not in md
        assert "descripcion" in md


# ─── Certification Alignment (8.10.5) ─────────────────────────────────────────


class TestCertificationAlignment:
    def test_engine_init_sets_analyzer(self):
        engine = CertificationEngine(GOLDEN_PATH)
        assert engine.analyzer is not None
        assert engine.compat_checker is not None

    def test_run_alignment_check(self):
        engine = CertificationEngine(GOLDEN_PATH)
        alignment = engine.run_alignment_check()
        assert alignment["coverage_by_country"]["CO"]
        assert alignment["coverage_by_country"]["PA"]
        assert alignment["coverage_by_document_type"]["pdf_tabular"]
        assert alignment["coverage_by_stage"]["produccion"]
        assert alignment["golden_fields_without_parser"] == []
        assert "fianza_porcentaje" not in alignment["golden_fields_without_parser"]
        assert alignment["blocked"] is False

    def test_certified_passes_with_alignment(self):
        engine = CertificationEngine(GOLDEN_PATH)
        engine.regression.run_regression = MagicMock(
            return_value=MagicMock(
                to_dict=MagicMock(return_value={"overall_match_rate": 100.0,
                                                "summary": {"field_accuracy": {}}}),
                summary={"field_accuracy": {}},
            )
        )
        engine.stress.run_concurrent = MagicMock(
            return_value=StressTestResult(
                total_tasks=8, successful_tasks=8, failed_tasks=0,
                total_duration_ms=10.0, avg_task_duration_ms=1.0,
                max_task_duration_ms=2.0, min_task_duration_ms=0.5,
                throughput_tasks_per_sec=800.0, errors=[],
            )
        )
        engine.benchmark.run_all_benchmarks = MagicMock(
            return_value={"results": {"parser": {"throughput_records_per_sec": 50.0,
                                                 "memory_peak_mb": 10.0}}}
        )
        result = engine.run_certification()
        assert result.certified is True
        names = {c.name for c in result.criteria}
        assert "schema_alignment" in names
        assert result.details["schema_alignment"]["blocked"] is False
        assert "fianza_porcentaje" in result.details["schema_alignment"]["certified_fields"]

    def test_score_with_alignment_criteria(self):
        engine = CertificationEngine(GOLDEN_PATH)
        criteria = [
            CertificationCriterion(
                "parser_accuracy", "desc", 85, ">=", "%", passed=True, actual_value=95
            ),
        ]
        score = engine._calculate_score(criteria)
        assert score > 0


# ─── Field Matrix (8.10.7) ─────────────────────────────────────────────────────


class TestFieldMatrix:
    def test_matrix_rows(self):
        rows = FieldMatrixGenerator().generate_matrix()
        assert len(rows) == len(REGISTRY.field_names())
        expediente = next(r for r in rows if r["campo"] == "expediente")
        assert expediente["parser"] is True
        assert expediente["cobertura"] == 100.0
        assert expediente["obligatorio"] is True
        assert expediente["PA"] is True and expediente["CO"] is True

    def test_matrix_json(self):
        data = json.loads(FieldMatrixGenerator().to_json())
        assert data
        assert "fianza_porcentaje" in [r["campo"] for r in data]

    def test_matrix_markdown(self):
        md = FieldMatrixGenerator().to_markdown()
        assert "| Campo |" in md
        assert "fianza_porcentaje" in md
        assert "Cobertura" in md


# ─── Consistency Report (8.10.8) ──────────────────────────────────────────────


class TestConsistencyReport:
    def test_generate(self):
        report = ConsistencyReportGenerator().generate()
        assert "campos_faltantes" in report
        assert "dependencias_rotas" in report
        assert "porcentaje_alineacion" in report
        assert report["porcentaje_alineacion"] < 100.0
        broken_fields = {i["field"] for i in report["dependencias_rotas"]}
        assert "fianza_porcentaje" not in broken_fields
        assert "descripcion" in broken_fields

    def test_missing_fields_from_real_modules(self):
        report = ConsistencyReportGenerator().generate()
        assert isinstance(report["campos_faltantes"], list)
        for issue in report["campos_faltantes"]:
            assert issue["field"] not in REGISTRY.field_names()

    def test_report_serializable(self):
        report = ConsistencyReportGenerator().generate()
        json.dumps(report)

    def test_to_markdown(self):
        generator = ConsistencyReportGenerator()
        md = generator.to_markdown(generator.generate())
        assert "CONSISTENCY REPORT" in md
        assert "alineación" in md


# ─── Auto Fix Suggestions (8.10.9) ────────────────────────────────────────────


class TestAutoFixSuggestions:
    def test_generate(self):
        suggestions = AutoFixSuggestions().generate()
        assert suggestions

    def test_descripcion_suggestion(self):
        suggestions = AutoFixSuggestions().generate()
        descripcion = next(s for s in suggestions if s["campo"] == "descripcion")
        assert descripcion["accion"] == "agregar_campo"
        assert "Parser" in descripcion["recomendacion"]
        assert "Golden Dataset" in descripcion["porque"]
        fianza_suggestions = [s for s in suggestions if s["campo"] == "fianza_porcentaje"]
        assert fianza_suggestions == []

    def test_no_code_modified(self):
        before = {p: _probe_catalog(p) for p in MODULES}
        AutoFixSuggestions().generate()
        after = {p: _probe_catalog(p) for p in MODULES}
        assert before == after

    def test_suggestions_serializable(self):
        json.dumps(AutoFixSuggestions().generate())


# ─── Integration: registry vs real module catalogs ────────────────────────────


class TestRegistryAlignment:
    def test_validator_catalog_registered(self):
        validator_fields = set(_probe_catalog("validator"))
        for field in validator_fields:
            assert REGISTRY.resolve(field) is not None, field

    def test_normalizer_catalog_registered(self):
        normalizer_fields = set(_probe_catalog("normalizer"))
        for field in normalizer_fields:
            assert REGISTRY.resolve(field) is not None, field

    def test_regression_catalog_registered(self):
        regression_fields = set(_probe_catalog("regression"))
        for field in regression_fields:
            assert REGISTRY.resolve(field) is not None, field

    def test_golden_catalog_registered(self):
        golden_fields = set(_probe_catalog("golden_dataset"))
        for field in golden_fields:
            assert REGISTRY.resolve(field) is not None, field

    def test_parser_catalog_registered(self):
        parser_fields = set(_probe_catalog("parser"))
        assert parser_fields == {"expediente", "finca", "precio_base",
                                 "fecha_remate", "demandante", "demandado",
                                 "fianza_porcentaje", "minimo_porcentaje"}
        for field in parser_fields:
            assert REGISTRY.resolve(field) is not None, field

    def test_knowledge_real_fields(self):
        assert KNOWLEDGE_FIELDS_REAL <= set(REGISTRY.field_names())
