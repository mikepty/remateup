"""NoticeScorer — independent score 0.00–1.00 for each notice."""

from backend.app.v2.validator.models import NoticeDecision, RuleResult
from backend.app.v2.validator.production_rules import (
    STRONG_FIELDS, MEDIUM_FIELDS, WEAK_FIELDS,
)


class NoticeScorer:
    WEIGHTS = {
        "valid_header": 0.20,
        "strong_fields": 0.20,
        "medium_fields": 0.15,
        "field_count": 0.10,
        "co_occurrence": 0.10,
        "consistency": 0.10,
        "no_publicidad": 0.05,
        "no_edicto": 0.05,
        "structural": 0.05,
    }

    def score(self, decision: NoticeDecision) -> float:
        score = 0.0

        # Header
        if decision.header_valid:
            score += self.WEIGHTS["valid_header"]

        # Strong fields
        strong_count = len(STRONG_FIELDS & set(decision.fields_found))
        strong_ratio = min(strong_count / max(len(STRONG_FIELDS), 1), 1.0)
        score += strong_ratio * self.WEIGHTS["strong_fields"]

        # Medium fields
        medium_count = len(MEDIUM_FIELDS & set(decision.fields_found))
        medium_ratio = min(medium_count / max(len(MEDIUM_FIELDS), 1), 1.0)
        score += medium_ratio * self.WEIGHTS["medium_fields"]

        # Field count
        total_possible = len(STRONG_FIELDS) + len(MEDIUM_FIELDS) + len(WEAK_FIELDS)
        field_ratio = min(len(decision.fields_found) / max(total_possible, 1), 1.0)
        score += field_ratio * self.WEIGHTS["field_count"]

        # Co-occurrence
        co_ok = any(r.passed for r in decision.rules_applied if r.rule_name == "field_co_occurrence")
        if co_ok:
            score += self.WEIGHTS["co_occurrence"]

        # Consistency
        consistency_issues = len(decision.inconsistencies)
        if consistency_issues == 0:
            score += self.WEIGHTS["consistency"]
        else:
            score += max(0, self.WEIGHTS["consistency"] * (1 - consistency_issues * 0.5 / max(len(decision.inconsistencies), 1)))

        # Publicidad / Edicto
        not_pub = any(r.passed for r in decision.rules_applied if r.rule_name == "not_publicidad")
        not_ed = any(r.passed for r in decision.rules_applied if r.rule_name == "not_edicto")
        if not_pub:
            score += self.WEIGHTS["no_publicidad"]
        if not_ed:
            score += self.WEIGHTS["no_edicto"]

        # Structural
        if decision.structural_valid:
            score += self.WEIGHTS["structural"]

        return round(min(max(score, 0.0), 1.0), 4)
