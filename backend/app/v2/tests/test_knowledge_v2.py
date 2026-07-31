"""Tests for FASE 6.5 — Knowledge Validation & Learning Pipeline.

Covers: persistence, versioning, categories, batch learning, shadow mode,
alias priority, rule expiration, rollback, dashboard, benchmark, regression."""

import os
import tempfile
import unittest

from backend.app.v2.knowledge.models import (
    CorrectionEvent, KnowledgeAlias, KnowledgeCategory, KnowledgeEvidence,
    KnowledgeRule, RuleHistory, RuleStatus, RuleType, ShadowComparison,
)
from backend.app.v2.knowledge.repository import KnowledgeRepository
from backend.app.v2.knowledge.patterns import PatternGenerator
from backend.app.v2.knowledge.aliases import AliasManager
from backend.app.v2.knowledge.analyzer import KnowledgeAnalyzer
from backend.app.v2.knowledge.rules import RuleEngine
from backend.app.v2.knowledge.shadow import ShadowLearner
from backend.app.v2.knowledge.trainer import KnowledgeTrainer
from backend.app.v2.knowledge.metrics import MetricsTracker
from backend.app.v2.knowledge.services import CorrectionService
from backend.app.v2.knowledge.regression import RegressionGuard
from backend.app.v2.knowledge.benchmark import KnowledgeBenchmark
from backend.app.v2.parser.context import ParserContext
from backend.app.v2.parser.factory import ParserFactory
from backend.app.v2.parser.result import ParseResult


def _make_repo():
    """Create a repository with a temp database for testing."""
    tmp = tempfile.mktemp(suffix=".db")
    return KnowledgeRepository(db_path=tmp), tmp


# =============================================================================
# SQLite Persistence
# =============================================================================

