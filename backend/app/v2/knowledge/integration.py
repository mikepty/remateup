"""Parser-Knowledge integration layer.

Wraps existing parsers with knowledge-aware capabilities without modifying them.
Uses approved rules as fallback when parser returns NOT_FOUND or low confidence.
Supports full explainability for every extraction decision.
"""

from typing import Optional

from backend.app.v2.parser.base import ParserInterface
from backend.app.v2.parser.context import ParserContext
from backend.app.v2.parser.result import ParseResult
from backend.app.v2.knowledge.rules import RuleEngine
from backend.app.v2.knowledge.repository import KnowledgeRepository


class KnowledgeAwareWrapper:
    """Wraps a ParserInterface to augment results with knowledge rules.

    Does NOT modify the underlying parser — wraps it transparently.
    Knowledge rules are applied only when parser returns NOT_FOUND.
    Every extraction includes explainability via evidence.
    """

    def __init__(self, parser: ParserInterface,
                 rule_engine: Optional[RuleEngine] = None,
                 repository: Optional[KnowledgeRepository] = None):
        self._parser = parser
        self._rule_engine = rule_engine or RuleEngine(repository=repository)

    @property
    def parser(self) -> ParserInterface:
        return self._parser

    def parse(self, context: ParserContext) -> dict[str, ParseResult]:
        results = self._parser.parse(context)
        for field_name, result in results.items():
            if result.is_not_found or result.requires_review:
                knowledge_result = self._rule_engine.apply_rules(
                    field=field_name, text=context.text, previous_result=result
                )
                if knowledge_result and knowledge_result.is_found:
                    results[field_name] = knowledge_result
        return results

    def __getattr__(self, name):
        return getattr(self._parser, name)
