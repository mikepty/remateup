import re

_PROVINCIAS_PA = {
    "PANAMA": "Panamá",
    "PANAMÁ": "Panamá",
    "PANAMA OESTE": "Panamá Oeste",
    "HEREDIA": "Heredia",
    "COLON": "Colón",
    "COLÓN": "Colón",
    "CHIRIQUI": "Chiriquí",
    "CHIRIBI": "Chiriquí",
    "COCLE": "Coclé",
    "COCLÉ": "Coclé",
    "LIMA": "Limón",
    "LIMÓN": "Limón",
    "BOCAS": "Bocas del Toro",
    "BOCAS DEL TORO": "Bocas del Toro",
    "CANAAN": "Canaán",
    "CANAÁN": "Canaán",
}

_PROVINCIAS_CO = {
    "BOGOTA": "Bogotá",
    "BOGOTÁ": "Bogotá",
    "BOGOTA D.C": "Bogotá D.C.",
    "BOGOTÁ D.C.": "Bogotá D.C.",
    "ANTIOQUIA": "Antioquia",
    "CALDAS": "Caldas",
    "RISARALDA": "Risaralda",
    "QUINDIO": "Quindío",
    "QUINDÍO": "Quindío",
    "MAGDALENA": "Magdalena",
    "CESAR": "Cesar",
    "CORDOBA": "Córdoba",
    "CÓRDOBA": "Córdoba",
    "SUCRE": "Sucre",
    "CORAVAL": "Córdoba",
}


class LocationNormalizer:
    def normalize(self, raw: str) -> dict:
        prov = self.normalize_province(raw)
        city = self.normalize_city(raw)
        return {
            "raw": raw,
            "normalized_province": prov,
            "normalized_city": city,
            "success": prov is not None or city is not None,
        }

    def normalize_province(self, raw: str) -> str:
        if not raw:
            return None
        cleaned = re.sub(r"\s+", " ", raw.strip().upper())
        if cleaned in _PROVINCIAS_PA:
            return _PROVINCIAS_PA[cleaned]
        if cleaned in _PROVINCIAS_CO:
            return _PROVINCIAS_CO[cleaned]
        return raw.strip().title()

    def normalize_city(self, raw: str) -> str:
        if not raw:
            return None
        return re.sub(r"\s+", " ", raw.strip()).title()