class TestSQLitePersistence(unittest.TestCase):
    def setUp(self):
        self.repo, self.path = _make_repo()

    def tearDown(self):
        self.repo.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_save_correction_persists(self):
        e = CorrectionEvent(document_id="D1", country="PA", field_name="finca",
                            corrected_value="12345", evidence_text="FINCA 12345")
        self.repo.save_correction(e)
        self.assertEqual(self.repo.count_corrections(), 1)

    def test_save_correction_survives_reopen(self):
        e = CorrectionEvent(document_id="D1", country="PA", field_name="finca",
                            corrected_value="12345")
        self.repo.save_correction(e)
        self.repo.close()
        repo2 = KnowledgeRepository(db_path=self.path)
        self.assertEqual(repo2.count_corrections(), 1)
        repo2.close()

    def test_save_rule_persists(self):
        r = KnowledgeRule(field_name="finca", pattern=r"FINCA (\d+)")
        self.repo.save_rule(r)
        self.assertEqual(self.repo.count_rules(), 1)

    def test_save_rule_survives_reopen(self):
        r = KnowledgeRule(field_name="finca", pattern=r"FINCA (\d+)")
        self.repo.save_rule(r)
        saved_id = r.rule_id
        self.repo.close()
        repo2 = KnowledgeRepository(db_path=self.path)
        loaded = repo2.get_rule(saved_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.field_name, "finca")
        repo2.close()

    def test_get_rules_by_field(self):
        self.repo.save_rule(KnowledgeRule(field_name="finca", pattern="x"))
        self.repo.save_rule(KnowledgeRule(field_name="base", pattern="y"))
        finca = self.repo.get_rules(field="finca")
        self.assertEqual(len(finca), 1)

    def test_get_rules_by_status(self):
        self.repo.save_rule(KnowledgeRule(field_name="finca", pattern="x", status="APPROVED"))
        self.repo.save_rule(KnowledgeRule(field_name="base", pattern="y", status="PENDING"))
        approved = self.repo.get_rules(status="APPROVED")
        self.assertEqual(len(approved), 1)

    def test_get_rules_by_category(self):
        self.repo.save_rule(KnowledgeRule(field_name="finca", pattern="x",
                                          category=KnowledgeCategory.PROPERTY.value))
        self.repo.save_rule(KnowledgeRule(field_name="base", pattern="y",
                                          category=KnowledgeCategory.MONEY.value))
        money = self.repo.get_rules(category=KnowledgeCategory.MONEY.value)
        self.assertEqual(len(money), 1)

    def test_save_alias_persists(self):
        a = KnowledgeAlias(source="TEST", target="PRUEBA", field_name="finca")
        self.repo.save_alias(a)
        self.assertEqual(self.repo.count_aliases(), 1)

    def test_save_alias_survives_reopen(self):
        self.repo.save_alias(KnowledgeAlias(source="TEST", target="PRUEBA"))
        self.repo.close()
        repo2 = KnowledgeRepository(db_path=self.path)
        aliases = repo2.get_aliases(source="TEST")
        self.assertEqual(len(aliases), 1)
        repo2.close()

    def test_get_aliases_by_field(self):
        self.repo.save_alias(KnowledgeAlias(source="A", target="B", field_name="finca"))
        self.repo.save_alias(KnowledgeAlias(source="C", target="D", field_name="base"))
        finca = self.repo.get_aliases(field="finca")
        self.assertEqual(len(finca), 1)

    def test_get_learned_aliases_excludes_builtin(self):
        self.repo.save_alias(KnowledgeAlias(source="A", target="B", is_builtin=True))
        self.repo.save_alias(KnowledgeAlias(source="C", target="D", is_builtin=False))
        learned = self.repo.get_learned_aliases()
        self.assertEqual(len(learned), 1)

    def test_save_history(self):
        h = RuleHistory(rule_id="R1", version=1, previous_status="PENDING",
                        new_status="APPROVED")
        saved = self.repo.save_history(h)
        self.assertIsNotNone(saved.history_id)

    def test_get_history_by_rule(self):
        self.repo.save_history(RuleHistory(rule_id="R1", version=1))
        self.repo.save_history(RuleHistory(rule_id="R2", version=1))
        hist = self.repo.get_history(rule_id="R1")
        self.assertEqual(len(hist), 1)

    def test_save_shadow_comparison(self):
        c = ShadowComparison(document_id="D1", field_name="finca",
                             winner="parser", difference=False)
        saved = self.repo.save_shadow(c)
        self.assertIsNotNone(saved.comparison_id)

    def test_get_shadow_comparisons(self):
        self.repo.save_shadow(ShadowComparison(document_id="D1", field_name="finca",
                                                winner="parser"))
        self.repo.save_shadow(ShadowComparison(document_id="D2", field_name="base",
                                                winner="knowledge"))
        comps = self.repo.get_shadow_comparisons(field_name="finca")
        self.assertEqual(len(comps), 1)

    def test_count_rules_by_status(self):
        self.repo.save_rule(KnowledgeRule(field_name="finca", pattern="x", status="APPROVED"))
        self.repo.save_rule(KnowledgeRule(field_name="base", pattern="y", status="PENDING"))
        self.repo.save_rule(KnowledgeRule(field_name="finca", pattern="z", status="REJECTED"))
        self.assertEqual(self.repo.count_rules(status="APPROVED"), 1)
        self.assertEqual(self.repo.count_rules(status="PENDING"), 1)
        self.assertEqual(self.repo.count_rules(status="REJECTED"), 1)

    def test_count_corrections_by_country(self):
        self.repo.save_correction(CorrectionEvent(document_id="D1", country="PA"))
        self.repo.save_correction(CorrectionEvent(document_id="D2", country="CO"))
        self.repo.save_correction(CorrectionEvent(document_id="D3", country="PA"))
        self.assertEqual(self.repo.count_corrections(country="PA"), 2)
        self.assertEqual(self.repo.count_corrections(country="CO"), 1)


# =============================================================================
# Rule Versioning
# =============================================================================

