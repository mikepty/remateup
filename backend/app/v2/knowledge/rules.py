"""RuleEngine — applies approved knowledge rules to improve extraction.
Supports explainability (which rule, version, regex, origin) and rule expiration."""

import re
from datetime import datetime, timezone
from typing import Optional

from backend.app.v2.knowledge.models import KnowledgeRule, RuleHistory, RuleStatus
from backend.app.v2.knowledge.repository import KnowledgeRepository
from backend.app.v2.parser.context import ParserContext
from backend.app.v2.parser.result import ParseResult


class RuleEngine:
    EXPIRATION_THRESHOLD = 0.7
    MIN_EXECUTIONS_FOR_EXPIRATION = 5

    def __init__(self, repository: Optional[KnowledgeRepository] = None):
        self._repository = repository or KnowledgeRepository()

    def apply_rules(self, field: str, text: str,
                    previous_result: Optional[ParseResult] = None) -> Optional[ParseResult]:
        rules = self._get_applicable_rules(field)
        if not rules:
            return None

        for rule in rules:
            if not rule.is_approved:
                continue

            self._check_expiration(rule)

            if rule.is_inactive:
                continue

            m = re.search(rule.pattern, text, re.IGNORECASE | re.MULTILINE)
            if m:
                value = m.group(1) if m.lastindex else m.group(0).strip()
                result = ParseResult(field_name=field)
                result.set_found(value.strip(), confidence=rule.confidence * 0.9)
                for ev in rule.evidence:
                    result.add_evidence(
                        source="knowledge",
                        method=f"rule:{rule.rule_type}:{rule.rule_id}:v{rule.version}",
                        snippet=ev.text_snippet,
                        confidence=ev.confidence,
                    )
                rule.record_usage(success=True)
                self._repository.save_rule(rule)
                return result

        if previous_result and not previous_result.is_not_found:
            for rule in rules:
                if rule.is_approved and not rule.is_inactive:
                    rule.record_usage(success=False)
                    self._check_expiration(rule)
                    self._repository.save_rule(rule)

        return None

    def _get_applicable_rules(self, field: str) -> list[KnowledgeRule]:
        return self._repository.get_approved_rules(field=field)

    def _check_expiration(self, rule: KnowledgeRule):
        """Automatically mark rule INACTIVE if accuracy drops below threshold."""
        if (rule.usage_count >= self.MIN_EXECUTIONS_FOR_EXPIRATION
                and rule.accuracy < self.EXPIRATION_THRESHOLD
                and not rule.is_inactive):
            accuracy_before = rule.accuracy
            rule.mark_inactive()
            reason = (
                f"Auto-expired: accuracy {accuracy_before:.2%} < "
                f"{self.EXPIRATION_THRESHOLD:.0%} threshold "
                f"after {rule.usage_count} executions"
            )
            self._repository.save_history(RuleHistory(
                rule_id=rule.rule_id,
                version=rule.version,
                previous_status=RuleStatus.APPROVED.value,
                new_status=RuleStatus.INACTIVE.value,
                accuracy_before=accuracy_before,
                accuracy_after=0.0,
                reason=reason,
            ))

    def get_applicable_rules(self, field: str) -> list[KnowledgeRule]:
        return self._get_applicable_rules(field)

    def explain_rule(self, rule_id: str) -> Optional[dict]:
        """Return explainability info for a rule."""
        rule = self._repository.get_rule(rule_id)
        if not rule:
            return None

        history = self._repository.get_history(rule_id=rule_id)
        return {
            "rule_id": rule.rule_id,
            "version": rule.version,
            "pattern": rule.pattern,
            "category": rule.category,
            "field": rule.field_name,
            "status": rule.status,
            "confidence": rule.confidence,
            "accuracy": rule.accuracy,
            "usage_count": rule.usage_count,
            "success_count": rule.success_count,
            "fail_count": rule.fail_count,
            "created_from_correction": rule.created_from_correction,
            "approved_by": rule.approved_by,
            "evidence_count": len(rule.evidence),
            "history": [h.to_dict() for h in history],
        }

    def rollback_rule(self, rule_id: str) -> bool:
        """Rollback a rule to PENDING status."""
        rule = self._repository.get_rule(rule_id)
        if not rule:
            return False

        prev_status = rule.status
        accuracy_before = rule.accuracy
        rule.status = RuleStatus.PENDING.value
        rule.updated_at = datetime.now(timezone.utc).isoformat()

        self._repository.save_history(RuleHistory(
            rule_id=rule.rule_id,
            version=rule.version,
            previous_status=prev_status,
            new_status=RuleStatus.PENDING.value,
            accuracy_before=accuracy_before,
            accuracy_after=0.0,
            reason="Manual rollback to PENDING",
        ))

        self._repository.save_rule(rule)
        return True
