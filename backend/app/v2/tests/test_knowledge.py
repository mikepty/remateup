import os
import tempfile
import unittest

from backend.app.v2.knowledge.models import (
    CorrectionEvent, KnowledgeRule, KnowledgeAlias, KnowledgeEvidence,
    RuleStatus, RuleType,
)
from backend.app.v2.knowledge.repository import KnowledgeRepository
from backend.app.v2.knowledge.services import CorrectionService
from backend.app.v2.knowledge.analyzer import KnowledgeAnalyzer
from backend.app.v2.knowledge.trainer import KnowledgeTrainer
from backend.app.v2.knowledge.rules import RuleEngine
from backend.app.v2.knowledge.metrics import MetricsTracker
from backend.app.v2.knowledge.patterns import PatternGenerator
from backend.app.v2.knowledge.aliases import AliasManager
from backend.app.v2.knowledge.integration import KnowledgeAwareWrapper
from backend.app.v2.parser.context import ParserContext
from backend.app.v2.parser.result import ParseResult
from backend.app.v2.parser.factory import ParserFactory


def _make_repo():
    tmp = tempfile.mktemp(suffix=".db")
    return KnowledgeRepository(db_path=tmp), tmp


class TestCorrectionEvent(unittest.TestCase):
    def test_create_event(self):
        e = CorrectionEvent(
            document_id="DOC-001", country="PA",
            field_name="finca", previous_value="123",
            corrected_value="456", evidence_text="FINCA 456",
        )
        self.assertEqual(e.document_id, "DOC-001")
        self.assertEqual(e.previous_value, "123")
        self.assertEqual(e.corrected_value, "456")

    def test_to_dict(self):
        e = CorrectionEvent(document_id="D1", field_name="finca")
        d = e.to_dict()
        self.assertIn("field_name", d)
        self.assertEqual(d["field_name"], "finca")


class TestKnowledgeRule(unittest.TestCase):
    def test_default_state(self):
        r = KnowledgeRule(field_name="finca", pattern="FINCA (\\d+)")
        self.assertTrue(r.is_pending)
        self.assertFalse(r.is_approved)

    def test_approve(self):
        r = KnowledgeRule(field_name="finca", pattern="FINCA (\\d+)")
        r.approve()
        self.assertTrue(r.is_approved)
        self.assertEqual(r.status, "APPROVED")

    def test_reject(self):
        r = KnowledgeRule(field_name="finca", pattern="FINCA (\\d+)")
        r.reject()
        self.assertTrue(r.is_rejected)

    def test_record_usage(self):
        r = KnowledgeRule(field_name="finca", pattern="FINCA (\\d+)")
        r.record_usage(success=True)
        r.record_usage(success=True)
        r.record_usage(success=False)
        self.assertEqual(r.usage_count, 3)
        self.assertEqual(r.success_count, 2)
        self.assertEqual(r.accuracy, 0.6667)

    def test_no_usage_accuracy_zero(self):
        r = KnowledgeRule(field_name="finca", pattern="FINCA (\\d+)")
        self.assertEqual(r.accuracy, 0.0)


class TestKnowledgeRepository(unittest.TestCase):
    def setUp(self):
        self.repo, self.path = _make_repo()

    def tearDown(self):
        self.repo.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_save_correction(self):
        e = CorrectionEvent(document_id="D1", field_name="finca")
        self.repo.save_correction(e)
        self.assertEqual(self.repo.count_corrections(), 1)

    def test_get_corrections_by_country(self):
        self.repo.save_correction(CorrectionEvent(document_id="D1", country="PA", field_name="finca"))
        self.repo.save_correction(CorrectionEvent(document_id="D2", country="CO", field_name="finca"))
        pa = self.repo.get_corrections(country="PA")
        self.assertEqual(len(pa), 1)

    def test_save_rule(self):
        r = KnowledgeRule(field_name="finca", pattern="FINCA (\\d+)")
        self.repo.save_rule(r)
        self.assertEqual(self.repo.count_rules(), 1)

    def test_get_approved_rules(self):
        self.repo.save_rule(KnowledgeRule(field_name="finca", pattern="FINCA (\\d+)", status="APPROVED"))
        self.repo.save_rule(KnowledgeRule(field_name="finca", pattern="BASE (\\d+)", status="PENDING"))
        approved = self.repo.get_approved_rules()
        self.assertEqual(len(approved), 1)

    def test_save_alias(self):
        a = KnowledgeAlias(source="NRO", target="NUMERO", field_name="expediente")
        self.repo.save_alias(a)
        self.assertEqual(self.repo.count_aliases(), 1)


