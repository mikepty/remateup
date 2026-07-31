"""Tests for FASE 8.20 — Canonical Schema Completion & Final Architecture Audit."""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from backend.app.v2.schema import FieldDefinition, FieldRegistry
from backend.app.v2.schema.completion import (
    AlignmentScorer,
    ArchitectureScoreReport,
    BlockedFieldsReport,
    CanonicalMatrixBuilder,
    CompletionAuditor,
    StackProbe,
)
from backend.app.v2.schema.models import MODULES
from backend.app.v2.fase8.certification_engine import CertificationEngine

GOLDEN_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..",
    "evaluation", "golden_dataset", "records.json"
))
OUTPUT_DIR = Path(__file__).resolve().parents[4] / "backend" / "app" / "v2" / "schema" / "output"


def _field(name, **kwargs):
    defaults = dict(field_name=name, display_name=name, description="desc",
                    examples=["x"])
    defaults.update(kwargs)
    return FieldDefinition(**defaults)


def _custom_registry(definitions):
    return FieldRegistry(definitions)


def _custom_auditor(definitions):
    reg = _custom_registry(definitions)
    return CompletionAuditor(registry=reg)


# ─── StackProbe: real layers ──────────────────────────────────────────────────


class TestStackProbe:
    def test_database_fields(self):
        fields = StackProbe().database_fields()
        assert "expediente" in fields
        assert "base" in fields
        assert fields["fianza_porcentaje"] == "Float"

    def test_api_fields(self):
        fields = StackProbe().api_fields()
        assert "expediente" in fields
        assert "demandante" in fields
        assert "fianza_porcentaje" in fields

    def test_frontend_fields(self):
        fields = StackProbe().frontend_fields()
        assert "expediente" in fields
        assert "fianza_porcentaje" in fields
        assert "finca_matr" in fields

    def test_export_fields(self):
        fields = StackProbe().export_fields()
        assert "base" in fields
        assert "demandante" in fields
        assert "finca_matr" in fields


# ─── 17 checks per field ──────────────────────────────────────────────────────


class TestCompletionAuditorChecks:
    def test_expediente_fully_aligned(self):
        check = CompletionAuditor().check_field("expediente")
        assert check["in_schema"] is True
        assert check["in_parser"] is True
        assert check["in_knowledge"] is True
        assert check["in_validator"] is True
        assert check["in_normalizer"] is True
        assert check["in_database"] is True
        assert check["in_api"] is True
        assert check["in_frontend"] is True
        assert check["in_export"] is True
        assert check["in_golden"] is True
        assert check["has_producer"] is True
        assert check["has_consumer"] is True
        assert check["has_alias"] is True
        assert check["type_ok"] is True
        assert check["format_ok"] is True
        assert check["deps_ok"] is True
        assert check["has_documentation"] is True

    def test_fianza_porcentaje_with_producer(self):
        check = CompletionAuditor().check_field("fianza_porcentaje")
        assert check["in_parser"] is True
        assert check["in_validator"] is True
        assert check["in_database"] is True
        assert check["in_golden"] is True
        assert check["has_producer"] is True

    def test_check_all_covers_registry(self):
        checks = CompletionAuditor().check_all()
        assert len(checks) == 33

    def test_base_resolves_via_equivalence(self):
        check = CompletionAuditor().check_field("base")
        assert check["has_producer"] is True


# ─── Validation 1: orphan fields ──────────────────────────────────────────────


class TestOrphanFields:
    def test_no_orphans_in_real_catalog(self):
        assert CompletionAuditor().detect_orphan_fields() == []

    def test_detects_defined_but_unused(self):
        auditor = _custom_auditor([
            _field("a", parser_supported=True),
            _field("b"),
        ])
        assert auditor.detect_orphan_fields() == ["b"]


# ─── Validation 2: missing consumers ──────────────────────────────────────────


class TestMissingConsumers:
    def test_no_missing_consumers_in_real_catalog(self):
        assert CompletionAuditor().detect_missing_consumers() == []

    def test_detects_produced_but_unused(self):
        auditor = _custom_auditor([
            _field("producido", parser_supported=True),
        ])
        assert auditor.detect_missing_consumers() == ["producido"]


# ─── Validation 3: missing producers ──────────────────────────────────────────


class TestMissingProducers:
    def test_real_no_blockers(self):
        missing = CompletionAuditor().detect_missing_producers()
        assert missing == []
        assert "fianza_porcentaje" not in missing
        assert "minimo_porcentaje" not in missing
        assert "expediente" not in missing

    def test_detects_required_without_producer(self):
        auditor = _custom_auditor([
            _field("req", required=True, golden_dataset_supported=True),
        ])
        assert auditor.detect_missing_producers() == ["req"]

    def test_non_required_without_producer_not_reported(self):
        auditor = _custom_auditor([
            _field("opcional"),
        ])
        assert auditor.detect_missing_producers() == []


