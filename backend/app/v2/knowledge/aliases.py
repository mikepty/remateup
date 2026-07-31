"""Alias manager — learns and resolves equivalence mappings between terms.
Priority: builtin > approved learned > pending learned."""

import re
from typing import Optional

from backend.app.v2.knowledge.models import KnowledgeAlias, KnowledgeEvidence
from backend.app.v2.knowledge.repository import KnowledgeRepository


COMMON_ABBREVIATIONS = {
    "N°": "NUMERO", "NRO": "NUMERO", "NO.": "NUMERO",
    "B/.": "BALBOAS", "B/": "BALBOAS",
    "C/": "CALLE", "AV/": "AVENIDA", "AV": "AVENIDA",
    "LTDA": "LIMITADA", "SA": "S.A.", "S.A": "S.A.",
    "D/S": "DEMANDANTE", "DDO": "DEMANDADO",
    "EXP": "EXPEDIENTE", "EXPE": "EXPEDIENTE",
}


class AliasManager:
    def __init__(self, repository: Optional[KnowledgeRepository] = None):
        self._repository = repository or KnowledgeRepository()
        self._builtin = dict(COMMON_ABBREVIATIONS)

    def resolve(self, term: str, field: str) -> str:
        """Resolve alias by priority: builtin > approved learned > pending learned."""
        upper = term.strip().upper()

        # 1. Builtin has highest priority
        if upper in self._builtin:
            self._record_builtin_usage(upper)
            return self._builtin[upper]

        # 2. Approved learned aliases
        approved = self._repository.get_aliases(field=field, source=upper, status="APPROVED")
        if approved:
            approved[0].usage_count += 1
            return approved[0].target

        # 3. Pending learned aliases
        pending = self._repository.get_aliases(field=field, source=upper, status="PENDING")
        if pending:
            pending[0].usage_count += 1
            return pending[0].target

        return term

    def _record_builtin_usage(self, source: str):
        """Track builtin alias usage in the repository."""
        aliases = self._repository.get_aliases(source=source)
        if aliases:
            aliases[0].usage_count += 1

    def learn_alias(self, source: str, target: str, field: str,
                    evidence_text: str = "", confidence: float = 0.7) -> Optional[KnowledgeAlias]:
        upper_src = source.strip().upper()
        upper_tgt = target.strip().upper()
        if upper_src == upper_tgt or len(upper_src) < 2:
            return None

        if upper_src in self._builtin:
            return None

        alias = KnowledgeAlias(
            source=upper_src,
            target=upper_tgt,
            field_name=field,
            confidence=confidence,
            status="APPROVED" if confidence >= 0.8 else "PENDING",
            evidence=[KnowledgeEvidence(
                text_snippet=evidence_text,
                field_name=field,
                confidence=confidence,
            )] if evidence_text else [],
        )
        self._repository.save_alias(alias)
        return alias

    def get_all_aliases(self, field: Optional[str] = None) -> list[KnowledgeAlias]:
        return self._repository.get_aliases(field=field)

    def get_builtin_aliases(self) -> dict[str, str]:
        return dict(self._builtin)

    def normalize(self, text: str, field: str) -> str:
        """Apply all known aliases to normalize text.
        Priority: builtin > approved learned > pending learned."""
        result = text

        for src, tgt in self._builtin.items():
            result = re.sub(re.escape(src), tgt, result, flags=re.IGNORECASE)

        for alias in self._repository.get_aliases(field=field, status="APPROVED"):
            result = re.sub(re.escape(alias.source), alias.target, result, flags=re.IGNORECASE)
            alias.usage_count += 1

        for alias in self._repository.get_aliases(field=field, status="PENDING"):
            result = re.sub(re.escape(alias.source), alias.target, result, flags=re.IGNORECASE)
            alias.usage_count += 1

        return result
