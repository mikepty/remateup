import re

from backend.app.v2.document.models import SectionType
from backend.app.v2.segmenter.models import DetectedBlock, DetectedSection, BoundingBox


_RE_AVISO_HEADER = re.compile(
    r"AVISO\s+DE\s+[A-Z]{0,2}E[MN]ATE", re.IGNORECASE
)
_RE_EDICTO_HEADER = re.compile(
    r"EDICTO\s+EMPLAZATORIO", re.IGNORECASE
)
_RE_REMATE_KEYWORDS = re.compile(
    r"\b(?:REMATE|REMAT[EA]|MARTILLO|SUBASTA)\b", re.IGNORECASE
)
_RE_PORTADA_INDICATORS = re.compile(
    r"\b(?:PORTADA|RESUMEN|CONTENIDO|SUMARIO|BREVES)\b", re.IGNORECASE
)
_RE_FINCA = re.compile(
    r"\b(?:FINCA|FOLIO|MATR[IÍ]CULA|MATRICULA)\s*(?:N[°º]|No\.?|NUMERO|N[UÚ]MERO)?\s*:?\s*\d+",
    re.IGNORECASE,
)
_RE_EXPEDIENTE = re.compile(
    r"\b(?:EXPEDIENTE|EXP\.?|EXP[E]?)\s*(?:N[°º]|No\.?|NUMERO|N[UÚ]MERO)?\s*:?\s*\d+",
    re.IGNORECASE,
)
_RE_VALOR = re.compile(
    r"\b(?:BASE|AVAL[UÚ]O|AVALUO|VALOR|PRECIO)\s*(?:DEL\s+)?(?:REMATE)?\s*:?\s*\$?",
    re.IGNORECASE,
)
_RE_FIANZA = re.compile(
    r"\b(?:FIANZA|DEP[ÓO]SITO|DEPOSITO|GARANT[IÍ]A)\b", re.IGNORECASE
)
_RE_PARTES = re.compile(
    r"\b(?:DEMANDANTE|DEMANDADO|ACTOR|DEMTE|DDO\.?|DEMANDADA)\b", re.IGNORECASE
)
_RE_TITLE_LIKE = re.compile(
    r"^(?:AVISO|EDICTO|NOTIFICACI[OÓ]N|CITACI[OÓ]N|REQUERIMIENTO)",
    re.IGNORECASE,
)
_RE_UBICACION = re.compile(
    r"\b(?:PROVINCIA|DISTRITO|CORREGIMIENTO|MUNICIPIO|DEPARTAMENTO|CIUDAD|LUGAR)\b",
    re.IGNORECASE,
)
_RE_DESCRIPCION_KEYWORDS = re.compile(
    r"\b(?:DESCRIPCI[OÓ]N|DESCRIPCION|LOTE|CASA|APARTAMENTO|TERRENO|VEH[IÍ]CULO|VEHICULO|INMUEBLE|PROPIEDAD|UBICAD[OA]|SITO|SITA)\b",
    re.IGNORECASE,
)
_RE_VALORES_KEYWORDS = re.compile(
    r"\b(?:BASE|AVAL[UÚ]O|PRECIO|VALOR|FIANZA|DEP[ÓO]SITO|GARANT[IÍ]A|CANON|ARRENDAMIENTO)\b",
    re.IGNORECASE,
)


def _get_bbox_from_blocks(blocks: list[DetectedBlock]) -> BoundingBox:
    xs = [b.bbox.x0 for b in blocks if b.bbox]
    ys = [b.bbox.y0 for b in blocks if b.bbox]
    x1s = [b.bbox.x1 for b in blocks if b.bbox]
    y1s = [b.bbox.y1 for b in blocks if b.bbox]
    if not xs:
        return BoundingBox(0, 0, 0, 0)
    return BoundingBox(
        x0=min(xs), y0=min(ys), x1=max(x1s), y1=max(y1s),
    )


