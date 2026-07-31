"""Performance benchmark for Knowledge Engine overhead.
Ensures knowledge adds <10% overhead compared to parser alone."""

import time
from typing import Optional

from backend.app.v2.knowledge.repository import KnowledgeRepository
from backend.app.v2.knowledge.rules import RuleEngine
from backend.app.v2.knowledge.models import KnowledgeRule
from backend.app.v2.parser.context import ParserContext
from backend.app.v2.parser.factory import ParserFactory


class KnowledgeBenchmark:
    MAX_OVERHEAD_PCT = 10.0

    def __init__(self, repository: Optional[KnowledgeRepository] = None,
                 rule_engine: Optional[RuleEngine] = None):
        self._repository = repository or KnowledgeRepository()
        self._rule_engine = rule_engine or RuleEngine(repository=repository)

    def benchmark_parser(self, parser_id: str = "PA/REMATE",
                         iterations: int = 100) -> dict:
        factory = ParserFactory()
        parser = factory.get_parser("PA", "REMATE")
        text = self._build_test_text()

        context = ParserContext(
            country="PA", document_type="REMATE", text=text
        )

        parser_times: list[float] = []
        knowledge_times: list[float] = []

        for _ in range(iterations):
            start = time.perf_counter()
            parser.parse(context)
            elapsed = time.perf_counter() - start
            parser_times.append(elapsed)

            start = time.perf_counter()
            for field_name, result in parser.parse(context).items():
                if result.is_not_found:
                    self._rule_engine.apply_rules(
                        field=field_name, text=context.text, previous_result=result
                    )
            elapsed = time.perf_counter() - start
            knowledge_times.append(elapsed)

        avg_parser = sum(parser_times) / len(parser_times)
        avg_knowledge = sum(knowledge_times) / len(knowledge_times)
        overhead_pct = ((avg_knowledge - avg_parser) / max(avg_parser, 0.0001)) * 100

        return {
            "iterations": iterations,
            "parser_avg_ms": round(avg_parser * 1000, 4),
            "knowledge_avg_ms": round(avg_knowledge * 1000, 4),
            "overhead_pct": round(overhead_pct, 2),
            "within_limit": overhead_pct <= self.MAX_OVERHEAD_PCT,
        }

    def _build_test_text(self) -> str:
        return (
            "AVISO DE REMATE\n"
            "EXPEDIENTE N° 12345-2026\n"
            "FINCA N° 78901\n"
            "BASE: B/.100,000.00\n"
            "FECHA DE REMATE: 15 DE SEPTIEMBRE DE 2026\n"
            "DEMANDANTE: JUAN PEREZ\n"
            "DEMANDADO: MARIA GOMEZ\n"
        )

    def setup_test_data(self):
        """Add knowledge rules for benchmark."""
        for field, pattern in [
            ("finca", r"FINCA\s*(?:N[°º]\s*)?(\d+)"),
            ("expediente", r"EXPEDIENTE\s*(?:N[°º]\s*)?([\d\-]+)"),
        ]:
            rule = KnowledgeRule(
                field_name=field,
                pattern=pattern,
                status="APPROVED",
                confidence=0.9,
            )
            self._repository.save_rule(rule)