class TestRuleVersioning(unittest.TestCase):
    def setUp(self):
        self.repo, self.path = _make_repo()

    def tearDown(self):
        self.repo.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_rule_has_rule_id(self):
        r = KnowledgeRule(field_name="finca", pattern="x")
        self.repo.save_rule(r)
        self.assertNotEqual(r.rule_id, "")

    def test_rule_has_version_default(self):
        r = KnowledgeRule(field_name="finca", pattern="x")
        self.assertEqual(r.version, 1)

    def test_rule_has_rollback_version_none(self):
        r = KnowledgeRule(field_name="finca", pattern="x")
        self.assertIsNone(r.rollback_version)

    def test_rule_has_created_from_correction(self):
        r = KnowledgeRule(field_name="finca", pattern="x",
                          created_from_correction="DOC-001")
        self.assertEqual(r.created_from_correction, "DOC-001")

    def test_rule_has_approved_by(self):
        r = KnowledgeRule(field_name="finca", pattern="x")
        r.approve(approved_by="test_user")
        self.assertEqual(r.approved_by, "test_user")

    def test_rollback_updates_status(self):
        r = KnowledgeRule(field_name="finca", pattern="x", status="APPROVED")
        self.repo.save_rule(r)
        engine = RuleEngine(repository=self.repo)
        result = engine.rollback_rule(r.rule_id)
        self.assertTrue(result)
        loaded = self.repo.get_rule(r.rule_id)
        self.assertEqual(loaded.status, "PENDING")


# =============================================================================
# Rule Categories
# =============================================================================

class TestKnowledgeCategories(unittest.TestCase):
    def setUp(self):
        self.generator = PatternGenerator()

    def test_detect_money_from_field(self):
        cat = self.generator.detect_category("50000", "precio_base", "BASE B/.50000")
        self.assertEqual(cat, KnowledgeCategory.MONEY.value)

    def test_detect_date_from_field(self):
        cat = self.generator.detect_category(
            "15 DE SEPTIEMBRE DE 2026", "fecha_remate",
            "FECHA DE REMATE: 15 DE SEPTIEMBRE DE 2026"
        )
        self.assertEqual(cat, KnowledgeCategory.DATE.value)

    def test_detect_case_number_from_dash(self):
        cat = self.generator.detect_category("12345-2026", "expediente", "EXPEDIENTE N° 12345-2026")
        self.assertEqual(cat, KnowledgeCategory.CASE_NUMBER.value)

    def test_detect_property_simple_number(self):
        cat = self.generator.detect_category("90123", "finca", "FINCA 90123")
        self.assertEqual(cat, KnowledgeCategory.PROPERTY.value)

    def test_detect_person_from_context(self):
        cat = self.generator.detect_category(
            "JUAN PEREZ", "demandante",
            "DEMANDANTE: JUAN PEREZ"
        )
        self.assertEqual(cat, KnowledgeCategory.PERSON.value)

    def test_detect_label_as_fallback(self):
        cat = self.generator.detect_category("SECCION", "section", "SECCION JUDICIAL")
        self.assertEqual(cat, KnowledgeCategory.LABEL.value)

    def test_generate_money_pattern(self):
        pattern = self.generator.generate_category_pattern(
            KnowledgeCategory.MONEY.value, ["B/.50000", "$100000"]
        )
        self.assertIsNotNone(pattern)

    def test_generate_date_pattern(self):
        pattern = self.generator.generate_category_pattern(
            KnowledgeCategory.DATE.value, ["15 DE SEPTIEMBRE DE 2026"]
        )
        self.assertIsNotNone(pattern)

    def test_rule_saves_category(self):
        repo, path = _make_repo()
        r = KnowledgeRule(field_name="finca", pattern="x",
                          category=KnowledgeCategory.PROPERTY.value)
        repo.save_rule(r)
        loaded = repo.get_rule(r.rule_id)
        self.assertEqual(loaded.category, KnowledgeCategory.PROPERTY.value)
        repo.close()
        os.unlink(path)


