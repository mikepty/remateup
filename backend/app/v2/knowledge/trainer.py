"""KnowledgeTrainer — validates, approves/rejects rules, supports versioning and history."""

from typing import Optional

from backend.app.v2.knowledge.models import KnowledgeRule, RuleHistory, RuleStatus
from backend.app.v2.knowledge.repository import KnowledgeRepository
from backend.app.v2.knowledge.metrics import MetricsTracker


class KnowledgeTrainer:
    MIN_CONFIDENCE_TO_APPROVE = 0.7
    MIN_EVIDENCE_TO_APPROVE = 1

    def __init__(self, repository: Optional[KnowledgeRepository] = None,
                 metrics: Optional[MetricsTracker] = None):
        self._repository = repository or KnowledgeRepository()
        self._metrics = metrics or MetricsTracker(repository=repository)

    def approve_rule(self, rule: KnowledgeRule,
                     approved_by: str = "trainer") -> KnowledgeRule:
        accuracy_before = rule.accuracy
        if rule.confidence < self.MIN_CONFIDENCE_TO_APPROVE:
            rule.confidence = self.MIN_CONFIDENCE_TO_APPROVE
        rule.approve(approved_by=approved_by)
        self._repository.save_history(RuleHistory(
            rule_id=rule.rule_id,
            version=rule.version,
            previous_status=RuleStatus.PENDING.value,
            new_status=RuleStatus.APPROVED.value,
            accuracy_before=accuracy_before,
            accuracy_after=rule.accuracy,
            reason=f"Approved by {approved_by}",
        ))
        self._repository.save_rule(rule)
        return rule

    def reject_rule(self, rule: KnowledgeRule) -> KnowledgeRule:
        accuracy_before = rule.accuracy
        rule.reject()
        self._repository.save_history(RuleHistory(
            rule_id=rule.rule_id,
            version=rule.version,
            previous_status=rule.status if rule.status != "REJECTED" else RuleStatus.PENDING.value,
            new_status=RuleStatus.REJECTED.value,
            accuracy_before=accuracy_before,
            accuracy_after=0.0,
            reason="Rejected by trainer",
        ))
        self._repository.save_rule(rule)
        return rule

    def auto_approve(self, rule: KnowledgeRule) -> Optional[KnowledgeRule]:
        if (rule.confidence >= self.MIN_CONFIDENCE_TO_APPROVE
                and len(rule.evidence) >= self.MIN_EVIDENCE_TO_APPROVE):
            return self.approve_rule(rule, approved_by="auto")
        return None

    def get_pending_rules(self, field: Optional[str] = None) -> list[KnowledgeRule]:
        return self._repository.get_rules(field=field, status=RuleStatus.PENDING.value)

    def get_approved_rules(self, field: Optional[str] = None) -> list[KnowledgeRule]:
        return self._repository.get_rules(field=field, status=RuleStatus.APPROVED.value)

    def get_rejected_rules(self, field: Optional[str] = None) -> list[KnowledgeRule]:
        return self._repository.get_rules(field=field, status=RuleStatus.REJECTED.value)

    def get_inactive_rules(self, field: Optional[str] = None) -> list[KnowledgeRule]:
        return self._repository.get_rules(field=field, status=RuleStatus.INACTIVE.value)

    @property
    def metrics(self) -> MetricsTracker:
        return self._metrics
