import re

from backend.app.v2.parser.base import ParserInterface
from backend.app.v2.parser.context import ParserContext
from backend.app.v2.parser.result import ParseResult


_SECTION_LABELS = {
    "expediente": [r"EXPEDIENTE", r"EXPE\.?", r"E\.?J\.?E\.?"],
    "finca": [r"FINCA", r"FINC", r"F\.?"],
    "precio_base": [r"BASE", r"BASE\s+DEL\s+REMATE", r"PRECIO\s+BASE"],
    "fecha_remate": [r"FECHA", r"FECHA\s+DE\s+REMATE", r"REMATE"],
    "demandante": [r"DEMANDANTE", r"ACTOR", r"EJECUTANTE"],
    "demandado": [r"DEMANDADO", r"DEUDOR", r"EJECUTADO"],
}

_PATTERNS = {
    "expediente": [
        r"(?:EXPEDIENTE|EXPE\.?|E\.?J\.?E\.?)\s*[:\s#N°]*\s*([\d]+[\d/\-\.\s]*)",
    ],
    "finca": [
        r"FINCA\s+(?:N[°o]\.?\s*)?(\d[\d\s]*)",
        r"FINC\s*[:\s]*(\d[\d\s/]*)",
        r"(?:MATRICULA\s+)?(?:INMUEBLE|PROPIEDAD)\s*[:\s]*(\d[\d\s/-]*)",
    ],
    "precio_base": [
        r"BASE\s+DEL\s+REMATE\s*[:\s]*B[/\.]?\s*([\d,\.]+)",
        r"BASE\s*[:\s]*B[/\.]?\s*([\d,\.]+)",
        r"BASE\s*[:\s]*([\d,\.]+)",
        r"VALOR\s+(?:DEL\s+)?(?:REMATE|BASE|AVALUO)\s*[:\s]*B[/\.]?\s*([\d,\.]+)",
    ],
    "fecha_remate": [
        r"FECHA\s*(?:DE\s+REMATE|DEL\s+REMATE|PROBABLE)?\s*[:\s]*(\d{1,2}\s+DE\s+[A-ZÁÉÍÓÚ]+\s+DE\s+\d{4})",
        r"REMATE\s*(?:PROBABLE|SEÑALADO)?\s*[:\s]*(\d{1,2}/\d{1,2}/\d{2,4})",
        r"(\d{1,2}\s+DE\s+[A-ZÁÉÍÓÚ]+\s+DE\s+\d{4})",
    ],
    "demandante": [
        r"DEMANDANTE\s*[:\s]*([A-ZÁÉÍÓÚ\s,\.]+?)(?:\n|\s{2,}|$)",
        r"ACTOR\s*[:\s]*([A-ZÁÉÍÓÚ\s,\.]+?)(?:\n|\s{2,}|$)",
    ],
    "demandado": [
        r"DEMANDADO\s*[:\s]*([A-ZÁÉÍÓÚ\s,\.]+?)(?:\n|\s{2,}|$)",
        r"DEUDOR\s*[:\s]*([A-ZÁÉÍÓÚ\s,\.]+?)(?:\n|\s{2,}|$)",
    ],
}


class PanamaRemateParser(ParserInterface):
    @property
    def country(self) -> str:
        return "PA"

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
        for pattern in patterns:
            m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if m:
                raw = m.group(1).strip() if m.lastindex and m.group(1) else m.group(0).strip()
                clean = re.sub(r'\s+', ' ', raw).strip()
                result.value = clean
                result.confidence = 0.95
                result.add_evidence(
                    source="text",
                    method=f"regex:{field_name}",
                    snippet=raw[:200],
                    confidence=0.95,
                )
                return True
        return False