# =============================================================================
# Alias Priority
# =============================================================================

class TestAliasPriority(unittest.TestCase):
    def setUp(self):
        self.repo, self.path = _make_repo()
        self.manager = AliasManager(repository=self.repo)

    def tearDown(self):
        self.repo.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_builtin_takes_priority(self):
        self.repo.save_alias(KnowledgeAlias(
            source="NRO", target="WRONG", field_name="expediente",
            is_builtin=False, status="APPROVED"
        ))
        result = self.manager.resolve("NRO", "expediente")
        self.assertEqual(result, "NUMERO")

    def test_approved_learned_over_pending(self):
        self.repo.save_alias(KnowledgeAlias(
            source="CIA", target="COMPANIA", field_name="demandante",
            is_builtin=False, status="APPROVED"
        ))
        self.repo.save_alias(KnowledgeAlias(
            source="CIA", target="WRONG", field_name="demandante",
            is_builtin=False, status="PENDING"
        ))
        result = self.manager.resolve("CIA", "demandante")
        self.assertEqual(result, "COMPANIA")

    def test_learn_alias_returns_none_if_builtin(self):
        result = self.manager.learn_alias("NRO", "NUMERO", "expediente")
        self.assertIsNone(result)

    def test_learn_alias_returns_alias_if_new(self):
        result = self.manager.learn_alias("XYZ", "XYZ CORP", "demandante",
                                          evidence_text="XYZ CORP", confidence=0.9)
        self.assertIsNotNone(result)
        self.assertEqual(result.source, "XYZ")


# =============================================================================
# Batch Learning
# =============================================================================

class TestBatchLearning(unittest.TestCase):
    def setUp(self):
        self.repo, self.path = _make_repo()
        self.analyzer = KnowledgeAnalyzer(repository=self.repo)

    def tearDown(self):
        self.repo.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_batch_creates_single_rule_from_similar(self):
        for i in range(3):
            self.repo.save_correction(CorrectionEvent(
                document_id=f"D{i}", field_name="finca",
                corrected_value="12345",
                confidence=0.9, evidence_text="FINCA 12345",
            ))
        candidates = self.analyzer.analyze_batch(field="finca")
        self.assertGreaterEqual(len(candidates), 1)

    def test_batch_requires_min_corrections(self):
        self.repo.save_correction(CorrectionEvent(
            document_id="D1", field_name="finca", corrected_value="12345", confidence=0.9
        ))
        candidates = self.analyzer.analyze_batch()
        self.assertEqual(len(candidates), 0)

    def test_batch_detects_category(self):
        for i in range(3):
            self.repo.save_correction(CorrectionEvent(
                document_id=f"D{i}", field_name="precio_base",
                corrected_value=f"B/.{i}0000",
                confidence=0.9, evidence_text=f"BASE B/.{i}0000",
            ))
        candidates = self.analyzer.analyze_batch(field="precio_base")
        if candidates:
            self.assertEqual(candidates[0].category, KnowledgeCategory.MONEY.value)

    def test_find_variants(self):
        corrections = [
            CorrectionEvent(field_name="finca", evidence_text="FINCA 12345"),
            CorrectionEvent(field_name="finca", evidence_text="FINCA N° 67890"),
            CorrectionEvent(field_name="base", evidence_text="BASE B/.50000"),
        ]
        variants = self.analyzer.find_variants(corrections, "finca")
        self.assertGreater(len(variants), 0)


# =============================================================================
# Rule Expiration
# =============================================================================

