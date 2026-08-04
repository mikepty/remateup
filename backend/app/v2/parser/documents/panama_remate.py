import re

from backend.app.v2.parser.base import ParserInterface
from backend.app.v2.parser.context import ParserContext
from backend.app.v2.parser.result import ParseResult


_SECTION_LABELS = {
    "expediente": [r"EXPEDIENTE", r"EXPE\.?", r"E\.?J\.?E\.?"],
    "finca": [r"FINCA", r"FINC", r"F\.?"],
    "precio_base": [r"BASE", r"BASE\s+DEL\s+REMATE", r"PRECIO\s+BASE",
                     r"AVAL[UÚ]O\s+COMERCIAL"],
    "fecha_remate": [r"FECHA", r"FECHA\s+DE\s+REMATE", r"REMATE"],
    "hora": [r"HORA", r"HORA\s+DE\s+REMATE"],
    "lugar": [r"JUZGADO", r"CORTE", r"PLAZA", r"TRIBUNAL"],
    "superficie": [r"SUPERFICIE", r"SUPERF", r"M2", r"METROS"],
    "provincia": [r"PROVINCIA", r"PROV"],
    "codigo_ubicacion": [r"CODIGO\s+DE\s+UBICACION", r"UBICACION", r"COD\.?\s+UBIC"],
    "categoria": [r"CATEGORIA", r"TIPO\s+DE\s+BIEN", r"TIPO\s+DE\s+PROCESO"],
    "proceso": [r"PROCESO", r"EJECUTIVO", r"MONITARIO", r"INSOLVENCIA"],
}

# Símbolo de moneda antes del monto: en Panamá aparece como B/. (balboas) o
# como $ según el periódico/juzgado. Ambos opcionales y equivalentes aquí.
_CURRENCY = r"(?:B[/\.]|\$)?"

