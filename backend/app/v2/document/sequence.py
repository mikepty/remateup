import re
from pathlib import Path
from typing import Optional

from backend.app.v2.document.models import (
    ImageFragment, DocumentPage, SourceDocument, SourceType,
)

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}
_PDF_EXTENSION = ".pdf"

_POSITION_KEYWORDS = {
    "top": ["superior", "upper", "top", "sup", "arriba"],
    "bottom": ["inferior", "lower", "bottom", "inf", "abajo"],
}


class SequenceDetector:
    def detect(
        self, file_paths: list[str], country: str = ""
    ) -> Optional[SourceDocument]:
        if not file_paths:
            return None
        if country.upper() == "PA" or country.upper() == "PANAMA":
            return self._detect_panama(file_paths)
        elif country.upper() == "CO" or country.upper() == "COLOMBIA":
            return self._detect_colombia(file_paths)
        else:
            return self._detect_auto(file_paths)

    def _detect_panama(self, file_paths: list[str]) -> SourceDocument:
        pages: list[DocumentPage] = []
        fragments = self._categorize_by_position(file_paths)
        has_position_keywords = any(f.page_position != "full" for f in fragments)

        if has_position_keywords:
            top_fragments = [f for f in fragments if f.page_position == "top"]
            bottom_fragments = [f for f in fragments if f.page_position == "bottom"]
            full_fragments = [f for f in fragments if f.page_position == "full"]

            page_num = 1
            for ff in full_fragments:
                ff.page_number = page_num
                page = DocumentPage(page_number=page_num, fragments=[ff], page_type="newspaper")
                pages.append(page)
                page_num += 1

            for i in range(max(len(top_fragments), len(bottom_fragments))):
                page_fragments: list[ImageFragment] = []
                if i < len(top_fragments):
                    top_fragments[i].page_number = page_num
                    page_fragments.append(top_fragments[i])
                if i < len(bottom_fragments):
                    bottom_fragments[i].page_number = page_num
                    page_fragments.append(bottom_fragments[i])
                if page_fragments:
                    pages.append(DocumentPage(page_number=page_num, fragments=page_fragments, page_type="newspaper"))
                    page_num += 1
        else:
            # No position keywords → pair by upload order: odd=top, even=bottom
            page_num = 1
            for i in range(0, len(file_paths), 2):
                top = ImageFragment(path=file_paths[i], page_position="top", page_number=page_num)
                frags = [top]
                if i + 1 < len(file_paths):
                    bottom = ImageFragment(path=file_paths[i + 1], page_position="bottom", page_number=page_num)
                    frags.append(bottom)
                pages.append(DocumentPage(page_number=page_num, fragments=frags, page_type="newspaper"))
                page_num += 1

        return SourceDocument(
            source_type=SourceType.PANAMA_NEWSPAPER,
            file_paths=file_paths,
            pages=pages,
            metadata={"country": "PA", "detected_count": len(file_paths)},
        )

    def _detect_colombia(self, file_paths: list[str]) -> SourceDocument:
        pages: list[DocumentPage] = []
        for i, fp in enumerate(file_paths, 1):
            ext = Path(fp).suffix.lower()
            fragments: list[ImageFragment] = []
            if ext == ".pdf":
                from backend.app.v2.document.assembly import PDFAnalyzer
                pdf_type = PDFAnalyzer().analyze(fp)
                fragments.append(ImageFragment(
                    path=fp, page_position="full", page_number=i,
                ))
                page = DocumentPage(
                    page_number=i, fragments=fragments,
                    page_type=pdf_type,
                )
            else:
                fragments.append(ImageFragment(
                    path=fp, page_position="full", page_number=i,
                ))
                page = DocumentPage(
                    page_number=i, fragments=fragments, page_type="image",
                )
            pages.append(page)

        st = self._detect_source_type(pages)
        return SourceDocument(
            source_type=st,
            file_paths=file_paths,
            pages=pages,
            metadata={"country": "CO", "detected_count": len(file_paths)},
        )

    def _detect_auto(self, file_paths: list[str]) -> SourceDocument:
        pdfs = [f for f in file_paths if Path(f).suffix.lower() == ".pdf"]
        images = [f for f in file_paths if Path(f).suffix.lower() in _IMAGE_EXTENSIONS]
        if len(pdfs) == 1 and not images:
            from backend.app.v2.document.assembly import PDFAnalyzer
            pdf_type = PDFAnalyzer().analyze(pdfs[0])
            page = DocumentPage(
                page_number=1,
                fragments=[ImageFragment(path=pdfs[0], page_position="full", page_number=1)],
                page_type=pdf_type,
            )
            st = SourceType.PDF_MIXED if pdf_type == "pdf_mixed" else (
                SourceType.COLOMBIA_PDF_TEXT if pdf_type == "pdf_text"
                else SourceType.COLOMBIA_PDF_SCANNED
            )
            return SourceDocument(
                source_type=st,
                file_paths=file_paths,
                pages=[page],
                metadata={"detected_count": len(file_paths)},
            )
        return self._detect_panama(file_paths)

    def _categorize_by_position(self, file_paths: list[str]) -> list[ImageFragment]:
        fragments: list[ImageFragment] = []
        for fp in file_paths:
            name = Path(fp).stem.lower()
            pos = self._detect_position(name)
            fragments.append(ImageFragment(
                path=fp, page_position=pos,
            ))
        return fragments

    def _detect_position(self, filename_stem: str) -> str:
        parts = re.split(r"[^a-z0-9]", filename_stem.lower())
        for part in parts:
            for pos, keywords in _POSITION_KEYWORDS.items():
                if part in keywords:
                    return pos
        return "full"

    def _detect_source_type(self, pages: list[DocumentPage]) -> SourceType:
        types = set(p.page_type for p in pages)
        if "pdf_text" in types and "pdf_scanned" in types:
            return SourceType.PDF_MIXED
        if "pdf_text" in types:
            return SourceType.COLOMBIA_PDF_TEXT
        if "pdf_scanned" in types:
            return SourceType.COLOMBIA_PDF_SCANNED
        return SourceType.IMAGE
