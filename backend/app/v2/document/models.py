from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class DocumentType(str, Enum):
    NEWSPAPER_PAGE = "newspaper_page"
    PDF_TABULAR = "pdf_tabular"
    PDF_SCANNED = "pdf_scanned"
    INDIVIDUAL_IMAGE = "individual_image"
    UNKNOWN = "unknown"


class SectionType(str, Enum):
    HEADER = "header"
    PORTADA = "portada"
    PORTADA_RESUMEN = "portada_resumen"
    AVISO_COMPLETO = "aviso_completo"
    CONTINUACION_AVISO = "continuacion_aviso"
    INDICE = "indice"
    PUBLICIDAD = "publicidad"
    PROPIETARIO = "propietario"
    UBICACION = "ubicacion"
    VALORES = "valores"
    DESCRIPCION = "descripcion"
    PARTIES = "parties"
    FOOTER = "footer"
    UNKNOWN = "unknown"


@dataclass
class Page:
    number: int
    width: int = 0
    height: int = 0
    text: str = ""
    blocks: list[dict] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)

    def area(self) -> int:
        return self.width * self.height

    def is_empty(self) -> bool:
        return len(self.text.strip()) == 0


@dataclass
class Section:
    section_type: SectionType
    text: str
    page: int = 0
    bounding_box: Optional[dict] = None
    children: list[dict] = field(default_factory=list)
    confidence: float = 0.0
    raw_text: str = ""

    def to_dict(self) -> dict:
        return {
            "section_type": self.section_type.value,
            "text": self.text,
            "page": self.page,
            "confidence": self.confidence,
            "bounding_box": self.bounding_box,
            "raw_text": self.raw_text,
        }


@dataclass
class Field:
    name: str
    value: Any = None
    raw_value: Any = None
    confidence: float = 0.0
    state: str = "not_found"
    evidence: list[dict] = field(default_factory=list)
    section: Optional[str] = None
    page: int = 0
    normalized_value: Any = None
    transformations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "raw_value": self.raw_value,
            "confidence": self.confidence,
            "state": self.state,
            "section": self.section,
            "page": self.page,
            "normalized_value": self.normalized_value,
            "evidence_count": len(self.evidence),
        }

    def is_empty(self) -> bool:
        return self.value is None or str(self.value).strip() == ""

    def set_found(self, value: Any, confidence: float = 1.0):
        self.value = value
        self.raw_value = value
        self.confidence = confidence
        self.state = "found"

    def set_not_found(self):
        self.value = None
        self.confidence = 0.0
        self.state = "not_found"

    def set_requires_review(self, value: Any, confidence: float = 0.0):
        self.value = value
        self.confidence = confidence
        self.state = "requires_review"

    def add_evidence(self, evidence: dict):
        self.evidence.append(evidence)

    def add_transformation(self, transformation: str):
        self.transformations.append(transformation)