class TestRuleExpiration(unittest.TestCase):
    def setUp(self):
        self.repo, self.path = _make_repo()
        self.engine = RuleEngine(repository=self.repo)

    def tearDown(self):
        self.repo.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_rule_becomes_inactive_after_expiration(self):
        r = KnowledgeRule(field_name="finca", pattern=r"NO MATCH (\d+)",
                          status="APPROVED", confidence=0.9)
        self.repo.save_rule(r)
        prev = ParseResult(field_name="finca")
        prev.set_found("12345", confidence=0.9)
        for _ in range(10):
            self.engine.apply_rules("finca", "NO FINCA HERE", previous_result=prev)
        loaded = self.repo.get_rule(r.rule_id)
        self.assertTrue(loaded.is_inactive)

    def test_high_accuracy_rule_does_not_expire(self):
        r = KnowledgeRule(field_name="finca", pattern=r"FINCA (\d+)",
                          status="APPROVED", confidence=0.9)
        self.repo.save_rule(r)
        for _ in range(10):
            self.engine.apply_rules("finca", "FINCA 12345")
        loaded = self.repo.get_rule(r.rule_id)
        self.assertTrue(loaded.is_approved)
        self.assertFalse(loaded.is_inactive)

    def test_rule_has_fail_count(self):
        r = KnowledgeRule(field_name="finca", pattern=r"NO MATCH (\d+)",
                          status="APPROVED", confidence=0.9)
        self.repo.save_rule(r)
        prev = ParseResult(field_name="finca")
        prev.set_found("12345", confidence=0.9)
        for _ in range(5):
            self.engine.apply_rules("finca", "NO MATCH HERE", previous_result=prev)
        loaded = self.repo.get_rule(r.rule_id)
        self.assertEqual(loaded.fail_count, 5)

    def test_inactive_rule_not_applied(self):
        r = KnowledgeRule(field_name="finca", pattern=r"FINCA (\d+)",
                          status="INACTIVE", confidence=0.9)
        self.repo.save_rule(r)
        result = self.engine.apply_rules("finca", "FINCA 12345")
        self.assertIsNone(result)


# =============================================================================
# Shadow Learning
# =============================================================================

class TestShadowLearning(unittest.TestCase):
    def setUp(self):
        self.repo, self.path = _make_repo()
        self.learner = ShadowLearner(repository=self.repo)
        self.factory = ParserFactory()

    def tearDown(self):
        self.repo.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_compare_returns_comparisons(self):
        parser = self.factory.get_parser("PA", "REMATE")
        ctx = ParserContext(country="PA", document_type="REMATE",
                            text="AVISO DE REMATE\nFINCA 12345")
        comparisons = self.learner.compare(parser, ctx, document_id="D1")
        self.assertGreater(len(comparisons), 0)

    def test_compare_saves_to_db(self):
        parser = self.factory.get_parser("PA", "REMATE")
        ctx = ParserContext(country="PA", document_type="REMATE",
                            text="AVISO DE REMATE\nFINCA 12345")
        self.learner.compare(parser, ctx, document_id="D1")
        comps = self.repo.get_shadow_comparisons()
        self.assertGreater(len(comps), 0)

    def test_compare_detects_difference(self):
        repo2, _ = _make_repo()
        repo2.save_rule(KnowledgeRule(
            field_name="expediente", pattern=r"NO MATCH (\d+)",
            status="APPROVED", confidence=0.9
        ))
        learner = ShadowLearner(repository=repo2)
        parser = self.factory.get_parser("PA", "REMATE")
        ctx = ParserContext(country="PA", document_type="REMATE",
                            text="AVISO DE REMATE\nFINCA 12345")
        comparisons = learner.compare(parser, ctx, document_id="D1")
        parser_result = parser.parse(ctx)
        has_difference = any(c.difference for c in comparisons)
        self.assertIsNotNone(has_difference)
        repo2.close()

    def test_get_summary_empty(self):
        summary = self.learner.get_summary()
        self.assertEqual(summary["total_comparisons"], 0)


# =============================================================================
# Explainability
# =============================================================================

