from typing import Optional

from backend.app.v2.normalization.text import TextNormalizer
from backend.app.v2.normalization.names import NameNormalizer
from backend.app.v2.normalization.dates import DateNormalizer
from backend.app.v2.normalization.currency import CurrencyNormalizer
from backend.app.v2.normalization.numbers import NumberNormalizer, PercentageNormalizer
from backend.app.v2.normalization.locations import LocationNormalizer


FIELD_NORMALIZERS = {
    "fecha": "date",
    "fecha_remate": "date",
    "hora": "text",
    "expediente": "text",
    "finca": "number",
    "finca_matr": "text",
    "precio_base": "currency",
    "base": "currency",
    "fianza": "currency",
    "minimo": "currency",
    "fianza_porcentaje": "number",
    "minimo_porcentaje": "number",
    "demandante": "name",
    "demandado": "name",
    "lugar": "location",
    "proceso": "text",
    "categoria": "text",
    "provincia": "location",
    "descripcion": "text",
    "descripcion_completa": "text",
    "codigo": "text",
    "codigo_ubicacion": "text",
    "codigo_ubicacion_prensa": "text",
    "codigo_fuente": "text",
    "codigo_prensa": "text",
    "fecha_prensa": "date",
    "pagina_prensa": "number",
    "periodico": "text",
    "email_observaciones": "text",
    "lote_casa": "text",
    "plano": "text",
    "superficie": "number",
    "prevista": "text",
}


class FieldNormalizer:
    def __init__(self):
        self._text = TextNormalizer()
        self._names = NameNormalizer()
        self._dates = DateNormalizer()
        self._currency = CurrencyNormalizer()
        self._numbers = NumberNormalizer()
        self._percentages = PercentageNormalizer()
        self._locations = LocationNormalizer()

    def normalize_field(self, field_name: str, raw_value: str) -> dict:
        if field_name.lower() in ("fianza_porcentaje", "minimo_porcentaje"):
            return self._percentages.normalize(str(raw_value))
        field_type = FIELD_NORMALIZERS.get(field_name.lower(), "text")
        return self.normalize_by_type(field_type, raw_value)

    def normalize_by_type(self, field_type: str, raw_value: str) -> dict:
        if raw_value is None:
            return {"raw": None, "normalized": None, "success": False}

        if field_type == "date":
            return self._dates.normalize(str(raw_value))
        elif field_type == "currency":
            return self._currency.normalize(str(raw_value))
        elif field_type == "number":
            return self._numbers.normalize(str(raw_value))
        elif field_type == "name":
            return self._names.normalize(str(raw_value))
        elif field_type == "location":
            return self._locations.normalize(str(raw_value))
        else:
            return self._text.normalize(str(raw_value))

    def normalize_all(self, fields: dict) -> dict:
        result = {}
        for fname, fdata in fields.items():
            raw_value = None
            if isinstance(fdata, dict):
                raw_value = fdata.get("value")
            elif isinstance(fdata, str):
                raw_value = fdata
            else:
                raw_value = str(fdata) if fdata else None

            norm = self.normalize_field(fname, raw_value)
            result[fname] = {
                **(fdata if isinstance(fdata, dict) else {"value": raw_value}),
                "normalized": norm.get("normalized"),
                "normalization": norm,
            }
        return result
