import re
from typing import Optional


_UNIDADES = {
    "CERO": 0, "UN": 1, "UNO": 1, "UNA": 1, "DOS": 2, "TRES": 3, "CUATRO": 4,
    "CINCO": 5, "SEIS": 6, "SIETE": 7, "OCHO": 8, "NUEVE": 9, "DIEZ": 10,
    "ONCE": 11, "DOCE": 12, "TRECE": 13, "CATORCE": 14, "QUINCE": 15,
    "DIECISEIS": 16, "DIECISIETE": 17, "DIECIOCHO": 18, "DIECINUEVE": 19,
    "VEINTE": 20, "VEINTIUN": 21, "VEINTIUNO": 21, "VEINTIUNA": 21,
    "VEINTIDOS": 22, "VEINTITRES": 23, "VEINTICUATRO": 24, "VEINTICINCO": 25,
    "VEINTISEIS": 26, "VEINTISIETE": 27, "VEINTIOCHO": 28, "VEINTINUEVE": 29,
}

_DECENAS = {
    "TREINTA": 30, "CUARENTA": 40, "CINCUENTA": 50, "SESENTA": 60,
    "SETENTA": 70, "OCHENTA": 80, "NOVENTA": 90,
}

_RE_WORD_PERCENT = re.compile(
    r"^([A-ZÁÉÍÓÚÑ]+(?:\s+[A-ZÁÉÍÓÚÑ]+)*?)\s+POR\s+CIENTO$", re.IGNORECASE
)


def words_to_number(text: str) -> Optional[float]:
    """Deterministic Spanish number-words -> number conversion.

    Supports: cero..veintinueve, decenas simples, decenas compuestas
    ('CUARENTA Y CINCO'), 'CIEN' and 'CIENTO' followed by units.
    Returns None when the text cannot be parsed.
    """
    if not text:
        return None
    upper = re.sub(r"\s+", " ", str(text)).strip().upper()
    upper = upper.replace("Á", "A").replace("É", "E").replace("Í", "I") \
        .replace("Ó", "O").replace("Ú", "U")
    if upper in _UNIDADES:
        return float(_UNIDADES[upper])
    if upper == "CIEN":
        return 100.0
    parts = upper.split(" ")
    if parts and parts[0] in _DECENAS:
        base = _DECENAS[parts[0]]
        if len(parts) == 1:
            return float(base)
        if len(parts) == 3 and parts[1] == "Y" and parts[2] in _UNIDADES:
            return float(base + _UNIDADES[parts[2]])
        return None
    if len(parts) == 2 and parts[0] == "CIENTO" and parts[1] in _UNIDADES:
        return float(100 + _UNIDADES[parts[1]])
    return None


class PercentageNormalizer:
    """Deterministic percentage normalization.

    40%    -> 40
    70 %   -> 70
    0.40   -> 40
    CUARENTA POR CIENTO -> 40

    The original textual value is always preserved.
    """

    def normalize(self, raw: str) -> dict:
        original = str(raw).strip()
        if not original:
            return {"raw": None, "valor_original": None, "normalized": None,
                    "valor_normalizado": None, "float": None, "success": False}
        value = self.to_percent(original)
        return {
            "raw": original,
            "valor_original": original,
            "normalized": value,
            "valor_normalizado": value,
            "float": float(value) if value is not None else None,
            "success": value is not None,
        }

    def to_percent(self, raw: str) -> Optional[float]:
        text = str(raw).strip()
        m = _RE_WORD_PERCENT.match(text)
        if m:
            return words_to_number(m.group(1))
        cleaned = re.sub(r"[^\d.,\-]", "", text)
        if not cleaned:
            return None
        cleaned = cleaned.replace(",", ".") if cleaned.count(",") == 1 and \
            len(cleaned.split(",")[1]) <= 2 else cleaned.replace(",", "")
        try:
            value = float(cleaned)
        except ValueError:
            return None
        if 0 < value <= 1:
            value *= 100
        if value == int(value):
            return float(int(value))
        return round(value, 2)


class NumberNormalizer:
    def normalize(self, raw: str) -> dict:
        cleaned = self.clean_number(raw)
        value = self.to_float(raw)
        return {
            "raw": raw,
            "normalized": cleaned,
            "float": value,
            "success": value is not None,
        }

    def clean_number(self, raw: str) -> str:
        if not raw:
            return ""
        cleaned = re.sub(r"[^\d.,-]", "", str(raw))
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
        return cleaned

    def to_float(self, raw: str) -> float:
        cleaned = self.clean_number(raw)
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
