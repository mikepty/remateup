from dataclasses import dataclass, field
from typing import Any, Optional

from backend.app.v2.document.models import Document, DocumentType, Page


@dataclass
class OCRWord:
    text: str
    confidence: float
    x0: int
    y0: int
    x1: int
    y1: int
    page: int
    break_type: str = ""

    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2

    def center_y(self) -> float:
        return (self.y0 + self.y1) / 2

    def height(self) -> int:
        return self.y1 - self.y0

    def width(self) -> int:
        return self.x1 - self.x0

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "confidence": self.confidence,
            "x0": self.x0, "y0": self.y0,
            "x1": self.x1, "y1": self.y1,
            "page": self.page,
            "break_type": self.break_type,
        }


@dataclass
class OCRBlock:
    text: str
    confidence: float
    block_type: str
    x0: int
    y0: int
    x1: int
    y1: int
    page: int
    words: list[OCRWord] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "confidence": self.confidence,
            "block_type": self.block_type,
            "x0": self.x0, "y0": self.y0,
            "x1": self.x1, "y1": self.y1,
            "page": self.page,
            "words": [w.to_dict() for w in self.words],
        }


@dataclass
class OCRPage:
    page_number: int
    width: int
    height: int
    blocks: list[OCRBlock] = field(default_factory=list)
    text: str = ""

    @property
    def word_count(self) -> int:
        return sum(len(b.words) for b in self.blocks)

    @property
    def average_confidence(self) -> float:
        all_conf = [w.confidence for b in self.blocks for w in b.words if w.confidence > 0]
        return round(sum(all_conf) / len(all_conf), 4) if all_conf else 0.0

    def to_dict(self) -> dict:
        return {
            "page_number": self.page_number,
            "width": self.width,
            "height": self.height,
            "blocks": [b.to_dict() for b in self.blocks],
            "text": self.text[:500],
            "word_count": self.word_count,
            "average_confidence": self.average_confidence,
        }


@dataclass
class OCRDocument:
    pages: list[OCRPage] = field(default_factory=list)
    full_text: str = ""
    raw_response: dict = field(default_factory=dict)

    @property
    def total_pages(self) -> int:
        return len(self.pages)

    @property
    def total_blocks(self) -> int:
        return sum(len(p.blocks) for p in self.pages)

    @property
    def total_words(self) -> int:
        return sum(len(b.words) for p in self.pages for b in p.blocks)

    @property
    def average_confidence(self) -> float:
        all_conf = [w.confidence for p in self.pages for b in p.blocks for w in b.words if w.confidence > 0]
        return round(sum(all_conf) / len(all_conf), 4) if all_conf else 0.0

    def get_all_words(self) -> list[OCRWord]:
        return [w for p in self.pages for b in p.blocks for w in b.words]

    def get_blocks_on_page(self, page: int) -> list[OCRBlock]:
        for p in self.pages:
            if p.page_number == page:
                return p.blocks
        return []

    def get_text_for_page(self, page: int) -> str:
        for p in self.pages:
            if p.page_number == page:
                return p.text
        return ""

    def to_domain_document(self, pais: str, doc_type: str = "unknown") -> Document:
        try:
            document_type = DocumentType(doc_type)
        except ValueError:
            document_type = DocumentType.UNKNOWN
        doc = Document(
            pais=pais,
            document_type=document_type,
            raw_text=self.full_text,
        )
        for op in self.pages:
            page = Page(
                number=op.page_number,
                width=op.width,
                height=op.height,
                text=op.text,
                blocks=[b.to_dict() for b in op.blocks],
            )
            doc.add_page(page)
        return doc

    def to_dict(self) -> dict:
        return {
            "pages": [p.to_dict() for p in self.pages],
            "full_text_length": len(self.full_text),
            "total_pages": self.total_pages,
            "total_blocks": self.total_blocks,
            "total_words": self.total_words,
            "average_confidence": self.average_confidence,
        }