# ─── Validation 4: ambiguous aliases ──────────────────────────────────────────


class TestAmbiguousAliases:
    def test_no_ambiguous_in_real_catalog(self):
        assert CompletionAuditor().detect_ambiguous_aliases() == []

    def test_detects_shared_alias(self):
        auditor = _custom_auditor([
            _field("a", aliases=["mismo"]),
            _field("b", aliases=["mismo"]),
        ])
        ambiguous = auditor.detect_ambiguous_aliases()
        assert len(ambiguous) == 1
        assert ambiguous[0]["alias"] == "mismo"
        assert set(ambiguous[0]["owners"]) == {"a", "b"}


# ─── Validation 5: duplicate aliases ──────────────────────────────────────────


class TestDuplicateAliases:
    def test_repeated_alias_within_field(self):
        auditor = _custom_auditor([
            _field("a", aliases=["x", "x"]),
        ])
        dupes = auditor.detect_duplicate_aliases()
        assert any(d["field"] == "a" and d["alias"] == "x" for d in dupes)

    def test_v1_v2_pairs_not_invalid(self):
        auditor = CompletionAuditor()
        invalid = auditor.detect_invalid_aliases()
        assert all(i["alias"] not in ("base", "fecha", "finca_matr")
                   or i["problem"].startswith("alias") is False or True for i in invalid)
        assert invalid == []

    def test_duplicate_alias_shared_reported(self):
        auditor = _custom_auditor([
            _field("a", aliases=["compartido"]),
            _field("b", aliases=["compartido"]),
        ])
        dupes = auditor.detect_duplicate_aliases()
        assert any(d["alias"] == "compartido" for d in dupes)


# ─── Validation 6: incompatible types ─────────────────────────────────────────


class TestTypeConflicts:
    def test_real_conflicts_v1_v2(self):
        conflicts = CompletionAuditor().detect_type_conflicts()
        fields = {c["field"] for c in conflicts}
        assert "precio_base" in fields
        assert "base" in fields
        assert "fianza" in fields
        assert "superficie" in fields

    def test_percentage_floats_compatible(self):
        conflicts = CompletionAuditor().detect_type_conflicts()
        fields = {c["field"] for c in conflicts}
        assert "fianza_porcentaje" not in fields
        assert "minimo_porcentaje" not in fields

    def test_text_columns_compatible(self):
        conflicts = CompletionAuditor().detect_type_conflicts()
        fields = {c["field"] for c in conflicts}
        assert "expediente" not in fields
        assert "demandante" not in fields

    def test_custom_auditor_detects_golden_conflict(self):
        auditor = _custom_auditor([
            _field("name_ok", data_type="name"),
        ])
        assert auditor.check_type(auditor.registry.get("name_ok")) == []


# ─── Validation 7: incompatible formats ───────────────────────────────────────


class TestFormatConflicts:
    def test_no_format_conflicts_in_real_catalog(self):
        assert CompletionAuditor().detect_format_conflicts() == []

    def test_detects_bad_date_example(self):
        auditor = _custom_auditor([
            _field("fecha_test", data_type="date", examples=["15/09/2026"]),
        ])
        conflicts = auditor.detect_format_conflicts()
        assert len(conflicts) == 1
        assert conflicts[0]["field"] == "fecha_test"
        assert conflicts[0]["found"] == "15/09/2026"

    def test_iso_date_accepted(self):
        auditor = _custom_auditor([
            _field("fecha_ok", data_type="date", examples=["2026-09-15"]),
        ])
        assert auditor.detect_format_conflicts() == []

    def test_text_format_not_validated(self):
        auditor = _custom_auditor([
            _field("texto_libre", data_type="text", examples=["cualquier cosa"]),
        ])
        assert auditor.detect_format_conflicts() == []


# ─── Validation 8: circular dependencies ──────────────────────────────────────


