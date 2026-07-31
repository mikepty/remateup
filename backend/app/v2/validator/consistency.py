"""ConsistencyEngine — checks field-level coherence within a single notice."""

import re
from typing import Optional

from backend.app.v2.validator.models import Inconsistency


_RE_DATE = re.compile(r"\b(\d{1,2})\s*(?:de\s+)?([A-Za-z]+)\s*(?:de\s+)?(\d{4})\b")
_RE_DATE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_RE_MONEY = re.compile(r"\$?\s*[\d,]+(?:\.\d{2,})?")


class ConsistencyEngine:
    def check(self, fields_found: dict, text: str = "") -> list[Inconsistency]:
        inconsistencies: list[Inconsistency] = []
        field_names = {k.lower() for k in fields_found}

        # 1. Base vs precio_base consistency
        base_vals = self._get_field_values(fields_found, {"base", "precio_base"})
        if len(base_vals) >= 2 and len(set(base_vals)) > 1:
            inconsistencies.append(Inconsistency(
                field_1="base/precio_base",
                field_2="base/precio_base",
                description=f"Múltiples valores distintos para base: {base_vals}",
                severity="high",
            ))

        # 2. Finca vs finca_matr
        finca_vals = self._get_field_values(fields_found, {"finca", "finca_matr"})
        if len(finca_vals) >= 2 and len(set(finca_vals)) > 1:
            inconsistencies.append(Inconsistency(
                field_1="finca/finca_matr",
                field_2="finca/finca_matr",
                description=f"Múltiples valores de finca: {finca_vals}",
                severity="high",
            ))

        # 3. Fecha consistency
        dates = self._extract_dates(text)
        fecha_vals = self._get_field_values(fields_found, {"fecha", "fecha_remate"})
        if len(dates) >= 2:
            if len(set(dates)) >= 2:
                inconsistencies.append(Inconsistency(
                    field_1="fecha/fecha_remate",
                    field_2="fecha/fecha_remate",
                    description=f"Múltiples fechas distintas en el texto: {dates}",
                    severity="medium",
                ))

        # 4. Demandante = Demandado check
        demante = self._get_field_values(fields_found, {"demandante"})
        demado = self._get_field_values(fields_found, {"demandado"})
        if demante and demado:
            if any(d.strip().upper() == demado[0].strip().upper() for d in demante):
                inconsistencies.append(Inconsistency(
                    field_1="demandante",
                    field_2="demandado",
                    description="Demandante y demandado tienen el mismo nombre",
                    severity="high",
                ))

        # 5. Fecha imposible
        for d in dates:
            if self._is_impossible_date(d):
                inconsistencies.append(Inconsistency(
                    field_1="fecha",
                    field_2="fecha",
                    description=f"Fecha imposible: {d}",
                    severity="medium",
                ))

        return inconsistencies

    def _get_field_values(self, fields: dict, names: set) -> list[str]:
        vals = []
        for fname, fdata in fields.items():
            if fname.lower() in names:
                val = fdata.get("value") if isinstance(fdata, dict) else str(fdata)
                if val and str(val).strip():
                    vals.append(str(val).strip())
        return vals

    def _extract_dates(self, text: str) -> list[str]:
        dates = []
        for m in _RE_DATE.finditer(text):
            dates.append(m.group(0))
        for m in _RE_DATE_ISO.finditer(text):
            dates.append(m.group(0))
        return dates

    def _is_impossible_date(self, date_str: str) -> bool:
        m = _RE_DATE_ISO.match(date_str)
        if m:
            year = int(m.group(1))
            month = int(m.group(2))
            day = int(m.group(3))
            if month > 12 or day > 31:
                return True
            if year < 1900 or year > 2100:
                return True
            return False
        m = _RE_DATE.match(date_str)
        if m:
            day = int(m.group(1))
            year = int(m.group(3))
            if day > 31:
                return True
            if year < 1900 or year > 2100:
                return True
            return False
        return False
