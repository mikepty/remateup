import re

_RE_CURRENCY = re.compile(r"\$|[A-Z]{3}|B/|BS\.|USD|COP|PAB", re.IGNORECASE)
_RE_NUMBER = re.compile(r"[\d.,]+")


class CurrencyNormalizer:
    def normalize(self, raw: str) -> dict:
        amount = self.parse_amount(raw)
        currency = self.detect_currency(raw)
        return {
            "raw": raw,
            "normalized": amount,
            "currency": currency,
            "success": amount is not None,
        }

    def parse_amount(self, raw: str) -> float:
        if not raw:
            return None
        cleaned = re.sub(r"[^\d.,]", "", str(raw))
        cleaned = cleaned.strip(".")
        if not cleaned:
            return None
        if "," in cleaned and "." in cleaned:
            last_comma = cleaned.rfind(",")
            last_dot = cleaned.rfind(".")
            if last_comma > last_dot:
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                cleaned = cleaned.replace(",", "")
        elif "," in cleaned:
            if cleaned.count(",") == 1 and len(cleaned.split(",")[1]) <= 2:
                cleaned = cleaned.replace(",", ".")
            else:
                cleaned = cleaned.replace(",", "")
        try:
            return round(float(cleaned), 2)
        except ValueError:
            return None

    def detect_currency(self, text: str) -> str:
        if not text:
            return "UNKNOWN"
        upper = text.upper().strip()
        if re.search(r"\bB\.?\s*/", upper):
            return "HNL"
        if "USD" in upper:
            return "USD"
        if "COP" in upper:
            return "COP"
        if "PAB" in upper:
            return "PAB"
        if "$" in text:
            return "LOCAL"
        return "UNKNOWN"