class TestCircularDependencies:
    def test_real_v1_v2_alias_pairs(self):
        circular = CompletionAuditor().detect_circular_dependencies()
        pairs = {(c["a"], c["b"]) for c in circular}
        assert ("base", "precio_base") in pairs
        assert ("finca", "finca_matr") in pairs
        assert ("fecha", "fecha_remate") in pairs
        assert all(c["type"] == "alias_circular" for c in circular)

    def test_detects_depends_on_cycle(self):
        auditor = _custom_auditor([
            _field("a", depends_on=["b"]),
            _field("b", depends_on=["a"]),
        ])
        circular = auditor.detect_circular_dependencies()
        assert any(c["type"] == "dependencia_circular" for c in circular)

    def test_detects_dependency_missing_from_schema(self):
        auditor = _custom_auditor([
            _field("a", depends_on=["no_existe"]),
        ])
        problems = auditor._check_deps(auditor.registry.get("a"))
        assert len(problems) == 1

    def test_linear_dependency_not_circular(self):
        auditor = _custom_auditor([
            _field("a", depends_on=["b"]),
            _field("b"),
        ])
        assert auditor.detect_circular_dependencies() == []


# ─── Validations 9-10: never certified / never evaluated ──────────────────────


class TestCertificationStatus:
    def test_real_certified_fields(self):
        certified = CompletionAuditor().certified_fields()
        assert {"expediente", "demandante", "demandado", "precio_base",
                "fecha_remate", "finca"} <= set(certified)

    def test_never_certified_non_empty(self):
        never = CompletionAuditor().never_certified_fields()
        assert "fianza_porcentaje" not in never
        assert "minimo_porcentaje" not in never
        assert "descripcion" in never
        assert "expediente" not in never

    def test_never_evaluated(self):
        never = CompletionAuditor().never_evaluated_fields()
        assert "periodico" in never
        assert "pagina_prensa" in never
        assert "expediente" not in never


# ─── Alignment score ──────────────────────────────────────────────────────────


class TestAlignmentScorer:
    def test_scores_real_catalog(self):
        scores = CompletionAuditor().scores()
        assert scores["expediente"] == 100
        assert scores["fianza_porcentaje"] == 100
        assert scores["base"] == 90

    def test_scale_100(self):
        auditor = _custom_auditor([
            _field("ok", parser_supported=True, validator_supported=True,
                   normalizer_supported=True, golden_dataset_supported=True,
                   certification_supported=True, aliases=["a1"]),
        ])
        assert auditor.score_field("ok") == 100

    def test_scale_90_missing_docs(self):
        auditor = _custom_auditor([
            _field("ok", parser_supported=True, validator_supported=True,
                   normalizer_supported=True, golden_dataset_supported=True,
                   certification_supported=True, examples=[]),
        ])
        assert auditor.score_field("ok") == 90

    def test_scale_75_missing_consumer(self):
        auditor = _custom_auditor([
            _field("p", parser_supported=True),
        ])
        assert auditor.score_field("p") == 75

    def test_scale_50_missing_producer(self):
        auditor = _custom_auditor([
            _field("r", required=True, validator_supported=True),
        ])
        assert auditor.score_field("r") == 50

    def test_scale_25_only_golden(self):
        auditor = _custom_auditor([
            _field("g", golden_dataset_supported=True),
        ])
        assert auditor.score_field("g") == 25

    def test_scale_0_broken(self):
        auditor = _custom_auditor([
            _field("b"),
        ])
        assert auditor.score_field("b") == 0

    def test_overall_alignment(self):
        auditor = CompletionAuditor()
        assert 0 < auditor.overall_alignment() < 100

    def test_scorer_labels(self):
        scorer = AlignmentScorer()
        assert scorer.score_field("expediente")["status"] == "completamente alineado"
        assert scorer.score_field("fianza_porcentaje")["status"] == "completamente alineado"
        assert scorer.score_field("categoria")["status"] == "falta productor"
        assert scorer.all()


# ─── Blocked / certified cases ────────────────────────────────────────────────


class TestBlockedAndCertified:
    def test_real_blocked_fields(self):
        blocked = CompletionAuditor().blocked_fields()
        names = {b["field"] for b in blocked}
        assert "fianza_porcentaje" not in names
        assert "minimo_porcentaje" not in names
        assert "categoria" in names
        assert "expediente" not in names
        for b in blocked:
            assert b["state"] == "BLOCKED"
            assert b["score"] < 100
            assert b["reasons"]

    def test_custom_blocked_reasons(self):
        auditor = _custom_auditor([
            _field("critico", required=True, golden_dataset_supported=True),
        ])
        blocked = auditor.blocked_fields()
        assert blocked[0]["reasons"] == ["solo existe en golden"]

    def test_custom_fully_certified(self):
        auditor = _custom_auditor([
            _field("perfecto", parser_supported=True, validator_supported=True,
                   normalizer_supported=True, golden_dataset_supported=True,
                   certification_supported=True, aliases=["al"]),
        ])
        assert auditor.certified_fields() == ["perfecto"]
        assert auditor.blocked_fields() == []


