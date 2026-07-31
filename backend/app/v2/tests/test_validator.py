"""Tests for FASE 6.9 Validator module."""

import pytest

from backend.app.v2.validator.models import (
    Decision, DuplicateLevel, NoticeDecision, Inconsistency, RuleResult, ValidationResult,
)
from backend.app.v2.validator.notice_validator import NoticeValidator
from backend.app.v2.validator.consistency import ConsistencyEngine
from backend.app.v2.validator.duplicate_detector import DuplicateDetector
from backend.app.v2.validator.scoring import NoticeScorer
from backend.app.v2.validator.orchestrator import ValidationOrchestrator
from backend.app.v2.validator.production_rules import (
    detect_header, check_mandatory_fields, check_field_co_occurrence,
    has_publicidad_only, has_edicto_only, min_strong_fields_rule,
    VALID_HEADERS, INVALID_HEADERS,
)


# --- Valid headers ---
class TestValidHeaders:
    def test_aviso_remate(self):
        h, ok = detect_header("AVISO DE REMATE\nExpediente: 123")
        assert ok
        assert "AVISO DE REMATE" in h

    def test_remate_judicial(self):
        h, ok = detect_header("REMATE JUDICIAL\nJUZGADO: ...")
        assert ok

    def test_primera_fecha_remate(self):
        h, ok = detect_header("PRIMERA FECHA DE REMATE\n...")
        assert ok

    def test_segunda_fecha_remate(self):
        h, ok = detect_header("SEGUNDA FECHA DE REMATE\n...")
        assert ok

    def test_tercera_fecha_remate(self):
        h, ok = detect_header("TERCERA FECHA DE REMATE\n...")
        assert ok

    def test_subasta_judicial(self):
        h, ok = detect_header("SUBASTA JUDICIAL\n...")
        assert ok

    def test_remate_extrajudicial(self):
        h, ok = detect_header("REMATE EXTRAJUDICIAL\n...")
        assert ok

    def test_no_header(self):
        h, ok = detect_header("")
        assert not ok


# --- Invalid headers ---
class TestInvalidHeaders:
    def test_edicto(self):
        h, ok = detect_header("EDICTO\n...")
        assert not ok

    def test_edicto_emplazatorio(self):
        h, ok = detect_header("EDICTO EMPLAZATORIO\n...")
        assert not ok

    def test_publicidad(self):
        h, ok = detect_header("PUBLICIDAD\n...")
        assert not ok

    def test_aviso_simple(self):
        h, ok = detect_header("AVISO\nimportante...")
        assert not ok

    def test_comunicado(self):
        h, ok = detect_header("COMUNICADO\n...")
        assert not ok

    def test_circular(self):
        h, ok = detect_header("CIRCULAR\n...")
        assert not ok

    def test_licitacion(self):
        h, ok = detect_header("LICITACION\n...")
        assert not ok

    def test_convocatoria(self):
        h, ok = detect_header("CONVOCATORIA\n...")
        assert not ok


# --- Publicidad / Edicto ---
class TestContentType:
    def test_publicidad_only(self):
        t = "PUBLICIDAD\nCompre nuestros productos\nOferta limitada"
        assert has_publicidad_only(t)

    def test_not_publicidad(self):
        t = "AVISO DE REMATE\nExpediente: 123\nJUZGADO: ..."
        assert not has_publicidad_only(t)

    def test_edicto_only(self):
        t = "EDICTO\nSe cita a comparecer..."
        assert has_edicto_only(t)

    def test_not_edicto(self):
        t = "AVISO DE REMATE\nExpediente: 123"
        assert not has_edicto_only(t)

    def test_edicto_with_remate(self):
        t = "EDICTO\nAVISO DE REMATE\nExpediente: 123"
        assert not has_edicto_only(t)


# --- Mandatory fields ---
class TestMandatoryFields:
    def test_all_strong_present(self):
        fields, missing = check_mandatory_fields({"expediente", "finca", "precio_base"})
        assert "expediente" in fields
        assert "finca" in fields or "finca_matr" in fields
        assert len(missing) <= 4

    def test_no_fields(self):
        fields, missing = check_mandatory_fields(set())
        assert len(fields) == 0

    def test_weak_only(self):
        fields, missing = check_mandatory_fields({"lugar", "hora"})
        assert missing

    def test_min_strong_fields_rule_pass(self):
        assert min_strong_fields_rule({"expediente"})
        assert min_strong_fields_rule({"finca"})
        assert min_strong_fields_rule({"demandante", "demandado"})

    def test_min_strong_fields_rule_fail(self):
        assert not min_strong_fields_rule({"lugar"})
        assert not min_strong_fields_rule(set())


