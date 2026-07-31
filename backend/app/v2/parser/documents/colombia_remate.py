import re
from typing import Any

from backend.app.v2.parser.base import ParserInterface
from backend.app.v2.parser.context import ParserContext
from backend.app.v2.parser.result import ParseResult
from backend.app.v2.normalization.numbers import words_to_number


_PERCENT_LABELS = (
    r"FIANZA\s+DEL\s+POSTOR|PORCENTAJE\s+DE\s+FIANZA|FIANZA"
)
_MIN_PERCENT_LABELS = (
    r"POSTURA\s+ADMISIBLE|PORCENTAJE\s+MÍNIMO|PORCENTAJE\s+MINIMO|"
    r"BASE\s+MÍNIMA|BASE\s+MINIMA|MÍNIMO|MINIMO"
)
_GAP_PERCENT = r"(?:(?:[A-ZÁÉÍÓÚÑ]+[ \t]+){1,3}[A-ZÁÉÍÓÚÑ]+\s*[:\-]?\s*)"
_SEP = r"\s*[:\-]?\s*"
_NO_WORD = r"(?<![A-ZÁÉÍÓÚÑ])"

_PATTERNS = {
    "expediente": [
        r"(?:EXPEDIENTE|RADICADO|PROCESO)\s*(?:N[°o]\.?|NÚMERO|NUMERO)?\s*[:\s]*([\d\-/\.]+)",
        r"N[°o]\.?\s*(?:EXP|EXPE)\s*[:\s]*([\d\-/\.]+)",
    ],
    "finca": [
        r"(?:MATRÍCULA|MATRICULA)\s+(?:INMOBILIARIA\s+)?(?:N[°o]\.?\s*)?(\d[\d\s\-/]*)",
        r"(?:CEDULA\s+)?CATASTRAL\s*[:\s]*(\d[\d\s\-/]*)",
        r"FINCA\s+(?:N[°o]\.?\s*)?(\d[\d\s]*)",
    ],
    "precio_base": [
        r"(?:AVALÚO|AVALUO|BASE|PRECIO)\s*[:\s]*(?:COMERCIAL|DEL\s+BIEN|DEL\s+INMUEBLE)?\s*[:\s]*\$?\s*([\d,\.]+)",
        r"VALOR\s+(?:COMERCIAL|DEL\s+INMUEBLE)\s*[:\s]*\$?\s*([\d,\.]+)",
    ],
    "fecha_remate": [
        r"FECHA\s*(?:DE\s+REMATE|PROGRAMADA|SEÑALADA|ESTIMADA)?\s*[:\s]*(\d{1,2}\s+DE\s+[A-ZÁÉÍÓÚ]+\s+DE\s+\d{4})",
        r"REMATE\s*(?:EL\s+DÍA|SEÑALADO\s+PARA\s+EL)?\s*[:\s]*(\d{1,2}/\d{1,2}/\d{2,4})",
    ],
    "demandante": [
        r"DEMANDANTE\s*[:\s]*([A-ZÁÉÍÓÚÑ\s,\.]+?)(?:\n|\s{3,}|$)",
        r"ACTOR\s*[:\s]*([A-ZÁÉÍÓÚÑ\s,\.]+?)(?:\n|\s{3,}|$)",
    ],
    "demandado": [
        r"DEMANDADO\s*[:\s]*([A-ZÁÉÍÓÚÑ\s,\.]+?)(?:\n|\s{3,}|$)",
        r"DEUDOR\s*[:\s]*([A-ZÁÉÍÓÚÑ\s,\.]+?)(?:\n|\s{3,}|$)",
    ],
    "fianza_porcentaje": [
        rf"({_PERCENT_LABELS}){_SEP}(?:{_GAP_PERCENT})??{_NO_WORD}(\d{{1,3}}(?:[.,]\d+)?)\s*%",
        rf"({_PERCENT_LABELS}){_SEP}(?:{_GAP_PERCENT})??{_NO_WORD}([A-ZÁÉÍÓÚÑ]+(?:\s+[A-ZÁÉÍÓÚÑ]+)*?)\s+POR\s+CIENTO\b",
        rf"({_PERCENT_LABELS}){_SEP}(?:{_GAP_PERCENT})??{_NO_WORD}(\d{{1,3}}(?:[.,]\d+)?)\s*$",
    ],
    "minimo_porcentaje": [
        rf"({_MIN_PERCENT_LABELS}){_SEP}(?:{_GAP_PERCENT})??{_NO_WORD}(\d{{1,3}}(?:[.,]\d+)?)\s*%",
        rf"({_MIN_PERCENT_LABELS}){_SEP}(?:{_GAP_PERCENT})??{_NO_WORD}([A-ZÁÉÍÓÚÑ]+(?:\s+[A-ZÁÉÍÓÚÑ]+)*?)\s+POR\s+CIENTO\b",
        rf"({_MIN_PERCENT_LABELS}){_SEP}(?:{_GAP_PERCENT})??{_NO_WORD}(\d{{1,3}}(?:[.,]\d+)?)\s*$",
    ],
}


class ColombiaRemateParser(ParserInterface):
    @property
    def country(self) -> str:
        return "CO"

    @property
    def document_type(self) -> str:
        return "REMATE"

    @property
    def supported_fields(self) -> list[str]:
        return list(_PATTERNS.keys())

    def parse(self, context: ParserContext) -> dict[str, ParseResult]:
        results: dict[str, ParseResult] = {}
        text = context.text

        for field_name in self.supported_fields:
            result = ParseResult(field_name=field_name)
            matched = self._extract_field(text, field_name, result)
            if matched:
                result.set_found(result.value, result.confidence)
            else:
                result.set_not_found()
            results[field_name] = result

        return results

    def _extract_field(self, text: str, field_name: str, result: ParseResult) -> bool:
        patterns = _PATTERNS.get(field_name, [])
        is_percentage = field_name in ("fianza_porcentaje", "minimo_porcentaje")
        for pattern in patterns:
            m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if m:
                matched_text = re.sub(r'\s+', ' ', m.group(0)).strip()
                raw = m.group(m.lastindex).strip() if m.lastindex else matched_text
                clean = re.sub(r'\s+', ' ', raw).strip()
                original: Any = clean
                value: Any = clean
                if is_percentage:
                    number = words_to_number(clean)
                    if number is not None:
                        value = int(number) if number == int(number) else round(number, 2)
                        original = f"{clean} POR CIENTO"
                    else:
                        number = self._to_number(clean)
                        if number is not None:
                            value = number
                            if matched_text.rstrip().endswith("%"):
                                original = f"{clean}%"
                result.value = value
                result.original_value = original
                result.confidence = 0.95
                result.add_evidence(
                    source="text",
                    method=f"regex:{field_name}",
                    snippet=matched_text[:200],
                    confidence=0.95,
                )
                return True
        return False

    @staticmethod
    def _to_number(raw: str):
        cleaned = raw.strip()
        if not cleaned:
            return None
        cleaned = re.sub(r"[^\d.,\-]", "", cleaned)
        if "," in cleaned and "." in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        elif "," in cleaned:
            if cleaned.count(",") == 1 and len(cleaned.split(",")[1]) <= 2:
                cleaned = cleaned.replace(",", ".")
            else:
                cleaned = cleaned.replace(",", "")
        try:
            value = float(cleaned)
        except ValueError:
            return None
        return int(value) if value == int(value) else round(value, 2)
