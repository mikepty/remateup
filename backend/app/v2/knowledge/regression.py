"""Regression Protection — automatically tests new rules against Golden Dataset
and rejects rules that reduce precision."""

import json
import os
from typing import Any, Optional

from backend.app.v2.knowledge.models import KnowledgeRule, RuleHistory, RuleStatus
from backend.app.v2.knowledge.repository import KnowledgeRepository
from backend.app.v2.knowledge.rules import RuleEngine
from backend.app.v2.parser.context import ParserContext
from backend.app.v2.parser.factory import ParserFactory


def _load_golden_dataset(path: str = "") -> dict:
    if not path:
        base = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "..",
            "evaluation", "golden_dataset", "records.json"
        )
        path = os.path.abspath(base)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class RegressionGuard:
    def __init__(self, repository: Optional[KnowledgeRepository] = None,
                 rule_engine: Optional[RuleEngine] = None,
                 parser_factory: Optional[ParserFactory] = None):
        self._repository = repository or KnowledgeRepository()
        self._rule_engine = rule_engine or RuleEngine(repository=repository)
        self._parser_factory = parser_factory or ParserFactory()

    def evaluate_rule(self, rule: KnowledgeRule, dataset_path: str = "") -> dict:
        """Evaluate a single rule against the Golden Dataset.
        Returns metrics + pass/fail."""
        dataset = _load_golden_dataset(dataset_path)
        total_before = 0
        total_after = 0
        correct_before = 0
        correct_after = 0

        for suite in dataset.get("test_suites", []):
            country = suite.get("pais", "")
            for aviso in suite.get("expected_avisos", []):
                expected = aviso.get(rule.field_name)
                if expected is None:
                    continue
                parser = self._parser_factory.get_parser(country, "REMATE")
                text = self._build_test_text(aviso)
                ctx = ParserContext(
                    country=country, document_type="REMATE", text=text
                )
                results = parser.parse(ctx)
                result = results.get(rule.field_name)

                if result and result.is_found:
                    total_before += 1
                    if self._matches(expected, result.value):
                        correct_before += 1

                rule_result = self._rule_engine.apply_rules(
                    field=rule.field_name, text=text, previous_result=result
                )
                final_value = rule_result.value if (rule_result and rule_result.is_found) else (
                    result.value if (result and result.is_found) else None
                )

                if final_value is not None:
                    total_after += 1
                    if self._matches(expected, final_value):
                        correct_after += 1

        precision_before = correct_before / max(total_before, 1)
        precision_after = correct_after / max(total_after, 1)
        regression = precision_after < precision_before

        return {
            "rule_id": rule.rule_id,
            "field": rule.field_name,
            "pattern": rule.pattern,
            "total_before": total_before,
            "correct_before": correct_before,
            "precision_before": round(precision_before, 4),
            "total_after": total_after,
            "correct_after": correct_after,
            "precision_after": round(precision_after, 4),
            "regression": regression,
            "delta": round(precision_after - precision_before, 4),
        }

    def approve_with_guard(self, rule: KnowledgeRule,
                           dataset_path: str = "") -> tuple[bool, dict]:
        """Approve only if no regression. Auto-reject if regression detected."""
        evaluation = self.evaluate_rule(rule, dataset_path)
        if evaluation["regression"]:
            rule.reject()
            self._repository.save_history(RuleHistory(
                rule_id=rule.rule_id,
                version=1,
                previous_status=RuleStatus.PENDING.value,
                new_status=RuleStatus.REJECTED.value,
                accuracy_before=evaluation["precision_before"],
                accuracy_after=evaluation["precision_after"],
                reason=f"Regression detected: {evaluation['precision_before']:.2%} -> {evaluation['precision_after']:.2%}",
            ))
            self._repository.save_rule(rule)
            return False, evaluation

        rule.approve(approved_by="regression_guard")
        self._repository.save_history(RuleHistory(
            rule_id=rule.rule_id,
            version=1,
            previous_status=RuleStatus.PENDING.value,
            new_status=RuleStatus.APPROVED.value,
            accuracy_before=evaluation["precision_before"],
            accuracy_after=evaluation["precision_after"],
            reason="No regression detected. Approved by RegressionGuard.",
        ))
        self._repository.save_rule(rule)
        return True, evaluation

    def batch_evaluate(self, dataset_path: str = "") -> dict:
        """Evaluate all pending rules against the dataset."""
        pending = self._repository.get_rules(status=RuleStatus.PENDING.value)
        results = []
        for rule in pending:
            ev = self.evaluate_rule(rule, dataset_path)
            results.append(ev)
        return {
            "total_evaluated": len(results),
            "regressions": sum(1 for r in results if r["regression"]),
            "improvements": sum(1 for r in results if r["delta"] > 0),
            "results": results,
        }

    def _build_test_text(self, aviso: dict) -> str:
        """Build a realistic test text from expected aviso data."""
        parts = ["AVISO DE REMATE"]
        for field in ["expediente", "finca", "demandante", "demandado"]:
            val = aviso.get(field)
            if val:
                label = field.upper()
                parts.append(f"{label}: {val}")
        base = aviso.get("base") or aviso.get("precio_base")
        if base:
            parts.append(f"BASE: {base}")
        fecha = aviso.get("fecha_remate")
        if fecha:
            parts.append(f"FECHA DE REMATE: {fecha}")
        return "\n".join(parts)

    def _matches(self, expected: Any, actual: Any) -> bool:
        if expected is None and actual is None:
            return True
        if expected is None or actual is None:
            return False
        return str(expected).strip() == str(actual).strip()