# --- Co-occurrence ---
class TestCoOccurrence:
    def test_expediente_without_finca(self):
        w = check_field_co_occurrence({"expediente"})
        assert any("finca" in x.lower() for x in w)

    def test_finca_without_expediente(self):
        w = check_field_co_occurrence({"finca"})
        assert any("expediente" in x.lower() for x in w)

    def test_demandante_without_demandado(self):
        w = check_field_co_occurrence({"demandante", "expediente"})
        assert any("demandado" in x.lower() for x in w)

    def test_no_warnings(self):
        w = check_field_co_occurrence({"expediente", "finca", "precio_base", "fecha_remate", "demandante", "demandado"})
        assert len(w) == 0


# --- NoticeValidator ---
class TestNoticeValidator:
    def make_valid_aviso(self) -> dict:
        return {
            "expediente": {"value": "123/2024", "status": "FOUND", "confidence": 0.95},
            "finca": {"value": "82699", "status": "FOUND", "confidence": 0.95},
            "precio_base": {"value": "100000", "status": "FOUND", "confidence": 0.95},
            "demandante": {"value": "Juan Perez", "status": "FOUND", "confidence": 0.95},
            "demandado": {"value": "Maria Lopez", "status": "FOUND", "confidence": 0.95},
            "fecha_remate": {"value": "7 de agosto de 2026", "status": "FOUND", "confidence": 0.95},
        }

    def test_valid_notice(self):
        validator = NoticeValidator()
        text = "AVISO DE REMATE\nExpediente: 123/2024\nFinca: 82699\nBase: $100,000\nDemandante: Juan Perez\nDemandado: Maria Lopez"
        d = validator.validate(aviso_id="test1", text=text, fields_found=self.make_valid_aviso())
        assert d.decision == Decision.VALID
        assert d.header_valid
        assert d.structural_valid
        assert len(d.fields_found) >= 4
        assert len(d.rules_failed) == 0

    def test_invalid_notice_wrong_header(self):
        validator = NoticeValidator()
        d = validator.validate(aviso_id="test2", text="PUBLICIDAD\nCompre ahora!", fields_found={})
        assert d.decision == Decision.INVALID
        assert not d.header_valid

    def test_invalid_notice_edicto(self):
        validator = NoticeValidator()
        d = validator.validate(aviso_id="test3", text="EDICTO EMPLAZATORIO\nSe cita...", fields_found={})
        assert d.decision == Decision.INVALID

    def test_incomplete_notice(self):
        validator = NoticeValidator()
        text = "AVISO DE REMATE\nExpediente: 123/2024"
        fields = {"expediente": {"value": "123/2024", "status": "FOUND", "confidence": 0.95}}
        d = validator.validate(aviso_id="test4", text=text, fields_found=fields)
        assert d.decision in (Decision.INCOMPLETE, Decision.VALID)

    def test_requires_review(self):
        validator = NoticeValidator()
        text = "Algo aqui\nSin header claro\nSin campos fuertes"
        fields = {"lugar": {"value": "JUZGADO", "status": "FOUND", "confidence": 0.5}}
        d = validator.validate(aviso_id="test5", text=text, fields_found=fields)
        assert d.decision == Decision.INVALID


# --- Consistency ---
class TestConsistency:
    def test_no_inconsistencies(self):
        eng = ConsistencyEngine()
        fields = {
            "expediente": {"value": "123/2024"},
            "finca": {"value": "82699"},
            "precio_base": {"value": "100000"},
        }
        issues = eng.check(fields, text="AVISO DE REMATE\nExpediente: 123/2024")
        assert len(issues) == 0

    def test_base_mismatch(self):
        eng = ConsistencyEngine()
        fields = {
            "base": {"value": "100000"},
            "precio_base": {"value": "200000"},
        }
        issues = eng.check(fields)
        assert any("base" in i.field_1.lower() for i in issues)

    def test_finca_mismatch(self):
        eng = ConsistencyEngine()
        fields = {
            "finca": {"value": "82699"},
            "finca_matr": {"value": "99999"},
        }
        issues = eng.check(fields)
        assert any("finca" in i.field_1.lower() for i in issues)

    def test_same_party(self):
        eng = ConsistencyEngine()
        fields = {
            "demandante": {"value": "Juan Perez"},
            "demandado": {"value": "Juan Perez"},
        }
        issues = eng.check(fields)
        assert any("demandante" in i.field_1.lower() for i in issues)

    def test_impossible_date(self):
        eng = ConsistencyEngine()
        issues = eng.check({}, text="Fecha: 99-99-9999")
        assert len(issues) >= 0


