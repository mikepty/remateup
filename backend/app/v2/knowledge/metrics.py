"""MetricsTracker — full metrics dashboard backend with JSON export."""

from collections import Counter
from typing import Optional

from backend.app.v2.knowledge.repository import KnowledgeRepository
from backend.app.v2.knowledge.models import RuleStatus


class MetricsTracker:
    def __init__(self, repository: Optional[KnowledgeRepository] = None):
        self._repository = repository or KnowledgeRepository()

    def get_overall_accuracy(self) -> float:
        rules = self._repository.get_rules(status=RuleStatus.APPROVED.value)
        if not rules:
            return 0.0
        total_usage = sum(r.usage_count for r in rules)
        total_success = sum(r.success_count for r in rules)
        if total_usage == 0:
            return 0.0
        return round(total_success / total_usage, 4)

    def get_field_accuracy(self, field: str) -> float:
        rules = self._repository.get_approved_rules(field=field)
        if not rules:
            return 0.0
        total_usage = sum(r.usage_count for r in rules)
        total_success = sum(r.success_count for r in rules)
        if total_usage == 0:
            return 0.0
        return round(total_success / total_usage, 4)

    def get_country_accuracy(self) -> dict[str, float]:
        accuracies: dict[str, float] = {}
        for country in ("PA", "CO"):
            rules = self._repository.get_rules_by_country(country)
            approved = [r for r in rules if r.is_approved]
            if not approved:
                accuracies[country] = 0.0
                continue
            total_usage = sum(r.usage_count for r in approved)
            total_success = sum(r.success_count for r in approved)
            accuracies[country] = round(total_success / max(total_usage, 1), 4)
        return accuracies

    def get_most_used_rules(self, limit: int = 5) -> list[dict]:
        rules = self._repository.get_rules(status=RuleStatus.APPROVED.value)
        sorted_rules = sorted(rules, key=lambda r: r.usage_count, reverse=True)
        return [r.to_dict() for r in sorted_rules[:limit]]

    def get_most_failed_rules(self, limit: int = 5) -> list[dict]:
        rules = self._repository.get_rules(status=RuleStatus.APPROVED.value)
        sorted_rules = sorted(rules, key=lambda r: r.fail_count, reverse=True)
        return [r.to_dict() for r in sorted_rules[:limit] if r.fail_count > 0]

    def get_dashboard(self) -> dict:
        """Full metrics dashboard — JSON exportable."""
        approved = self._repository.get_rules(status=RuleStatus.APPROVED.value)
        pending = self._repository.get_rules(status=RuleStatus.PENDING.value)
        rejected = self._repository.get_rules(status=RuleStatus.REJECTED.value)
        inactive = self._repository.get_rules(status=RuleStatus.INACTIVE.value)

        corrections = self._repository.count_corrections()

        total_usage = sum(r.usage_count for r in approved)
        total_success = sum(r.success_count for r in approved)

        field_accuracies: dict[str, float] = {}
        for r in approved:
            if r.field_name not in field_accuracies:
                field_accuracies[r.field_name] = self.get_field_accuracy(r.field_name)

        category_distribution: dict[str, int] = {}
        for r in self._repository.get_rules():
            if r.category:
                category_distribution[r.category] = category_distribution.get(r.category, 0) + 1

        return {
            "summary": {
                "total_corrections": corrections,
                "total_rules": len(approved) + len(pending) + len(rejected) + len(inactive),
                "approved_rules": len(approved),
                "pending_rules": len(pending),
                "rejected_rules": len(rejected),
                "inactive_rules": len(inactive),
            },
            "accuracy": {
                "overall": round(total_success / max(total_usage, 1), 4),
                "total_usage": total_usage,
                "total_success": total_success,
            },
            "by_field": field_accuracies,
            "by_country": self.get_country_accuracy(),
            "top_rules": self.get_most_used_rules(limit=10),
            "top_failed_rules": self.get_most_failed_rules(limit=10),
            "category_distribution": category_distribution,
        }

    def get_summary(self) -> dict:
        approved = self._repository.get_rules(status=RuleStatus.APPROVED.value)
        total_rules = self._repository.count_rules()
        total_usage = sum(r.usage_count for r in approved)
        total_success = sum(r.success_count for r in approved)
        avg_accuracy = round(total_success / max(total_usage, 1), 4)
        return {
            "total_rules": total_rules,
            "approved_rules": len(approved),
            "total_usage": total_usage,
            "total_success": total_success,
            "overall_accuracy": avg_accuracy,
            "fields_covered": len(set(r.field_name for r in approved)),
        }
