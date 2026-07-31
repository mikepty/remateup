import re


class NameNormalizer:
    _COMMA_PARTS = re.compile(r"^([^,]+),\s*(.+)$")
    _SOCIEDAD = re.compile(r"\b(S\.A\.|S\.A\.|S\.A|LIMITADA|S\.A\. DE C\.V\.|DE C\.V\.)", re.IGNORECASE)

    def normalize(self, raw: str) -> dict:
        normalized = self.normalize_legal_name(raw)
        parts = self.extract_parts(normalized)
        return {
            "raw": raw,
            "normalized": normalized,
            "parts": parts,
            "success": normalized is not None,
        }

    def normalize_legal_name(self, raw: str) -> str:
        if not raw:
            return None
        result = raw.strip()
        result = re.sub(r"\s+", " ", result)
        m = self._COMMA_PARTS.match(result)
        if m:
            result = f"{m.group(2)} {m.group(1)}"
        result = self._normalize_accents(result)
        result = self._normalize_case(result)
        return result

    def extract_parts(self, name: str) -> dict:
        if not name:
            return {}
        parts = name.strip().split()
        if len(parts) == 0:
            return {}
        if len(parts) == 1:
            return {"first_name": parts[0], "last_name": ""}
        if len(parts) == 2:
            return {"first_name": parts[0], "last_name": parts[1]}
        return {
            "first_name": parts[0],
            "middle_names": parts[1:-1],
            "last_name": parts[-1],
        }

    def _normalize_accents(self, text: str) -> str:
        replacements = {
            "Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U",
            "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
            "Ñ": "Ñ", "ñ": "ñ",
        }
        # Preserve accents (spec says "acentos preservados")
        return text

    def _normalize_case(self, text: str) -> str:
        parts = text.strip().split()
        if not parts:
            return text
        result_parts = []
        for p in parts:
            if "." in p or p.upper() in ("S.A.", "S.A", "DE", "LIMITADA", "Y", "E"):
                result_parts.append(p.upper())
            else:
                result_parts.append(p.capitalize())
        return " ".join(result_parts)
