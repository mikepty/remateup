"""Remate-only notice detector for newspaper pages.

Only detects avisos strictly related to judicial sales/auctions:
- AVISO DE REMATE
- REMATE JUDICIAL
- SUBASTA JUDICIAL

Does NOT detect:
- EDICTO EMPLAZATORIO (general legal notice)
- AVISO (generic)
- EDICTO (generic)
"""

import re

from backend.app.v2.segmenter.models import (
    BoundingBox, DetectedAviso, DetectedBlock, DetectedSection,
)
from backend.app.v2.document.models import SectionType


_REMATE_HEADERS = re.compile(
    r"(?:^|\n)(AVISO\s+DE\s+REMATE|REMATE\s+JUDICIAL|SUBASTA\s+JUDICIAL)",
    re.IGNORECASE,
)

# En Panamá los avisos de remate se publican como "EDICTO EMPLAZATORIO Nº..."
# (sin la palabra "remate" en la cabecera). Cada edicto es un bloque propio:
# se usa como frontera de agrupación para NO mezclar dos avisos en uno, y el
# filtro _is_remate_body decide cuáles grupos son remates reales (los
# edictos de tutela/divorcio/emplazatorios simples quedan fuera).
_EDICTO_EMPLAZATORIO_SPLIT = re.compile(
    r"(?:^|\n)EDICTO\s+EMPLAZATORIO",
    re.IGNORECASE,
)

# Publicidad/cabeceras del periódico que NO son avisos de remate y no deben
# marcar el inicio de un aviso ni agrupar el resto de la columna:
#   - Banner "AVISO DE REMATE IC Publica tus judiciales llamando al
#     204-0000 204-0045 correo: judiciales@laestrella.com.pa ..." (contiene
#     "AVISO DE REMATE" pero es publicidad del periódico).
#   - Cabecera de columna "EDICTO 810" (fondo negro, grande).
#   - Pie/rodapié promocional ("estrellaonline", teléfonos/correos).
_FURNITURE_RE = re.compile(
    r"Publica\s+tus\s+judiciales"
    r"|judiciales@laestrella\.com\.pa"
    r"|204-0000"
    r"|estrellaonline"
    r"|^EDICTO\s+\d+\s*$",
    re.IGNORECASE,
)

_REMATE_BASE = re.compile(
    r"(?:BASE\s+DEL\s+REMATE|BASE\s+PARA\s*EL\s+REMATE|"
    r"SERVIR[ÁA]?\s+DE\s+BASE.{0,80}?REMATE)",
    re.IGNORECASE | re.DOTALL,
)
_REMATE_POSTURA = re.compile(r"POSTURA|POSTOR|PUJA|REPuja", re.IGNORECASE)
_REMATE_PROCEDURE = re.compile(
    r"AVISO\s+DE\s+REMATE|CERTIFICADO\s+DE\s+DEP[ÓO]SITO|"
    r"P[ÚU]BLICA\s+SUBASTA|DILIGENCIA\s+DE\s+REMATE",
    re.IGNORECASE,
)


class NoticeDetector:
    def detect_avisos(self, column_blocks: list) -> list[DetectedAviso]:
        if not column_blocks:
            return []

        grouped = self._group_by_header(column_blocks)
        avisos: list[DetectedAviso] = []

        for group in grouped:
            header_text = self._find_header(group)
            if not header_text and not self._is_remate_body(group):
                continue
            if not header_text:
                header_text = "AVISO DE REMATE"

            group_bbox = self._compute_bbox(group)
            confidence = self._compute_confidence(group)

            sections = [
                DetectedSection(
                    section_type=SectionType.AVISO_COMPLETO,
                    text="\n".join(b.text for b in group),
                    bbox=group_bbox,
                    confidence=confidence,
                )
            ]

            avisos.append(DetectedAviso(
                header_text=header_text,
                sections=sections,
                bbox=group_bbox,
                confidence=confidence,
                blocks=group,
            ))

        return avisos

    def _es_furniture(self, block) -> bool:
        """Bloques que son publicidad/cabeceras del periódico, no contenido
        de aviso: banner "AVISO DE REMATE IC Publica tus judiciales...",
        cabecera de columna "EDICTO 810", rodapié "estrellaonline"."""
        text = getattr(block, "text", "") or ""
        return bool(_FURNITURE_RE.search(text))

    def _find_header(self, blocks: list) -> str:
        for b in blocks:
            if self._es_furniture(b):
                continue
            text = getattr(b, "text", "") or ""
            match = _REMATE_HEADERS.search(text.strip())
            if match:
                return match.group(1)
        return ""

    def _is_remate_body(self, blocks: list) -> bool:
        text = "\n".join((getattr(block, "text", "") or "") for block in blocks if not self._es_furniture(block))
        return bool(
            _REMATE_BASE.search(text)
            and _REMATE_POSTURA.search(text)
            and _REMATE_PROCEDURE.search(text)
        )

    def _group_by_header(self, blocks: list) -> list[list]:
        groups: list[list] = []
        current: list = []

        for b in blocks:
            if self._es_furniture(b):
                continue
            text = getattr(b, "text", "") or ""
            if _REMATE_HEADERS.search(text.strip()) or _EDICTO_EMPLAZATORIO_SPLIT.search(text.strip()):
                if current:
                    groups.append(current)
                current = [b]
            else:
                current.append(b)

        if current:
            groups.append(current)

        return groups

    def _compute_bbox(self, blocks: list):
        xs = []
        ys = []
        x1s = []
        y1s = []
        for b in blocks:
            bbox = getattr(b, "bbox", None)
            if bbox:
                xs.append(bbox.x0)
                ys.append(bbox.y0)
                x1s.append(bbox.x1)
                y1s.append(bbox.y1)
            else:
                xs.append(getattr(b, "x0", 0))
                ys.append(getattr(b, "y0", 0))
                x1s.append(getattr(b, "x1", 0))
                y1s.append(getattr(b, "y1", 0))
        if not xs:
            return BoundingBox(0, 0, 0, 0)
        return BoundingBox(x0=min(xs), y0=min(ys), x1=max(x1s), y1=max(y1s))

    def _compute_confidence(self, blocks: list) -> float:
        confs = []
        for b in blocks:
            c = getattr(b, "confidence", 0.0) or 0.0
            if c > 0:
                confs.append(c)
        return round(sum(confs) / len(confs), 4) if confs else 0.0