class SectionDetector:
    def __init__(self):
        self._portada_cache: dict[str, bool] = {}

    def detect_sections(self, blocks: list[DetectedBlock]) -> list[DetectedSection]:
        if not blocks:
            return []
        return self._classify_blocks(blocks)

    def _classify_blocks(self, blocks: list[DetectedBlock]) -> list[DetectedSection]:
        sections: list[DetectedSection] = []

        for block in blocks:
            text = block.text.strip()
            if not text:
                continue

            stype = self._classify_single_block(block)

            section = DetectedSection(
                section_type=stype,
                text=text,
                bbox=block.bbox,
                confidence=block.confidence,
                blocks=[block],
            )
            sections.append(section)

        return self._merge_adjacent_same_type(sections)

    def _classify_single_block(self, block: DetectedBlock) -> SectionType:
        text = block.text.strip()
        if not text:
            return SectionType.UNKNOWN

        if _RE_TITLE_LIKE.match(text):
            return SectionType.HEADER

        if _RE_VALOR.search(text) and _RE_FIANZA.search(text):
            return SectionType.VALORES

        if _RE_PARTES.search(text):
            labels = _RE_PARTES.findall(text)
            unique_labels = set(l.lower() for l in labels)
            if len(unique_labels) >= 1:
                return SectionType.PARTIES

        if _RE_UBICACION.search(text):
            return SectionType.UBICACION

        if _RE_DESCRIPCION_KEYWORDS.search(text):
            return SectionType.DESCRIPCION

        if _RE_VALORES_KEYWORDS.search(text):
            return SectionType.VALORES

        return SectionType.UNKNOWN

    def _merge_adjacent_same_type(self, sections: list[DetectedSection]) -> list[DetectedSection]:
        if not sections:
            return []
        merged: list[DetectedSection] = [sections[0]]
        for s in sections[1:]:
            prev = merged[-1]
            if prev.section_type == s.section_type:
                prev.text = prev.text + "\n" + s.text
                if prev.bbox and s.bbox:
                    prev.bbox.x1 = max(prev.bbox.x1, s.bbox.x1)
                    prev.bbox.y1 = max(prev.bbox.y1, s.bbox.y1)
                prev.blocks.extend(s.blocks)
                prev.confidence = round(
                    (prev.confidence + s.confidence) / 2, 4
                )
            else:
                merged.append(s)
        return merged

    def detect_portada(self, text: str) -> bool:
        if not text:
            return False
        normalized = text.strip().lower()

        if len(normalized) > 800:
            return False

        has_header = bool(_RE_AVISO_HEADER.search(text))
        has_finca = bool(_RE_FINCA.search(text))
        has_expediente = bool(_RE_EXPEDIENTE.search(text))
        has_portada_keyword = bool(_RE_PORTADA_INDICATORS.search(text))
        short_text = len(normalized) < 300
        has_remate_keyword = bool(_RE_REMATE_KEYWORDS.search(text))

        if short_text and not has_header and (has_finca or has_expediente):
            return True

        if has_portada_keyword:
            return True

        if short_text and has_remate_keyword and not has_header and len(normalized.split("\n")) <= 3:
            return True

        return False

    def detect_party_section(self, text: str) -> bool:
        return bool(_RE_PARTES.search(text))

    def detect_full_aviso(self, text: str) -> bool:
        has_header = bool(_RE_AVISO_HEADER.search(text))
        has_finca = bool(_RE_FINCA.search(text))
        has_valor = bool(_RE_VALOR.search(text))
        has_partes = bool(_RE_PARTES.search(text))
        long_text = len(text.strip()) > 500

        score = sum([has_header, has_finca, has_valor, has_partes, long_text])
        return score >= 3

    def classify_block(self, block: DetectedBlock) -> tuple[SectionType, float]:
        stype = self._classify_single_block(block)
        confidence = block.confidence if stype != SectionType.UNKNOWN else block.confidence * 0.5
        return stype, confidence