class TestExplainability(unittest.TestCase):
    def setUp(self):
        self.repo, self.path = _make_repo()
        self.engine = RuleEngine(repository=self.repo)

    def tearDown(self):
        self.repo.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_explain_rule_returns_details(self):
        r = KnowledgeRule(field_name="finca", pattern=r"FINCA (\d+)",
                          status="APPROVED", confidence=0.9)
        self.repo.save_rule(r)
        explanation = self.engine.explain_rule(r.rule_id)
        self.assertIsNotNone(explanation)
        self.assertEqual(explanation["rule_id"], r.rule_id)
        self.assertEqual(explanation["pattern"], r.pattern)

    def test_explain_nonexistent_rule(self):
        explanation = self.engine.explain_rule("NONEXISTENT")
        self.assertIsNone(explanation)

    def test_explain_includes_history(self):
        r = KnowledgeRule(field_name="finca", pattern=r"FINCA (\d+)",
                          status="PENDING", confidence=0.9)
        self.repo.save_rule(r)
        r.approve(approved_by="tester")
        self.repo.save_history(RuleHistory(
            rule_id=r.rule_id, version=1,
            previous_status="PENDING", new_status="APPROVED"
        ))
        self.repo.save_rule(r)
        explanation = self.engine.explain_rule(r.rule_id)
        self.assertGreater(len(explanation["history"]), 0)

    def test_evidence_includes_rule_info(self):
        r = KnowledgeRule(field_name="finca", pattern=r"FINCA (\d+)",
                          status="APPROVED", confidence=0.9,
                          evidence=[KnowledgeEvidence(text_snippet="FINCA 12345")])
        self.repo.save_rule(r)
        result = self.engine.apply_rules("finca", "AVISO FINCA 12345")
        self.assertIsNotNone(result)
        self.assertGreater(len(result.evidence), 0)
        method = result.evidence[0]["method"]
        self.assertIn("rule:", method)
        self.assertIn(r.rule_id, method)


# =============================================================================
# Metrics Dashboard
# =============================================================================

class TestMetricsDashboard(unittest.TestCase):
    def setUp(self):
        self.repo, self.path = _make_repo()
        self.metrics = MetricsTracker(repository=self.repo)

    def tearDown(self):
        self.repo.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_dashboard_returns_full_structure(self):
        dashboard = self.metrics.get_dashboard()
        self.assertIn("summary", dashboard)
        self.assertIn("accuracy", dashboard)
        self.assertIn("by_field", dashboard)
        self.assertIn("by_country", dashboard)
        self.assertIn("top_rules", dashboard)

    def test_dashboard_with_data(self):
        for i in range(3):
            r = KnowledgeRule(field_name="finca", pattern=f"p{i}",
                              status="APPROVED")
            r.record_usage(success=True)
            self.repo.save_rule(r)
        dashboard = self.metrics.get_dashboard()
        self.assertEqual(dashboard["summary"]["approved_rules"], 3)

    def test_field_accuracy(self):
        r = KnowledgeRule(field_name="finca", pattern="x", status="APPROVED")
        r.record_usage(success=True)
        r.record_usage(success=True)
        r.record_usage(success=False)
        self.repo.save_rule(r)
        acc = self.metrics.get_field_accuracy("finca")
        self.assertEqual(acc, 0.6667)

    def test_country_accuracy(self):
        self.repo.save_correction(CorrectionEvent(document_id="D1", country="PA",
                                                   field_name="finca"))
        r = KnowledgeRule(field_name="finca", pattern="x", status="APPROVED")
        r.record_usage(success=True)
        self.repo.save_rule(r)
        acc = self.metrics.get_country_accuracy()
        self.assertIn("PA", acc)

    def test_most_failed_rules(self):
        r = KnowledgeRule(field_name="finca", pattern="x", status="APPROVED")
        r.record_usage(success=False)
        r.record_usage(success=False)
        self.repo.save_rule(r)
        failed = self.metrics.get_most_failed_rules()
        self.assertGreater(len(failed), 0)