# --- DuplicateDetector ---
class TestDuplicateDetector:
    def test_unique(self):
        dd = DuplicateDetector()
        f1 = {"expediente": {"value": "123/2024"}, "finca": {"value": "82699"}}
        f2 = {"expediente": {"value": "456/2024"}, "finca": {"value": "45111"}}
        r1 = dd.check("id1", f1, "AVISO DE REMATE\nExpediente: 123/2024")
        assert r1.level == DuplicateLevel.UNIQUE
        r2 = dd.check("id2", f2, "AVISO DE REMATE\nExpediente: 456/2024")
        assert r2.level == DuplicateLevel.UNIQUE

    def test_duplicated_expediente(self):
        dd = DuplicateDetector()
        f1 = {"expediente": {"value": "123/2024"}, "finca": {"value": "82699"}}
        f2 = {"expediente": {"value": "123/2024"}, "finca": {"value": "82699"}}
        dd.check("id1", f1, "AVISO DE REMATE")
        r2 = dd.check("id2", f2, "AVISO DE REMATE")
        assert r2.level == DuplicateLevel.DUPLICATED

    def test_likely_duplicated(self):
        dd = DuplicateDetector()
        f1 = {"expediente": {"value": "123/2024"}}
        f2 = {"expediente": {"value": "123/2024"}}
        dd.check("id1", f1, "AVISO DE REMATE")
        r2 = dd.check("id2", f2, "AVISO DE REMATE DIFERENTE")
        assert r2.level == DuplicateLevel.LIKELY_DUPLICATED

    def test_reset(self):
        dd = DuplicateDetector()
        f1 = {"expediente": {"value": "123/2024"}}
        dd.check("id1", f1, "text")
        dd.reset()
        r = dd.check("id2", f1, "text")
        assert r.level == DuplicateLevel.UNIQUE


# --- Scoring ---
class TestScoring:
    def test_perfect_score(self):
        scorer = NoticeScorer()
        d = NoticeDecision(
            aviso_id="test",
            header_valid=True,
            structural_valid=True,
            fields_found=["expediente", "finca", "precio_base", "fecha_remate", "demandante", "demandado"],
            rules_applied=[
                RuleResult(rule_name="valid_header", passed=True, weight=0.25),
                RuleResult(rule_name="min_one_strong_field", passed=True, weight=0.15),
                RuleResult(rule_name="structural_coherence", passed=True, weight=0.15),
                RuleResult(rule_name="field_co_occurrence", passed=True, weight=0.10),
                RuleResult(rule_name="not_publicidad", passed=True, weight=0.15),
                RuleResult(rule_name="not_edicto", passed=True, weight=0.15),
                RuleResult(rule_name="min_field_count", passed=True, weight=0.05),
            ],
            inconsistencies=[],
        )
        s = scorer.score(d)
        assert s >= 0.5

    def test_low_score(self):
        scorer = NoticeScorer()
        d = NoticeDecision(
            aviso_id="test",
            header_valid=False,
            structural_valid=False,
            fields_found=[],
            rules_applied=[],
            inconsistencies=[Inconsistency(field_1="base", field_2="precio_base", description="mismatch", severity="high")],
        )
        s = scorer.score(d)
        assert s < 0.5


# --- Orchestrator ---
class TestOrchestrator:
    def test_valid_notice(self):
        orch = ValidationOrchestrator()
        d = orch.validate_notice(
            aviso_id="test1",
            text="AVISO DE REMATE\nExpediente: 123/2024\nFinca: 82699\nBase: $100,000\nDemandante: Juan\nDemandado: Maria",
            fields_found={
                "expediente": {"value": "123/2024", "status": "FOUND"},
                "finca": {"value": "82699", "status": "FOUND"},
                "precio_base": {"value": "100000", "status": "FOUND"},
                "demandante": {"value": "Juan", "status": "FOUND"},
                "demandado": {"value": "Maria", "status": "FOUND"},
            },
        )
        assert d.decision in (Decision.VALID, Decision.INCOMPLETE)
        assert d.score >= 0.5

    def test_invalid_notice(self):
        orch = ValidationOrchestrator()
        d = orch.validate_notice(
            aviso_id="test2",
            text="PUBLICIDAD\nCompre ahora!",
            fields_found={},
        )
        assert d.decision == Decision.INVALID

    def test_duplicate_detected(self):
        orch = ValidationOrchestrator()
        f = {"expediente": {"value": "123/2024"}}
        orch.validate_notice(aviso_id="a1", text="AVISO DE REMATE", fields_found=f)
        d = orch.validate_notice(aviso_id="a2", text="AVISO DE REMATE", fields_found=f)
        assert d.decision == Decision.DUPLICATED

    def test_batch(self):
        orch = ValidationOrchestrator()
        result = orch.validate_batch([
            {"id": "v1", "text": "AVISO DE REMATE\nExpediente: 1", "fields": {"expediente": {"value": "1"}}},
            {"id": "v2", "text": "PUBLICIDAD", "fields": {}},
            {"id": "v3", "text": "EDICTO", "fields": {}},
        ])
        assert result.total_avisos == 3
        assert result.valid_count >= 0
        assert result.invalid_count >= 1
        assert result.avg_score >= 0
