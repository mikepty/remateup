"""CorrectionService — high-level API for recording corrections and triggering learning."""

from typing import Any, Optional

from backend.app.v2.knowledge.models import CorrectionEvent, KnowledgeRule
from backend.app.v2.knowledge.repository import KnowledgeRepository
from backend.app.v2.knowledge.analyzer import KnowledgeAnalyzer
from backend.app.v2.knowledge.trainer import KnowledgeTrainer
from backend.app.v2.knowledge.rules import RuleEngine
from backend.app.v2.knowledge.metrics import MetricsTracker
from backend.app.v2.knowledge.shadow import ShadowLearner
from backend.app.v2.knowledge.regression import RegressionGuard


class CorrectionService:
    def __init__(self, repository: Optional[KnowledgeRepository] = None,
                 analyzer: Optional[KnowledgeAnalyzer] = None,
                 trainer: Optional[KnowledgeTrainer] = None,
                 rule_engine: Optional[RuleEngine] = None):
        self._repository = repository or KnowledgeRepository()
        self._analyzer = analyzer or KnowledgeAnalyzer(repository=self._repository)
        self._trainer = trainer or KnowledgeTrainer(repository=self._repository)
        self._rule_engine = rule_engine or RuleEngine(repository=self._repository)

    def record_correction(self, document_id: str, country: str, field_name: str,
                          previous_value: Any, corrected_value: Any,
                          evidence_text: str = "", confidence: float = 0.0) -> CorrectionEvent:
        event = CorrectionEvent(
            document_id=document_id,
            country=country,
            field_name=field_name,
            previous_value=previous_value,
            corrected_value=corrected_value,
            evidence_text=evidence_text,
            confidence=max(confidence, 0.5),
        )
        self._repository.save_correction(event)
        self._analyze_and_train(event)
        return event

    def _analyze_and_train(self, event: CorrectionEvent):
        candidates = self._analyzer.analyze_correction(event)
        for candidate in candidates:
            self._repository.save_rule(candidate)
            self._trainer.auto_approve(candidate)

    def batch_learn(self, country: Optional[str] = None,
                    field: Optional[str] = None,
                    use_regression_guard: bool = False) -> list[KnowledgeRule]:
        candidates = self._analyzer.analyze_batch(country=country, field=field)
        trained: list[KnowledgeRule] = []
        for candidate in candidates:
            self._repository.save_rule(candidate)
            if use_regression_guard:
                guard = RegressionGuard(repository=self._repository)
                success, _ = guard.approve_with_guard(candidate)
                if not success:
                    trained.append(candidate)
                    continue
            approved = self._trainer.auto_approve(candidate)
            trained.append(approved or candidate)
        return trained

    def rollback_rule(self, rule_id: str) -> bool:
        return self._rule_engine.rollback_rule(rule_id)

    def explain_rule(self, rule_id: str) -> Optional[dict]:
        return self._rule_engine.explain_rule(rule_id)

    def get_statistics(self) -> dict:
        corrections = self._repository.count_corrections()
        rules_total = self._repository.count_rules()
        rules_approved = self._repository.count_rules(status="APPROVED")
        rules_pending = self._repository.count_rules(status="PENDING")
        rules_rejected = self._repository.count_rules(status="REJECTED")
        rules_inactive = self._repository.count_rules(status="INACTIVE")
        aliases = self._repository.count_aliases()
        return {
            "total_corrections": corrections,
            "total_rules": rules_total,
            "approved_rules": rules_approved,
            "pending_rules": rules_pending,
            "rejected_rules": rules_rejected,
            "inactive_rules": rules_inactive,
            "total_aliases": aliases,
            "fields_with_rules": len(set(r.field_name for r in self._repository.get_rules())),
        }

    @property
    def repository(self) -> KnowledgeRepository:
        return self._repository

    @property
    def rule_engine(self) -> RuleEngine:
        return self._rule_engine

    @property
    def trainer(self) -> KnowledgeTrainer:
        return self._trainer

    @property
    def analyzer(self) -> KnowledgeAnalyzer:
        return self._analyzer