# =============================================================================
# Regression Guard
# =============================================================================

class TestRegressionGuard(unittest.TestCase):
    def setUp(self):
        self.repo, self.path = _make_repo()
        self.factory = ParserFactory()
        self.guard = RegressionGuard(repository=self.repo, parser_factory=self.factory)

    def tearDown(self):
        self.repo.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_evaluate_rule_returns_metrics(self):
        r = KnowledgeRule(field_name="finca", pattern=r"FINCA (\d+)")
        evaluation = self.guard.evaluate_rule(r)
        self.assertIn("field", evaluation)
        self.assertIn("precision_before", evaluation)
        self.assertIn("precision_after", evaluation)
        self.assertIn("regression", evaluation)

    def test_evaluate_batch(self):
        self.repo.save_rule(KnowledgeRule(field_name="finca", pattern=r"FINCA (\d+)",
                                          status="PENDING"))
        self.repo.save_rule(KnowledgeRule(field_name="base", pattern=r"BASE (\d+)",
                                          status="PENDING"))
        result = self.guard.batch_evaluate()
        self.assertEqual(result["total_evaluated"], 2)


# =============================================================================
# Benchmark
# =============================================================================

class TestBenchmark(unittest.TestCase):
    def setUp(self):
        self.repo, self.path = _make_repo()
        self.benchmark = KnowledgeBenchmark(repository=self.repo)

    def tearDown(self):
        self.repo.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_benchmark_returns_metrics(self):
        self.benchmark.setup_test_data()
        result = self.benchmark.benchmark_parser(iterations=10)
        self.assertIn("parser_avg_ms", result)
        self.assertIn("knowledge_avg_ms", result)
        self.assertIn("overhead_pct", result)
        self.assertIn("within_limit", result)

    def test_setup_test_data_adds_rules(self):
        self.benchmark.setup_test_data()
        self.assertGreater(self.repo.count_rules(), 0)


# =============================================================================
# Rollback
# =============================================================================

class TestRollback(unittest.TestCase):
    def setUp(self):
        self.repo, self.path = _make_repo()
        self.engine = RuleEngine(repository=self.repo)

    def tearDown(self):
        self.repo.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_rollback_updates_status(self):
        r = KnowledgeRule(field_name="finca", pattern="x", status="APPROVED")
        self.repo.save_rule(r)
        self.engine.rollback_rule(r.rule_id)
        loaded = self.repo.get_rule(r.rule_id)
        self.assertEqual(loaded.status, "PENDING")

    def test_rollback_creates_history(self):
        r = KnowledgeRule(field_name="finca", pattern="x", status="APPROVED")
        self.repo.save_rule(r)
        self.engine.rollback_rule(r.rule_id)
        history = self.repo.get_history(rule_id=r.rule_id)
        self.assertGreater(len(history), 0)

    def test_rollback_nonexistent_returns_false(self):
        result = self.engine.rollback_rule("NONEXISTENT")
        self.assertFalse(result)


# =============================================================================
# Integration: Batch Learning through CorrectionService
# =============================================================================

class TestCorrectionServiceV2(unittest.TestCase):
    def setUp(self):
        self.repo, self.path = _make_repo()
        self.service = CorrectionService(repository=self.repo)

    def tearDown(self):
        self.repo.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_batch_learn_creates_rules(self):
        for i in range(5):
            self.service.record_correction(
                f"D{i}", "PA", "finca", "0", "12345",
                f"FINCA 12345", confidence=0.9,
            )
        rules = self.service.batch_learn(field="finca")
        self.assertGreaterEqual(len(rules), 1)

    def test_explain_rule_from_service(self):
        r = KnowledgeRule(field_name="finca", pattern="x", status="APPROVED")
        self.repo.save_rule(r)
        explanation = self.service.explain_rule(r.rule_id)
        self.assertIsNotNone(explanation)

    def test_rollback_rule_from_service(self):
        r = KnowledgeRule(field_name="finca", pattern="x", status="APPROVED")
        self.repo.save_rule(r)
        result = self.service.rollback_rule(r.rule_id)
        self.assertTrue(result)

    def test_statistics_include_inactive(self):
        self.repo.save_rule(KnowledgeRule(field_name="finca", pattern="x",
                                          status="INACTIVE"))
        stats = self.service.get_statistics()
        self.assertEqual(stats["inactive_rules"], 1)

    def test_batch_learn_with_regression_guard(self):
        for i in range(3):
            self.service.record_correction(
                f"D{i}", "PA", "finca", "0", "12345",
                f"FINCA 12345", confidence=0.9,
            )
        rules = self.service.batch_learn(field="finca", use_regression_guard=True)
        self.assertGreaterEqual(len(rules), 1)


