from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from backend.app.v2.document.models import SectionType
from backend.app.v2.ocr.models import OCRWord, OCRBlock


@dataclass
class AvisoFragment:
    source_image: str = ""
    page_number: int = 0
    position: str = ""  # "top" or "bottom"
    blocks: list[DetectedBlock] = field(default_factory=list)
    bbox: Optional[BoundingBox] = None
    confidence: float = 0.0
    column_index: int = 0
    ends_incomplete: bool = False
    ends_with_hyphen: bool = False
    has_header: bool = False
    trailing_text: str = ""
    leading_text: str = ""

    def to_dict(self) -> dict:
        return {
            "source_image": self.source_image,
            "page_number": self.page_number,
            "position": self.position,
            "bbox": self.bbox.to_dict() if self.bbox else None,
            "confidence": self.confidence,
            "has_header": self.has_header,
            "ends_incomplete": self.ends_incomplete,
        }


@dataclass
class CompleteAviso:
    fragments: list[AvisoFragment] = field(default_factory=list)
    text: str = ""
    bbox: Optional[BoundingBox] = None
    confidence: float = 0.0
    aviso_type: str = "unknown"
    continuity_signals: list[str] = field(default_factory=list)

    @property
    def is_reconstructed(self) -> bool:
        return len(self.fragments) > 1

    @property
    def fragment_count(self) -> int:
        return len(self.fragments)

    @property
    def source_images(self) -> list[str]:
        return [f.source_image for f in self.fragments if f.source_image]

    def to_dict(self) -> dict:
        return {
            "text_preview": self.text[:300],
            "fragment_count": self.fragment_count,
            "is_reconstructed": self.is_reconstructed,
            "aviso_type": self.aviso_type,
            "confidence": self.confidence,
            "continuity_signals": self.continuity_signals,
        }


@dataclass
class BoundingBox:
    x0: int
    y0: int
    x1: int
    y1: int

    def area(self) -> int:
        return max(0, self.x1 - self.x0) * max(0, self.y1 - self.y0)

    def width(self) -> int:
        return max(0, self.x1 - self.x0)

    def height(self) -> int:
        return max(0, self.y1 - self.y0)

    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2.0

    def center_y(self) -> float:
        return (self.y0 + self.y1) / 2.0

    def intersects(self, other: "BoundingBox", tolerance: int = 0) -> bool:
        return (
            self.x1 + tolerance > other.x0
            and other.x1 + tolerance > self.x0
            and self.y1 + tolerance > other.y0
            and other.y1 + tolerance > self.y0
        )

    def to_dict(self) -> dict:
        return {"x0": self.x0, "y0": self.y0, "x1": self.x1, "y1": self.y1}


@dataclass
class DetectedLine:
    words: list[OCRWord] = field(default_factory=list)
    text: str = ""
    bbox: Optional[BoundingBox] = None
    confidence: float = 0.0
    y_center: float = 0.0

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "bbox": self.bbox.to_dict() if self.bbox else None,
            "confidence": self.confidence,
        }


@dataclass
class DetectedBlock:
    lines: list[DetectedLine] = field(default_factory=list)
    text: str = ""
    bbox: Optional[BoundingBox] = None
    confidence: float = 0.0
    block_type: str = "text"
    source_ocr_blocks: list[OCRBlock] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "text": self.text[:200],
            "bbox": self.bbox.to_dict() if self.bbox else None,
            "confidence": self.confidence,
            "block_type": self.block_type,
        }


@dataclass
class DetectedColumn:
    index: int = 0
    bbox: Optional[BoundingBox] = None
    blocks: list[DetectedBlock] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(b.text for b in self.blocks)

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "bbox": self.bbox.to_dict() if self.bbox else None,
            "block_count": len(self.blocks),
            "text_preview": self.text[:200],
        }


@dataclass
class DetectedSection:
    section_type: SectionType = SectionType.UNKNOWN
    text: str = ""
    bbox: Optional[BoundingBox] = None
    confidence: float = 0.0
    blocks: list[DetectedBlock] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "section_type": self.section_type.value,
            "text_preview": self.text[:200],
            "bbox": self.bbox.to_dict() if self.bbox else None,
            "confidence": self.confidence,
        }


@dataclass
class DetectedAviso:
    header_text: str = ""
    sections: list[DetectedSection] = field(default_factory=list)
    bbox: Optional[BoundingBox] = None
    confidence: float = 0.0
    is_portada_resumen: bool = False
    blocks: list[DetectedBlock] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        texts = [self.header_text] if self.header_text else []
        texts.extend(s.text for s in self.sections)
        return "\n".join(texts)

    def to_dict(self) -> dict:
        return {
            "header_text": self.header_text[:200],
            "section_count": len(self.sections),
            "bbox": self.bbox.to_dict() if self.bbox else None,
            "confidence": self.confidence,
            "is_portada_resumen": self.is_portada_resumen,
        }


@dataclass
class SegmentedPage:
    page_number: int = 0
    width: int = 0
    height: int = 0
    columns: list[DetectedColumn] = field(default_factory=list)
    avisos: list[DetectedAviso] = field(default_factory=list)
    confidence: float = 0.0

    @property
    def total_avisos(self) -> int:
        return len(self.avisos)

    def to_dict(self) -> dict:
        return {
            "page_number": self.page_number,
            "total_avisos": self.total_avisos,
            "confidence": self.confidence,
        }


@dataclass
class SegmentedDocument:
    pages: list[SegmentedPage] = field(default_factory=list)
    raw_ocr_document: Optional[object] = None

    @property
    def total_avisos(self) -> int:
        return sum(p.total_avisos for p in self.pages)

    @property
    def total_pages(self) -> int:
        return len(self.pages)

    @property
    def average_confidence(self) -> float:
        confs = [p.confidence for p in self.pages if p.confidence > 0]
        return round(sum(confs) / len(confs), 4) if confs else 0.0

    @property
    def full_text(self) -> str:
        parts = []
        for p in self.pages:
            for a in p.avisos:
                parts.append(a.full_text)
        return "\n\n".join(parts)

    def get_avisos_by_page(self, page: int) -> list[DetectedAviso]:
        for p in self.pages:
            if p.page_number == page:
                return p.avisos
        return []

    def to_dict(self) -> dict:
        return {
            "total_pages": self.total_pages,
            "total_avisos": self.total_avisos,
            "average_confidence": self.average_confidence,
            "pages": [p.to_dict() for p in self.pages],
        }
