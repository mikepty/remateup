"""Pattern generator — creates generalized regex patterns from correction evidence,
now with category-aware generation (LABEL, MONEY, DATE, PERSON, PROPERTY, CASE_NUMBER)."""

import re
from typing import Optional

from backend.app.v2.knowledge.models import KnowledgeCategory


class PatternGenerator:
    MIN_CONFIDENCE = 0.3
    MAX_PATTERN_LENGTH = 200

    # Category-specific regex templates
    CATEGORY_PATTERNS = {
        KnowledgeCategory.LABEL: r"({variants})",
        KnowledgeCategory.MONEY: r"([\$B/\.\s]*[\d\.,]+(?:\s*(?:B/?\.|USD|dólares|pesos))?)",
        KnowledgeCategory.DATE: r"(\d{{1,2}}\s+DE\s+[A-ZÁÉÍÓÚÑ]+\s+DE\s*\d{{2,4}})",
        KnowledgeCategory.PERSON: r"([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s\.]+(?:,\s*[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s\.]*)*)",
        KnowledgeCategory.PROPERTY: r"([\d]+)",
        KnowledgeCategory.CASE_NUMBER: r"([\d\-]+)",
    }

    def generate_for_value(self, value: str, field: str) -> Optional[str]:
        if not value or len(value) < 3:
            return None
        numeric = re.sub(r"[^\d]", "", value)
        if numeric and len(numeric) >= 3:
            return r"(\d[\d\.,\-/]*)"
        if len(value) >= 5:
            return re.escape(value)
        return None

    def generate_from_examples(self, examples: list[str], field: str) -> Optional[str]:
        if len(examples) < 2:
            return None
        cleaned = [self._normalize(e) for e in examples]
        common = self._longest_common_prefix(cleaned)
        if not common or len(common) < 3:
            return None
        escaped = re.escape(common)
        suffixes = [c[len(common):] for c in cleaned]
        if all(s == suffixes[0] for s in suffixes):
            pattern = f"{escaped}({re.escape(suffixes[0])})" if suffixes[0] else escaped
        else:
            pattern = f"{escaped}(.+?)(?:$|\\s)"
        if len(pattern) > self.MAX_PATTERN_LENGTH:
            return None
        return pattern

    def detect_category(self, value: str, field: str, evidence_text: str = "") -> str:
        """Detect the knowledge category for a given correction."""
        val_upper = value.strip().upper()
        ev_upper = evidence_text.strip().upper()

        if field in ("precio_base", "base"):
            return KnowledgeCategory.MONEY.value
        if field in ("fecha_remate",):
            return KnowledgeCategory.DATE.value

        if re.search(r"\d", value) and not re.search(r"[A-ZÁÉ]", value):
            if "-" in value:
                return KnowledgeCategory.CASE_NUMBER.value
            return KnowledgeCategory.PROPERTY.value

        has_money_value = re.search(r"[\d,\.]+", val_upper)
        has_money_context = re.search(r"B/?\.|\$|USD|BALBOAS|PESOS|DÓLARES|BASE|VALOR|PRECIO|AVALÚO|AVALUO", ev_upper)
        if has_money_value and has_money_context:
            return KnowledgeCategory.MONEY.value

        date_match = re.search(
            r"\d{1,2}\s+DE\s+[A-ZÁÉÍÓÚÑ]+\s+DE\s*\d{2,4}", ev_upper
        )
        if date_match:
            return KnowledgeCategory.DATE.value

        name_match = re.search(
            r"DEMANDANTE|DEMANDADO|DEUDOR|ACREEDOR", ev_upper
        )
        if name_match and re.search(r"[A-ZÁÉÍÓÚÑ]{3,}", val_upper):
            return KnowledgeCategory.PERSON.value

        return KnowledgeCategory.LABEL.value

    def generate_category_pattern(self, category: str, examples: list[str]) -> Optional[str]:
        """Generate a pattern optimized for the detected category."""
        try:
            cat = KnowledgeCategory(category)
        except ValueError:
            return self.generate_from_examples(examples, "")

        if cat == KnowledgeCategory.MONEY:
            return r"([\$B/\.\s]*[\d\.,]+(?:\s*(?:B/?\.|USD|dólares|pesos))?)"
        if cat == KnowledgeCategory.DATE:
            return r"(\d{1,2}\s+DE\s+[A-ZÁÉÍÓÚÑ]+\s+DE\s*\d{2,4})"
        if cat in (KnowledgeCategory.CASE_NUMBER, KnowledgeCategory.PROPERTY):
            return r"([\d\-]+)"

        return self.generate_from_examples(examples, "")

    def _normalize(self, text: str) -> str:
        return text.strip().upper()

    def _longest_common_prefix(self, strings: list[str]) -> str:
        if not strings:
            return ""
        prefix = strings[0]
        for s in strings[1:]:
            i = 0
            while i < len(prefix) and i < len(s) and prefix[i] == s[i]:
                i += 1
            prefix = prefix[:i]
            if not prefix:
                break
        return prefix