@dataclass
class Document:
    id: Optional[int] = None
    external_id: Optional[int] = None
    document_type: DocumentType = DocumentType.UNKNOWN
    pais: str = ""
    pages: list[Page] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    fields: dict[str, Field] = field(default_factory=dict)
    raw_text: str = ""
    source_paths: list[str] = field(default_factory=list)
    status: str = "pending"
    confidence: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @property
    def total_pages(self) -> int:
        return len(self.pages)

    @property
    def total_fields(self) -> int:
        return len(self.fields)

    @property
    def found_fields(self) -> list[str]:
        return [n for n, f in self.fields.items() if f.state == "found"]

    @property
    def missing_fields(self) -> list[str]:
        return [n for n, f in self.fields.items() if f.state == "not_found"]

    @property
    def review_fields(self) -> list[str]:
        return [n for n, f in self.fields.items() if f.state == "requires_review"]

    @property
    def average_field_confidence(self) -> float:
        if not self.fields:
            return 0.0
        confs = [f.confidence for f in self.fields.values() if f.confidence > 0]
        return round(sum(confs) / len(confs), 4) if confs else 0.0

    def add_field(self, name: str, value: Any = None, confidence: float = 0.0,
                  state: str = "not_found", raw_value: Any = None):
        self.fields[name] = Field(
            name=name, value=value, raw_value=raw_value or value,
            confidence=confidence, state=state,
        )

    def get_field(self, name: str) -> Optional[Field]:
        return self.fields.get(name)

    def has_field(self, name: str) -> bool:
        f = self.fields.get(name)
        return f is not None and not f.is_empty()

    def add_page(self, page: Page):
        self.pages.append(page)

    def add_section(self, section: Section):
        self.sections.append(section)

    def merge_field(self, name: str, field: Field):
        if name in self.fields:
            existing = self.fields[name]
            if field.confidence > existing.confidence:
                existing.value = field.value
                existing.confidence = field.confidence
                existing.state = field.state
            if field.evidence:
                existing.evidence.extend(field.evidence)
        else:
            self.fields[name] = field

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "document_type": self.document_type.value,
            "pais": self.pais,
            "pages": len(self.pages),
            "sections": [s.to_dict() for s in self.sections],
            "fields": {n: f.to_dict() for n, f in self.fields.items()},
            "raw_text_length": len(self.raw_text),
            "confidence": self.confidence,
            "status": self.status,
            "found_fields": len(self.found_fields),
            "missing_fields": len(self.missing_fields),
            "review_fields": len(self.review_fields),
        }


@dataclass
class ImageFragment:
    path: str = ""
    page_position: str = ""  # "top", "bottom", "full"
    page_number: int = 0
    width: int = 0
    height: int = 0
    ocr_processed: bool = False

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "page_position": self.page_position,
            "page_number": self.page_number,
        }


@dataclass
class DocumentPage:
    page_number: int = 0
    fragments: list[ImageFragment] = field(default_factory=list)
    width: int = 0
    height: int = 0
    page_type: str = ""  # "newspaper", "pdf_text", "pdf_scanned", "image"

    @property
    def fragment_count(self) -> int:
        return len(self.fragments)

    @property
    def is_complete(self) -> bool:
        return self.fragment_count > 0

    def to_dict(self) -> dict:
        return {
            "page_number": self.page_number,
            "fragment_count": self.fragment_count,
            "page_type": self.page_type,
        }


class SourceType(str, Enum):
    PANAMA_NEWSPAPER = "panama_newspaper"
    COLOMBIA_PDF_TEXT = "colombia_pdf_text"
    COLOMBIA_PDF_SCANNED = "colombia_pdf_scanned"
    PDF_MIXED = "pdf_mixed"
    IMAGE = "image"
    UNKNOWN = "unknown"


@dataclass
class SourceDocument:
    source_type: SourceType = SourceType.UNKNOWN
    file_paths: list[str] = field(default_factory=list)
    pages: list[DocumentPage] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def total_pages(self) -> int:
        return len(self.pages)

    @property
    def total_files(self) -> int:
        return len(self.file_paths)

    def to_dict(self) -> dict:
        return {
            "source_type": self.source_type.value,
            "total_files": self.total_files,
            "total_pages": self.total_pages,
            "metadata": self.metadata,
        }


PARSER_ALLOWED_STATES = ["found", "not_found", "requires_review"]
EXTRACTION_FIELDS = [
    "expediente", "demandante", "demandado", "base", "fianza_porcentaje",
    "minimo_porcentaje", "finca_matr", "codigo_ubicacion_prensa",
    "fecha", "hora", "lugar", "proceso", "categoria", "provincia",
    "descripcion", "descripcion_completa", "prevista", "plano",
    "lote_casa", "superficie", "periodico", "fecha_prensa",
    "pagina_prensa", "codigo_prensa", "email_observaciones",
    "codigo_fuente", "codigo_ubicacion",
]