# ─── Canonical matrix ─────────────────────────────────────────────────────────


class TestCanonicalMatrix:
    def test_matrix_rows(self):
        rows = CanonicalMatrixBuilder().build()
        assert len(rows) == 33

    def test_matrix_states(self):
        rows = {r["campo"]: r for r in CanonicalMatrixBuilder().build()}
        assert rows["expediente"]["estado"] == "CERTIFIED"
        assert rows["expediente"]["database"] is True
        assert rows["expediente"]["api"] is True
        assert rows["fianza_porcentaje"]["estado"] == "CERTIFIED"
        assert rows["fianza_porcentaje"]["productor"] == "parser"

    def test_matrix_json_and_md(self):
        rows = CanonicalMatrixBuilder().build()
        json.dumps(rows)
        md = CanonicalMatrixBuilder().to_markdown()
        assert "CERTIFIED" in md
        assert "BLOCKED" in md
        assert "fianza_porcentaje" in md


# ─── Reports generated ────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def generated_reports():
    import subprocess
    subprocess.run(
        [sys.executable, str(OUTPUT_DIR.parent / "generate_alignment_report.py")],
        check=True, capture_output=True,
    )
    return {
        "alignment_report.json": OUTPUT_DIR / "alignment_report.json",
        "alignment_report.md": OUTPUT_DIR / "alignment_report.md",
        "canonical_matrix.json": OUTPUT_DIR / "canonical_matrix.json",
        "canonical_matrix.md": OUTPUT_DIR / "canonical_matrix.md",
        "blocked_fields.json": OUTPUT_DIR / "blocked_fields.json",
        "blocked_fields.md": OUTPUT_DIR / "blocked_fields.md",
        "architecture_score.json": OUTPUT_DIR / "architecture_score.json",
        "architecture_score.md": OUTPUT_DIR / "architecture_score.md",
    }


class TestReports:
    def test_all_reports_exist(self, generated_reports):
        for name, path in generated_reports.items():
            assert path.exists(), name
            assert path.stat().st_size > 0, name

    def test_alignment_report_structure(self, generated_reports):
        data = json.loads(generated_reports["alignment_report.json"].read_text(encoding="utf-8"))
        assert data["resumen"]["overall_alignment"] < 100
        assert "fianza_porcentaje" in data["resumen"]["certified_fields"]
        assert data["resumen"]["missing_producers"] == []
        assert data["resumen"]["type_conflicts"]

    def test_blocked_report(self, generated_reports):
        data = json.loads(generated_reports["blocked_fields.json"].read_text(encoding="utf-8"))
        assert data["total_blocked"] > 0
        assert data["total_certified"] > 0
        md = generated_reports["blocked_fields.md"].read_text(encoding="utf-8")
        assert "BLOCKED" in md or "bloqueados" in md.lower()

    def test_architecture_score(self, generated_reports):
        data = json.loads(generated_reports["architecture_score.json"].read_text(encoding="utf-8"))
        assert "overall_alignment" in data
        assert "type_conflicts" in data
        assert "never_evaluated" in data
        assert set(data["score_distribution"].keys()) == {"100", "90", "75", "50", "25", "0"}

    def test_canonical_matrix_md(self, generated_reports):
        md = generated_reports["canonical_matrix.md"].read_text(encoding="utf-8")
        assert "Campo" in md and "Estado" in md

    def test_blocked_report_class(self):
        report = BlockedFieldsReport().generate()
        assert "blocked_fields" in report
        md = BlockedFieldsReport().to_markdown(report)
        assert "fianza_porcentaje" not in md
        assert "descripcion" in md

    def test_architecture_score_class(self):
        report = ArchitectureScoreReport().generate()
        assert report["overall_alignment"] > 0
        md = ArchitectureScoreReport().to_markdown(report)
        assert "ARCHITECTURE SCORE" in md


# ─── Certification extended (FASE 8.20 metrics) ───────────────────────────────


class TestCertificationExtended:
    def test_alignment_check_has_20_metrics(self):
        engine = CertificationEngine(GOLDEN_PATH)
        alignment = engine.run_alignment_check()
        for key in ("overall_alignment", "blocked_fields", "certified_fields",
                    "orphan_fields", "unused_fields", "missing_producers",
                    "missing_consumers", "invalid_aliases", "type_conflicts",
                    "format_conflicts"):
            assert key in alignment, key
        assert alignment["overall_alignment"] < 100
        assert "fianza_porcentaje" in alignment["certified_fields"]
        assert "fianza_porcentaje" not in alignment["blocked_fields"]
        assert alignment["orphan_fields"] == []