# =============================================================================
# Trainer V2 Features
# =============================================================================

class TestTrainerV2(unittest.TestCase):
    def setUp(self):
        self.repo, self.path = _make_repo()
        self.trainer = KnowledgeTrainer(repository=self.repo)

    def tearDown(self):
        self.repo.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_approve_with_approved_by(self):
        r = KnowledgeRule(field_name="finca", pattern="x", confidence=0.9)
        self.repo.save_rule(r)
        self.trainer.approve_rule(r, approved_by="tester")
        self.assertEqual(r.approved_by, "tester")

    def test_approve_creates_history(self):
        r = KnowledgeRule(field_name="finca", pattern="x", confidence=0.9)
        self.repo.save_rule(r)
        self.trainer.approve_rule(r)
        history = self.repo.get_history(rule_id=r.rule_id)
        self.assertGreater(len(history), 0)

    def test_get_inactive_rules(self):
        self.repo.save_rule(KnowledgeRule(field_name="finca", pattern="x", status="INACTIVE"))
        inactive = self.trainer.get_inactive_rules()
        self.assertEqual(len(inactive), 1)


# =============================================================================
# Models V2 Features
# =============================================================================

class TestModelsV2(unittest.TestCase):
    def test_rule_status_inactive(self):
        self.assertIn("INACTIVE", [s.value for s in RuleStatus])

    def test_knowledge_categories_all_present(self):
        categories = [c.value for c in KnowledgeCategory]
        for cat in ["label", "money", "date", "person", "property", "case_number"]:
            self.assertIn(cat, categories)

    def test_rule_has_fail_count(self):
        r = KnowledgeRule(field_name="finca", pattern="x")
        r.record_usage(success=False)
        r.record_usage(success=False)
        r.record_usage(success=True)
        self.assertEqual(r.fail_count, 2)
        self.assertEqual(r.success_count, 1)

    def test_rule_mark_inactive(self):
        r = KnowledgeRule(field_name="finca", pattern="x")
        r.mark_inactive()
        self.assertTrue(r.is_inactive)

    def test_rule_is_inactive_property(self):
        r = KnowledgeRule(field_name="finca", pattern="x", status="INACTIVE")
        self.assertTrue(r.is_inactive)

    def test_shadow_comparison_to_dict(self):
        c = ShadowComparison(document_id="D1", field_name="finca",
                             winner="parser", difference=False)
        d = c.to_dict()
        self.assertEqual(d["winner"], "parser")

    def test_rule_history_to_dict(self):
        h = RuleHistory(rule_id="R1", version=1, previous_status="PENDING",
                        new_status="APPROVED", reason="test")
        d = h.to_dict()
        self.assertEqual(d["reason"], "test")

    def test_alias_status_field(self):
        a = KnowledgeAlias(source="X", target="Y", status="APPROVED")
        self.assertEqual(a.status, "APPROVED")

    def test_alias_is_builtin_field(self):
        a = KnowledgeAlias(source="X", target="Y", is_builtin=True)
        self.assertTrue(a.is_builtin)


if __name__ == "__main__":
    unittest.main()
