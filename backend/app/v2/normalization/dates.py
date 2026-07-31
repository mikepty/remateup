import re

_MONTHS_ES = {
    "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
    "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
    "septiembre": "09", "setiembre": "09", "octubre": "10",
    "noviembre": "11", "diciembre": "12",
}

_RE_DATE_ES = re.compile(
    r"(\d{1,2})\s*(?:de\s+)?([A-Za-z]+)\s*(?:de\s+)?(\d{4})", re.IGNORECASE
)
_RE_DATE_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_RE_DATE_DOT = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")
_RE_DATE_SLASH = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")


class DateNormalizer:
    def normalize(self, raw: str) -> dict:
        iso = self.to_iso(raw)
        fmt = self.detect_format(raw)
        return {
            "raw": raw,
            "normalized": iso,
            "format": fmt,
            "success": iso is not None and iso != "",
        }

    def detect_format(self, raw: str) -> str:
        raw = raw.strip()
        if _RE_DATE_ISO.match(raw):
            return "ISO"
        if _RE_DATE_DOT.match(raw):
            return "DOT"
        if _RE_DATE_SLASH.match(raw):
            return "SLASH"
        if _RE_DATE_ES.match(raw):
            return "SPANISH"
        return "UNKNOWN"

    def to_iso(self, raw: str) -> str:
        if not raw or not raw.strip():
            return ""

        raw = raw.strip()

        m = _RE_DATE_ISO.match(raw)
        if m:
            y, mo, d = m.groups()
            if self._valid_date(int(y), int(mo), int(d)):
                return f"{y}-{mo}-{d}"

        m = _RE_DATE_DOT.match(raw)
        if m:
            d, mo, y = m.groups()
            if self._valid_date(int(y), int(mo), int(d)):
                return f"{y}-{mo.zfill(2)}-{d.zfill(2)}"

        m = _RE_DATE_SLASH.match(raw)
        if m:
            d, mo, y = m.groups()
            if self._valid_date(int(y), int(mo), int(d)):
                return f"{y}-{mo.zfill(2)}-{d.zfill(2)}"

        m = _RE_DATE_ES.match(raw)
        if m:
            d, month_name, y = m.groups()
            mo = _MONTHS_ES.get(month_name.lower())
            if mo:
                if self._valid_date(int(y), int(mo), int(d)):
                    return f"{y}-{mo}-{int(d):02d}"

        return ""

    def _valid_date(self, year: int, month: int, day: int) -> bool:
        if month < 1 or month > 12:
            return False
        if day < 1 or day > 31:
            return False
        if year < 1900 or year > 2100:
            return False
        return True
