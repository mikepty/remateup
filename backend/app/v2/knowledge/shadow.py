"""Shadow Learning — runs parser vs parser+knowledge side by side,
comparing results without replacing the parser output."""

from typing import Any, Optional

from backend.app.v2.knowledge.models import ShadowComparison
from backend.app.v2.knowledge.repository import KnowledgeRepository
from backend.app.v2.knowledge.rules import RuleEngine
from backend.app.v2.parser.base import ParserInterface
from backend.app.v2.parser.context import ParserContext


class ShadowLearner:
    def __init__(self, repository: Optional[KnowledgeRepository] = None,
                 rule_engine: Optional[RuleEngine] = None):
        self._repository = repository or KnowledgeRepository()
        self._rule_engine = rule_engine or RuleEngine(repository=repository)

    def compare(self, parser: ParserInterface, context: ParserContext,
                document_id: str = "") -> list[ShadowComparison]:
        """Run parser alone and parser+knowledge, save comparison for each field."""
        parser_results = parser.parse(context)
        comparisons: list[ShadowComparison] = []

        for field_name, result in parser_results.items():
            parser_value = str(result.value) if result.value is not None else None
            parser_conf = result.confidence

            rule_result = self._rule_engine.apply_rules(
                field=field_name, text=context.text, previous_result=result
            )

            knowledge_value = None
            knowledge_conf = 0.0
            rule_id = ""
            rule_version = 0

            if rule_result and rule_result.is_found:
                knowledge_value = str(rule_result.value)
                knowledge_conf = rule_result.confidence
                for ev in rule_result.evidence:
                    method = ev.get("method", "")
                    parts = method.split(":")
                    if len(parts) >= 3:
                        rule_id = parts[2]
                        rule_version = int(parts[3][1:]) if parts[3].startswith("v") else 0

            same = parser_value == knowledge_value
            winner = "tie"
            if not same:
                if rule_result and rule_result.is_found and not result.is_found:
                    winner = "knowledge"
                elif result.is_found and not (rule_result and rule_result.is_found):
                    winner = "parser"
                elif rule_result and rule_result.is_found and result.is_found:
                    winner = "knowledge" if rule_result.confidence > result.confidence else "parser"

            comp = ShadowComparison(
                document_id=document_id,
                field_name=field_name,
                parser_value=parser_value,
                parser_confidence=parser_conf,
                knowledge_value=knowledge_value,
                knowledge_confidence=knowledge_conf,
                knowledge_rule_id=rule_id,
                knowledge_rule_version=rule_version,
                winner=winner,
                difference=not same,
                evidence_text=context.text[:500],
            )
            self._repository.save_shadow(comp)
            comparisons.append(comp)

        return comparisons

    def get_comparisons(self, field_name: Optional[str] = None,
                        limit: int = 100) -> list[ShadowComparison]:
        return self._repository.get_shadow_comparisons(field_name=field_name, limit=limit)

    def get_summary(self) -> dict:
        """Get summary of shadow comparison results."""
        comparisons = self._repository.get_shadow_comparisons(limit=10000)
        total = len(comparisons)
        if total == 0:
            return {"total_comparisons": 0}
        parser_wins = sum(1 for c in comparisons if c.winner == "parser")
        knowledge_wins = sum(1 for c in comparisons if c.winner == "knowledge")
        ties = sum(1 for c in comparisons if c.winner == "tie")
        differences = sum(1 for c in comparisons if c.difference)
        return {
            "total_comparisons": total,
            "parser_wins": parser_wins,
            "knowledge_wins": knowledge_wins,
            "ties": ties,
            "differences": differences,
            "knowledge_improvement": round(
                knowledge_wins / max(total, 1) * 100, 2
            ),
        }
