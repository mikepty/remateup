"""KnowledgeAnalyzer — detects patterns, categories, and generates rule candidates from corrections."""

import re
from collections import Counter
from typing import Optional

from backend.app.v2.knowledge.models import (
    CorrectionEvent, KnowledgeCategory, KnowledgeEvidence, KnowledgeRule,
    RuleStatus, RuleType,
)
from backend.app.v2.knowledge.repository import KnowledgeRepository
from backend.app.v2.knowledge.patterns import PatternGenerator
from backend.app.v2.knowledge.aliases import AliasManager


class KnowledgeAnalyzer:
    MIN_CORRECTIONS_FOR_PATTERN = 2
    MIN_CORRECTIONS_FOR_ALIAS = 1

    def __init__(self, repository: Optional[KnowledgeRepository] = None,
                 pattern_generator: Optional[PatternGenerator] = None,
                 alias_manager: Optional[AliasManager] = None):
        self._repository = repository or KnowledgeRepository()
        self._pattern_generator = pattern_generator or PatternGenerator()
        self._alias_manager = alias_manager or AliasManager()

    def analyze_correction(self, event: CorrectionEvent) -> list[KnowledgeRule]:
        candidates: list[KnowledgeRule] = []
        if not event.evidence_text or not event.corrected_value:
            return candidates

        category = self._pattern_generator.detect_category(
            str(event.corrected_value), event.field_name, event.evidence_text
        )

        pattern = self._pattern_generator.generate_for_value(
            str(event.corrected_value), event.field_name
        )
        if pattern:
            rule = KnowledgeRule(
                rule_type=RuleType.REGEX.value,
                category=category,
                field_name=event.field_name,
                pattern=pattern,
                confidence=event.confidence * 0.8,
                status=RuleStatus.PENDING.value,
                created_from_correction=event.document_id,
                evidence=[KnowledgeEvidence(
                    text_snippet=event.evidence_text,
                    source_document=event.document_id,
                    field_name=event.field_name,
                    confidence=event.confidence,
                )],
            )
            candidates.append(rule)

        if event.previous_value and event.corrected_value:
            prev = str(event.previous_value).strip().upper()
            curr = str(event.corrected_value).strip().upper()
            if len(prev) >= 3 and len(curr) >= 3 and prev != curr:
                self._alias_manager.learn_alias(
                    prev, curr, event.field_name,
                    evidence_text=event.evidence_text,
                    confidence=event.confidence * 0.6,
                )

        return candidates

    def analyze_batch(self, country: Optional[str] = None,
                      field: Optional[str] = None) -> list[KnowledgeRule]:
        corrections = self._repository.get_corrections(country=country, field_name=field)
        if len(corrections) < self.MIN_CORRECTIONS_FOR_PATTERN:
            return []

        grouped: dict[str, list[CorrectionEvent]] = {}
        for c in corrections:
            grouped.setdefault(c.field_name, []).append(c)

        candidates: list[KnowledgeRule] = []
        for field_name, events in grouped.items():
            if len(events) < self.MIN_CORRECTIONS_FOR_PATTERN:
                continue

            examples = [str(e.corrected_value) for e in events if e.corrected_value]
            if len(examples) < self.MIN_CORRECTIONS_FOR_PATTERN:
                continue

            evidence_texts = [str(e.evidence_text) for e in events if e.evidence_text]

            category = self._detect_batch_category(examples, field_name, evidence_texts)

            pattern = self._pattern_generator.generate_category_pattern(category, examples)
            if not pattern:
                pattern = self._pattern_generator.generate_from_examples(examples, field_name)

            if pattern:
                avg_conf = sum(e.confidence for e in events) / len(events)
                rule = KnowledgeRule(
                    rule_type=RuleType.REGEX.value,
                    category=category,
                    field_name=field_name,
                    pattern=pattern,
                    confidence=round(avg_conf * 0.9, 4),
                    status=RuleStatus.PENDING.value,
                    evidence=[
                        KnowledgeEvidence(
                            text_snippet=e.evidence_text,
                            source_document=e.document_id,
                            field_name=e.field_name,
                            confidence=e.confidence,
                        ) for e in events[:5]
                    ],
                )
                candidates.append(rule)

        return candidates

    def _detect_batch_category(self, examples: list[str], field_name: str,
                               evidence_texts: list[str]) -> str:
        categories = [
            self._pattern_generator.detect_category(ex, field_name, ev)
            for ex, ev in zip(examples, evidence_texts or examples)
        ]
        if categories:
            return Counter(categories).most_common(1)[0][0]
        return KnowledgeCategory.LABEL.value

    def detect_aliases(self, country: Optional[str] = None,
                       field: Optional[str] = None) -> list:
        corrections = self._repository.get_corrections(country=country, field_name=field)
        pairs: set[tuple[str, str]] = set()
        for c in corrections:
            if c.previous_value and c.corrected_value:
                p = str(c.previous_value).strip().upper()
                n = str(c.corrected_value).strip().upper()
                if p != n and len(p) >= 3 and len(n) >= 3:
                    pairs.add((p, n))
        return list(pairs)

    def find_variants(self, corrections: list[CorrectionEvent], field_name: str) -> list[dict]:
        """Find common variants in corrections — labels, formats, positions."""
        labels: Counter = Counter()
        formats: Counter = Counter()
        for c in corrections:
            if c.evidence_text:
                for keyword in ["BASE", "FINCA", "FECHA", "EXPEDIENTE",
                                "DEMANDANTE", "DEMANDADO", "VALOR", "PRECIO",
                                "MATRICULA", "AVALUO"]:
                    if keyword in c.evidence_text.upper():
                        labels[keyword] += 1
        return [
            {"type": "label", "value": lbl, "count": cnt}
            for lbl, cnt in labels.most_common(5)
        ]