class TestPatternGenerator(unittest.TestCase):
    def setUp(self):
        self.generator = PatternGenerator()

    def test_generate_from_two_examples(self):
        examples = ["FINCA 12345", "FINCA 67890"]
        pattern = self.generator.generate_from_examples(examples, "finca")
        self.assertIsNotNone(pattern)

    def test_insufficient_examples(self):
        pattern = self.generator.generate_from_examples(["solo"], "finca")
        self.assertIsNone(pattern)

    def test_generate_for_value_numeric(self):
        pattern = self.generator.generate_for_value("12345", "finca")
        self.assertIsNotNone(pattern)
        self.assertIn("\\d", pattern)

    def test_generate_for_value_short(self):
        pattern = self.generator.generate_for_value("AB", "field")
        self.assertIsNone(pattern)


class TestAliasManager(unittest.TestCase):
    def setUp(self):
        self.repo, self.path = _make_repo()
        self.manager = AliasManager(repository=self.repo)

    def tearDown(self):
        self.repo.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_resolve_builtin(self):
        self.assertEqual(self.manager.resolve("N°", "expediente"), "NUMERO")
        self.assertEqual(self.manager.resolve("B/.", "precio_base"), "BALBOAS")

    def test_resolve_unknown(self):
        self.assertEqual(self.manager.resolve("UNKNOWN_X", "finca"), "UNKNOWN_X")

    def test_learn_alias(self):
        alias = self.manager.learn_alias("CIA", "COMPANIA", "demandante", evidence_text="CIA LTDA")
        self.assertIsNotNone(alias)
        self.assertEqual(alias.source, "CIA")
        self.assertEqual(alias.target, "COMPANIA")

    def test_learn_identical_returns_none(self):
        alias = self.manager.learn_alias("SAME", "SAME", "campo")
        self.assertIsNone(alias)

    def test_normalize_with_aliases(self):
        result = self.manager.normalize("N° 123", "expediente")
        self.assertIn("NUMERO", result)


class TestKnowledgeAnalyzer(unittest.TestCase):
    def setUp(self):
        self.repo, self.path = _make_repo()
        self.analyzer = KnowledgeAnalyzer(repository=self.repo)

    def tearDown(self):
        self.repo.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_analyze_correction_generates_candidate(self):
        event = CorrectionEvent(
            document_id="D1", country="PA", field_name="finca",
            corrected_value="12345", evidence_text="FINCA 12345",
        )
        candidates = self.analyzer.analyze_correction(event)
        self.assertGreater(len(candidates), 0)
        self.assertEqual(candidates[0].field_name, "finca")

    def test_analyze_correction_no_evidence(self):
        event = CorrectionEvent(document_id="D1", field_name="finca")
        candidates = self.analyzer.analyze_correction(event)
        self.assertEqual(len(candidates), 0)

    def test_analyze_batch_requires_min_corrections(self):
        self.repo.save_correction(CorrectionEvent(
            document_id="D1", field_name="finca", corrected_value="12345",
            confidence=0.9, evidence_text="FINCA 12345",
        ))
        candidates = self.analyzer.analyze_batch()
        self.assertEqual(len(candidates), 0)

    def test_analyze_batch_with_enough(self):
        for i in range(3):
            self.repo.save_correction(CorrectionEvent(
                document_id=f"D{i}", field_name="finca",
                corrected_value=f"FINC{i}",
                confidence=0.9, evidence_text=f"FINCA {i}",
            ))
        candidates = self.analyzer.analyze_batch(field="finca")
        self.assertGreaterEqual(len(candidates), 1)


class TestKnowledgeTrainer(unittest.TestCase):
    def setUp(self):
        self.repo, self.path = _make_repo()
        self.trainer = KnowledgeTrainer(repository=self.repo)

    def tearDown(self):
        self.repo.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_approve_rule(self):
        r = KnowledgeRule(field_name="finca", pattern="FINCA (\\d+)", confidence=0.8)
        self.trainer.approve_rule(r)
        self.assertTrue(r.is_approved)

    def test_reject_rule(self):
        r = KnowledgeRule(field_name="finca", pattern="FINCA (\\d+)")
        self.trainer.reject_rule(r)
        self.assertTrue(r.is_rejected)

    def test_auto_approve_high_confidence(self):
        r = KnowledgeRule(field_name="finca", pattern="FINCA (\\d+)",
                          confidence=0.8, evidence=[KnowledgeEvidence(text_snippet="test")])
        result = self.trainer.auto_approve(r)
        self.assertIsNotNone(result)
        self.assertTrue(result.is_approved)

    def test_auto_approve_low_confidence(self):
        r = KnowledgeRule(field_name="finca", pattern="FINCA (\\d+)", confidence=0.3)
        result = self.trainer.auto_approve(r)
        self.assertIsNone(result)

    def test_get_pending_rules(self):
        self.repo.save_rule(KnowledgeRule(field_name="finca", pattern="x"))
        self.repo.save_rule(KnowledgeRule(field_name="base", pattern="y", status="APPROVED"))
        pending = self.trainer.get_pending_rules()
        self.assertEqual(len(pending), 1)


