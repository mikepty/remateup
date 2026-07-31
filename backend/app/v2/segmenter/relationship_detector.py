import re
from dataclasses import dataclass, field
from typing import Optional

from backend.app.v2.segmenter.models import DetectedSection


@dataclass
class DetectedRelationship:
    field_name: str
    label_text: str
    value_text: str
    confidence: float = 0.0
    section_index: Optional[int] = None
    source_section_type: str = ""

    def to_dict(self) -> dict:
        return {
            "field_name": self.field_name,
            "label": self.label_text,
            "value": self.value_text,
            "confidence": self.confidence,
        }


class RelationshipDetector:
    KNOWN_LABELS = {
        "expediente": ["expediente", "exp", "no.", "numero", "número", "n°", "nº"],
        "demandante": ["demandante", "demante", "actor", "demte"],
        "demandado": ["demandado", "ddo", "demandada", "dda"],
        "finca_matr": [
            "finca", "folio real", "matrícula", "matricula",
            "folio", "finca n°", "finca nº", "finca no.",
        ],
        "base": ["base", "avalúo", "avaluo", "valor", "base del remate", "base de remate"],
        "provincia": ["provincia", "departamento", "lugar", "distrito", "corregimiento", "ciudad", "municipio"],
        "fianza_porcentaje": [
            "fianza", "depósito", "deposito", "garantía", "garantia",
            "fianza de ley",
        ],
        "minimo_porcentaje": ["mínimo", "minimo", "mínimo legal", "minimo legal"],
        "categoria": ["categoría", "categoria", "clase", "tipo de bien"],
        "descripcion": ["descripción", "descripcion", "lote", "inmueble", "propiedad"],
        "lugar": ["juzgado", "tribunal", "despacho", "juzgado"],
        "fecha": ["fecha", "día", "dia", "el día", "fecha de remate"],
        "hora": ["hora", "a las", "hora de remate"],
        "superficie": [
            "superficie", "área", "area", "metros", "m²", "m2", "hectáreas",
            "hectareas",
        ],
        "proceso": ["proceso", "causa", "juicio", "expediente"],
        "lote_casa": ["lote", "casa", "apartamento", "local", "oficina", "bodega", "terreno"],
    }

    def __init__(self):
        self._patterns: dict[str, list[re.Pattern]] = {}
        for field_name, labels in self.KNOWN_LABELS.items():
            self._patterns[field_name] = [
                re.compile(rf"\b{re.escape(label)}\b", re.IGNORECASE)
                for label in labels
            ]

    def detect_pairs(self, sections: list[DetectedSection]) -> list[DetectedRelationship]:
        relationships: list[DetectedRelationship] = []
        for sec_idx, section in enumerate(sections):
            text = section.text
            for field_name, patterns in self._patterns.items():
                for pat in patterns:
                    match = pat.search(text)
                    if match:
                        value = self._extract_value_after_label(text, match.end())
                        confidence = self._calculate_confidence(field_name, match, section)
                        rel = DetectedRelationship(
                            field_name=field_name,
                            label_text=match.group(0),
                            value_text=value,
                            confidence=confidence,
                            section_index=sec_idx,
                            source_section_type=section.section_type.value,
                        )
                        relationships.append(rel)
                        break
        return self._deduplicate(relationships)

    def _extract_value_after_label(self, text: str, start_pos: int) -> str:
        remainder = text[start_pos:]
        remainder = remainder.strip().lstrip(":;,-–— ")
        lines = remainder.split("\n")
        first_line = lines[0].strip() if lines else ""
        parts = first_line.split(",")
        value = parts[0].strip() if parts else ""
        value = re.sub(r"^\s*[:\s]+\s*", "", value)
        return value[:200]

    def _calculate_confidence(self, field_name: str, match: re.Match, section: DetectedSection) -> float:
        base = section.confidence if section.confidence > 0 else 0.7
        text_after = section.text[match.end():].strip()
        has_separator = bool(re.match(r"^[\s:;\-–—=]+", text_after))
        has_value = bool(text_after)
        boost = 0.0
        if has_separator:
            boost += 0.1
        if has_value and len(text_after) > 2:
            boost += 0.1
        return round(min(base + boost, 1.0), 4)

    def _deduplicate(self, relationships: list[DetectedRelationship]) -> list[DetectedRelationship]:
        seen: dict[str, DetectedRelationship] = {}
        for rel in relationships:
            key = rel.field_name
            if key not in seen or rel.confidence > seen[key].confidence:
                seen[key] = rel
        return list(seen.values())

    def extract_field_value(self, text: str) -> tuple[str, str]:
        for field_name, patterns in self._patterns.items():
            for pat in patterns:
                match = pat.search(text)
                if match:
                    value = self._extract_value_after_label(text, match.end())
                    if value:
                        return field_name, value
        return ("", "")

    def find_all_labels(self, text: str) -> list[tuple[str, str, int]]:
        results: list[tuple[str, str, int]] = []
        text_lower = text.lower()
        for field_name, labels in self.KNOWN_LABELS.items():
            for label in labels:
                pos = text_lower.find(label)
                if pos >= 0:
                    results.append((field_name, label, pos))
        results.sort(key=lambda x: x[2])
        return results
