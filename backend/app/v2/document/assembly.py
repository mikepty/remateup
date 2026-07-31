from pathlib import Path
from typing import Optional

from backend.app.v2.document.models import SourceDocument, SourceType
from backend.app.v2.document.sequence import SequenceDetector


_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}


class PDFAnalyzer:
    PDF_TEXT_THRESHOLD_CHARS = 100

    def analyze(self, pdf_path: str) -> str:
        path = Path(pdf_path)
        if not path.exists():
            return "unknown"
        try:
            import fitz
        except ImportError:
            return "unknown"
        try:
            doc = fitz.open(pdf_path)
        except Exception:
            return "unknown"
        for page_num in range(min(len(doc), 5)):
            text = doc[page_num].get_text().strip()
            if text:
                return "pdf_text"
        doc.close()
        return "pdf_scanned"


class DocumentAssembly:
    def __init__(self, pdf_analyzer: Optional[PDFAnalyzer] = None):
        self._sequence_detector = SequenceDetector()
        self._pdf_analyzer = pdf_analyzer or PDFAnalyzer()

    @property
    def sequence_detector(self) -> SequenceDetector:
        return self._sequence_detector

    @property
    def pdf_analyzer(self) -> PDFAnalyzer:
        return self._pdf_analyzer

    def assemble(
        self,
        file_paths: list[str],
        country: str = "",
        source_type: Optional[str] = None,
    ) -> SourceDocument:
        if not file_paths:
            return SourceDocument(source_type=SourceType.UNKNOWN)

        self._validate_paths(file_paths)
        source = self._sequence_detector.detect(file_paths, country)
        if source is None:
            return SourceDocument(
                source_type=SourceType.UNKNOWN,
                file_paths=file_paths,
            )
        if source_type:
            try:
                source.source_type = SourceType(source_type)
            except ValueError:
                pass
        return source

    def _validate_paths(self, paths: list[str]):
        for p in paths:
            path = Path(p)
            if not path.exists():
                raise FileNotFoundError(f"File not found: {p}")
            if path.suffix.lower() not in _IMAGE_EXTENSIONS and path.suffix.lower() != ".pdf":
                raise ValueError(f"Unsupported file type: {p}")

    def is_panama_newspaper(self, source: SourceDocument) -> bool:
        return source.source_type == SourceType.PANAMA_NEWSPAPER

    def is_colombia_pdf(self, source: SourceDocument) -> bool:
        return source.source_type in (
            SourceType.COLOMBIA_PDF_TEXT,
            SourceType.COLOMBIA_PDF_SCANNED,
            SourceType.PDF_MIXED,
        )