class TestRuleEngine(unittest.TestCase):
    def setUp(self):
        self.repo, self.path = _make_repo()
        self.engine = RuleEngine(repository=self.repo)

    def tearDown(self):
        self.repo.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_apply_approved_rule(self):
        r = KnowledgeRule(field_name="finca", pattern=r"FINCA (\d+)",
                          status="APPROVED", confidence=0.9)
        self.repo.save_rule(r)
        result = self.engine.apply_rules("finca", "AVISO DE REMATE FINCA 12345")
        self.assertIsNotNone(result)
        self.assertTrue(result.is_found)
        self.assertIn("12345", result.value)

    def test_no_approved_rules(self):
        result = self.engine.apply_rules("finca", "text")
        self.assertIsNone(result)

    def test_pending_rule_not_applied(self):
        r = KnowledgeRule(field_name="finca", pattern=r"FINCA (\d+)", status="PENDING")
        self.repo.save_rule(r)
        result = self.engine.apply_rules("finca", "FINCA 12345")
        self.assertIsNone(result)

    def test_rule_usage_tracked(self):
        r = KnowledgeRule(field_name="finca", pattern=r"FINCA (\d+)",
                          status="APPROVED", confidence=0.9)
        self.repo.save_rule(r)
        self.engine.apply_rules("finca", "FINCA 12345")
        saved = self.repo.get_rule_by_field_pattern("finca", r"FINCA (\d+)")
        self.assertEqual(saved.usage_count, 1)
        self.assertEqual(saved.success_count, 1)


class TestCorrectionService(unittest.TestCase):
    def setUp(self):
        self.repo, self.path = _make_repo()
        self.service = CorrectionService(repository=self.repo)

    def tearDown(self):
        self.repo.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_record_correction(self):
        event = self.service.record_correction(
            document_id="D1", country="PA", field_name="finca",
            previous_value="00000", corrected_value="12345",
            evidence_text="LA FINCA N° 12345",
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.field_name, "finca")

    def test_statistics(self):
        self.service.record_correction("D1", "PA", "finca", "0", "12345", "FINCA 12345")
        stats = self.service.get_statistics()
        self.assertEqual(stats["total_corrections"], 1)
        self.assertGreaterEqual(stats["total_rules"], 0)


class TestMetricsTracker(unittest.TestCase):
    def setUp(self):
        self.repo, self.path = _make_repo()
        self.metrics = MetricsTracker(repository=self.repo)

    def tearDown(self):
        self.repo.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_overall_accuracy_no_rules(self):
        self.assertEqual(self.metrics.get_overall_accuracy(), 0.0)

    def test_overall_accuracy_with_usage(self):
        r = KnowledgeRule(field_name="finca", pattern="x", status="APPROVED")
        r.record_usage(success=True)
        r.record_usage(success=True)
        r.record_usage(success=False)
        self.repo.save_rule(r)
        self.assertEqual(self.metrics.get_overall_accuracy(), 0.6667)

    def test_get_summary(self):
        for i in range(3):
            r = KnowledgeRule(field_name="finca", pattern=f"pattern{i}", status="APPROVED")
            r.record_usage(success=True)
            self.repo.save_rule(r)
        summary = self.metrics.get_summary()
        self.assertEqual(summary["total_rules"], 3)
        self.assertEqual(summary["approved_rules"], 3)
        self.assertEqual(summary["total_usage"], 3)


class TestKnowledgeAwareWrapper(unittest.TestCase):
    def setUp(self):
        self.factory = ParserFactory()
        self.repo, self.path = _make_repo()

    def tearDown(self):
        self.repo.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_wrapper_calls_underlying_parser(self):
        parser = self.factory.get_parser("PA", "REMATE")
        wrapper = KnowledgeAwareWrapper(parser, repository=self.repo)
        ctx = ParserContext(country="PA", document_type="REMATE",
                            text="AVISO DE REMATE\nFINCA 12345\nBASE: B/.50000")
        results = wrapper.parse(ctx)
        self.assertIn("finca", results)
        self.assertTrue(results["finca"].is_found)

    def test_wrapper_fallback_with_knowledge(self):
        parser = self.factory.get_parser("PA", "REMATE")
        r = KnowledgeRule(
            field_name="fecha_remate",
            pattern=r"FECHA\s*[:\s]*(\d{1,2}\s+DE\s+[A-Z]+\s+DE\s+\d{4})",
            status="APPROVED", confidence=0.8,
        )
        self.repo.save_rule(r)
        wrapper = KnowledgeAwareWrapper(parser, repository=self.repo)
        ctx = ParserContext(country="PA", document_type="REMATE",
                            text="AVISO DE REMATE\nFECHA: 15 DE SEPTIEMBRE DE 2026\nFINCA 12345")
        results = wrapper.parse(ctx)
        self.assertTrue(results["fecha_remate"].is_found)

    def test_wrapper_preserves_parser_identity(self):
        parser = self.factory.get_parser("PA", "REMATE")
        wrapper = KnowledgeAwareWrapper(parser, repository=self.repo)
        self.assertEqual(wrapper.country, "PA")
        self.assertEqual(wrapper.supported_fields, parser.supported_fields)


if __name__ == "__main__":
    unittest.main()