_PATTERNS = {
    "expediente": [
        r"(?:EXPEDIENTE|EXPE\.?|E\.?J\.?E\.?)\s*[:\s#N°]*\s*([\d]+[\d/\-\.\s]*)",
        r"(?:Exp\.?\s*Electr\.?)\s*[:\s]*(\d+)",
    ],
    "finca": [
        r"FINCA\s+(?:N[°o]\.?\s*)?(\d[\d\s]*)",
        r"FINC\s*[:\s]*(\d[\d\s/]*)",
        r"(?:MATRICULA\s+)?(?:INMUEBLE|PROPIEDAD)\s*[:\s]*(\d[\d\s/-]*)",
        r"LA\s+FINCA\s+N[°o]\.?\s*(\d[\d\s]*)",
    ],
    "precio_base": [
        r"BASE\s+DEL\s+REMATE\s*[:\s]*" + _CURRENCY + r"\s*([\d,\.]+)",
        r"AVAL[UÚ]O\s+COMERCIAL\s*[:\s]*" + _CURRENCY + r"\s*([\d,\.]+)",
        r"servir[aá]?\s+de\s+base[^)]{0,400}?\(\s*[B8]?\s*/\s*\.?\s*([\d.,\s]+)\s*\)",
        r"(?:SIRVE\s+DE\s+BASE|BASE\s+DEL\s+REMATE)[^)]{0,400}?\(\s*[B8]?\s*/\s*\.?\s*([\d.,\s]+)\s*\)",
        r"BASE\s*[:\s]*" + _CURRENCY + r"\s*([\d,\.]+)",
        r"BASE\s*[:\s]*([\d,\.]+)",
        r"VALOR\s+(?:DEL\s+)?(?:REMATE|BASE|AVAL[UÚ]O(?:\s+COMERCIAL)?)\s*[:\s]*" + _CURRENCY + r"\s*([\d,\.]+)",
    ],
    "fecha_remate": [
        r"FECHA\s*(?:DE\s+REMATE|DEL\s+REMATE|PROBABLE)?\s*[:\s]*(\d{1,2}\s+DE\s+[A-ZÁÉÍÓÚ]+\s+DE\s+\d{4})",
        r"REMATE\s*(?:PROBABLE|SEÑALADO)?\s*[:\s]*(\d{1,2}/\d{1,2}/\d{2,4})",
        r"(\d{1,2}\s+DE\s+[A-ZÁÉÍÓÚ]+\s+DE\s+\d{4})",
    ],
    "demandante": [
        # "promovido por BANCO GENERAL S.A., contra..."
        r"(?:PROMOVIDO|INSTAURADO|PROPUESTO)\s+POR\s+"
        r"([A-ZÑÁÉÍÓÚ0-9.,& ]{3,80}?)(?:,|\s+EN\s+CONTRA|\n|\.\s)",
        # "A FAVOR DE BANCO..."
        r"A\s+FAVOR\s+DE\s+([A-ZÑÁÉÍÓÚ0-9.,& ]{3,80}?)(?:,|\n|\.\s)",
        # "POR BANCO GENERAL..."
        r"POR\s+([A-ZÑÁÉÍÓÚ0-9.,& ]{3,80}?)(?:,|\s+EN\s+CONTRA|\n)",
        # Fallback: "DEMANDANTE: X"
        r"DEMANDANTE\s*[:\s]*([A-ZÁÉÍÓÚ\s,\.]+?)(?:\n|\s{2,}|$)",
        # Interleaved: "promovido por ... contra" en líneas mezcladas
        r"(?:PROMOVIDO|PROPUESTO)\s+POR\s+([A-ZÑÁÉÍÓÚ0-9.,& ]{3,80}?)(?:\n|$)",
        # "EL SUSCRITO ... promovido por X" (caso ALGUACIL primero)
        r"(?:ALGUACIL|ALGUIL)\s+.*?POR\s+([A-ZÑÁÉÍÓÚ0-9.,& ]{3,60}?)(?:,|\n|\.\s)",
        # "X, SA, Y ..." después de "contra" en texto interleavado
        r"(?:CONTRA|EN\s+CONTRA)\s+(?:DE?\s*)?[A-ZÑÁÉÍÓÚ\s,\.]{5,80}?\s+POR\s+EL\s+BANCO\s+([A-ZÑÁÉÍÓÚ0-9.,& ]{3,60}?)(?:,|\n)",
    ],
    "demandado": [
        # "contra YAHELYS ITZEL JIMENEZ CASTILLO"
        r"(?:EN\s+)?CONTRA\s+DE?\s*([A-ZÑÁÉÍÓÚ0-9.,& ]{3,80}?)(?:,|\n|\.\s|POR\s+EL|$)",
        # "SIENDO LA PARTE DEMANDADA LUIS..."
        r"(?:PARTE\s+)?DEMANDADA?\s+([A-ZÑÁÉÍÓÚ0-9.,& ]{3,80}?)(?:,|\n|\.\s|CED|$)",
        # Fallback: "DEMANDADO: X"
        r"DEMANDADO\s*[:\s]*([A-ZÁÉÍÓÚ\s,\.]+?)(?:\n|\s{2,}|$)",
        # Interleaved: "contra X" al final de línea
        r"(?:EN\s+)?CONTRA\s+(?:DE?\s*)?([A-ZÑÁÉÍÓÚ\s,\.]{3,80}?)(?:\n|$)",
    ],
    "hora": [
        r"HORA\s*[:\s]*(\d{1,2}[:\.]\d{2}\s*(?:A\.?M\.?|P\.?M\.?)?)",
        r"(?:a\s+las?\s+|hora\s*)(\d{1,2}[:\.]\d{2}\s*(?:A\.?M\.?|P\.?M\.?)?)",
        r"(\d{1,2}[:\.]\d{2}\s*(?:A\.?M\.?|P\.?M\.?))",
    ],
    "lugar": [
        r"JUZGADO\s+(?:DEL?\s+)?(?:PRIMER?|SEGUNDO|TERCER|CUARTO|QUINTO|DECIMO)\s+DE\s+CIRCUITO",
        r"JUZGADO\s+(?:DEL?\s+)?(?:PRIMER?|SEGUNDO|TERCER|CUARTO|QUINTO|DECIMO)\s+DE\s+INSOLVENCIA",
        r"JUZGADO\s+(?:DEL?\s+)?(?:PRIMER?|SEGUNDO|TERCER|CUARTO|QUINTO|DECIMO)\s+DE\s+LO(?:S)?\s+(?:CIVIL|PENAL|FAMILIA)",
        r"CORTE\s+SUPREMA",
        r"PLAZA\s+DE\s+ARMAS",
        r"TRIBUNAL\s+(?:DE\s+)?(?:CIRCUITO|FAMILIA|CIVIL)",
        r"SECRETAR[IÍ]A\s+DE\s+TRIBUNAL",
        # Interleaved: "JUZGADO... CIRCUITO... JUDICIAL" en líneas mezcladas
        r"JUZGADO\s+\w+\s+DE\s+CIRCUITO\s+DE\s+INSOLVENCIA",
        r"JUZGADO\s+\w+\s+DE\s+CIRCUITO\s+JUDICIAL",
    ],
    "superficie": [
        r"SUPERFICIE\s*[:\s]*([\d,\.]+)\s*(?:M2|M²|METROS?)",
        r"([\d,\.]+)\s*(?:M2|M²|METROS?\s+CUADRADOS?)",
        r"SUPERF(?:ICIE)?\s*[:\s]*([\d,\.]+)",
    ],
    "provincia": [
        r"PROVINCIA\s+DE\s+([A-ZÁÉÍÓÚÑ\s]+?)(?:,|\.|\n)",
        r"(?:CHIRIQUI|PANAMA|COLON|VERAGUAS|HERRERA|LOS\s+SANTOS|COCLE|BOCAS\s+DEL\s+TORO|PANAMA\s+OESTE)",
    ],
    "codigo_ubicacion": [
        r"CODIGO\s+DE\s+UBICACION\s*[:\s]*(\d+)",
        r"UBICACION\s*(?:DEL?\s+)?(?:CODIGO|COD)\s*[:\s]*(\d+)",
        r"COD\.?\s+UBIC\.?\s*[:\s]*(\d+)",
    ],
    "categoria": [
        r"(?:UNA?\s+)?(?:VIVIENDA(?:\s+UNIFAMILIAR)?|CASA(?:\s+RESIDENCIAL)?|RESIDENCIA|QUINTA)\b",
        r"APARTAMENTO|APTO\b",
        r"TERRENO|LOTE\b",
        r"\bVEH[IÍ]CULO\b|\bCARRO\b|\bMOTOCICLETA\b",
        r"\bLOCAL\b|\bCOMERCIO\b|\bOFICINA\b",
        r"CUOTAS?\s+PARTES?",
        r"CATEGORIA\s*[:\s]*(\d)",
    ],
    "proceso": [
        # "dentro del Proceso Ejecutivo Hipotecario"
        r"(?:DENTRO\s+DEL?\s+)?PROCESO\s+(EJECUTIVO(?:\s+HIPOTECARIO)?|MONITARIO(?:\s+HIPOTECARIO)?|INSOLVENCIA(?:\s+JUDICIAL)?|SUMARIO|EJECUTIVO\s+SIMPLE)",
        # "TIPO DE PROCESO EJECUTIVA HIPOTECARIA"
        r"TIPO\s+DE\s+PROCESO\s+(EJECUTIV[OA](?:\s+HIPOTECARIA?)?|MONITORIO(?:\s+HIPOTECARIO)?|INSOLVENCIA|SUMARIO)",
        # "Proceso Ejecutivo" solo
        r"PROCESO\s+(EJECUTIVO|MONITARIO|MONITORIO|INSOLVENCIA|SUMARIO)",
        # Fallback: "EJECUTIVO HIPOTECARIO" sin la palabra "proceso"
        r"(EJECUTIVO\s+HIPOTECARIO(?:\s+[A-Z]+)?)",
    ],
    "email_observaciones": [
        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
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
                # Normalizar campos especiales
                if field_name == "categoria":
                    clean = self._normalizar_categoria(clean, text)
                elif field_name == "proceso":
                    clean = self._normalizar_proceso(clean)
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

    @staticmethod
    def _normalizar_categoria(match_text: str, full_text: str) -> str:
        upper = (" " + match_text + " " + full_text).upper()
        if "CUOTA" in upper and "PARTE" in upper:
            return "MISCELANEO"
        for kw, cat in (("APARTAMENTO", "APARTAMENTO"), ("APTO", "APARTAMENTO"),
                        ("VEHICULO", "VEHICULO"), ("VEHÍCULO", "VEHICULO"),
                        ("CARRO", "VEHICULO"), ("MOTOCICLETA", "VEHICULO"),
                        ("CASA", "CASA"), ("VIVIENDA", "CASA"),
                        ("RESIDENCIA", "CASA"), ("QUINTA", "CASA"),
                        ("LOCAL", "MISCELANEO"), ("COMERCIO", "MISCELANEO"),
                        ("OFICINA", "MISCELANEO")):
            if (" " + kw + " ") in upper or upper.startswith(" " + kw + " ") or upper.endswith(" " + kw + " "):
                return cat
        if "TERRENO" in upper or "LOTE" in upper:
            return "TERRENO"
        return "TERRENO"

    @staticmethod
    def _normalizar_proceso(match_text: str) -> str:
        """Normaliza el tipo de proceso judicial."""
        upper = match_text.upper().strip()
        if "INSOLVENCIA" in upper:
            return "INSOLVENCIA"
        if "MONITARIO" in upper or "MONITORIO" in upper:
            return "MONITARIO"
        if "EJECUTIVO" in upper and "HIPOTECARIO" in upper:
            return "EJECUTIVO HIPOTECARIO"
        if "EJECUTIVO" in upper:
            return "EJECUTIVO"
        if "SUMARIO" in upper:
            return "SUMARIO"
        return upper.title()
