from backend.app.v2.ocr.models import OCRDocument
from backend.app.v2.segmenter.models import (
    SegmentedDocument, SegmentedPage, DetectedAviso, DetectedColumn,
    DetectedBlock, DetectedSection, BoundingBox,
)
from backend.app.v2.segmenter.block_detector import BlockDetector
from backend.app.v2.segmenter.column_detector import ColumnDetector
from backend.app.v2.segmenter.line_detector import LineDetector
from backend.app.v2.segmenter.section_detector import SectionDetector
from backend.app.v2.segmenter.relationship_detector import RelationshipDetector
from backend.app.v2.segmenter.scoring import SegmentationScorer


_REMATE_HEADERS = {
    "aviso de remate", "aviso de remate judicial",
    "edicto emplazatorio", "remate judicial",
    "aviso de venta judicial", "aviso de subasta",
    "aviso", "edicto",
}


class SegmentationEngine:
    def __init__(
        self,
        block_detector: BlockDetector = None,
        line_detector: LineDetector = None,
        column_detector: ColumnDetector = None,
        section_detector: SectionDetector = None,
        relationship_detector: RelationshipDetector = None,
        scorer: SegmentationScorer = None,
    ):
        self._block_detector = block_detector or BlockDetector()
        self._line_detector = line_detector or LineDetector()
        self._column_detector = column_detector or ColumnDetector()
        self._section_detector = section_detector or SectionDetector()
        self._relationship_detector = relationship_detector or RelationshipDetector()
        self._scorer = scorer or SegmentationScorer()
        self._last_sections: list[DetectedSection] = []

    def segment(self, ocr_document: OCRDocument) -> SegmentedDocument:
        pages = self._process_pages(ocr_document)
        doc = SegmentedDocument(pages=pages, raw_ocr_document=ocr_document)
        doc_confidence = self._scorer.score_document(doc)
        for page in doc.pages:
            if page.confidence == 0.0:
                page.confidence = doc_confidence
        return doc

    def _process_pages(self, ocr_document: OCRDocument) -> list[SegmentedPage]:
        pages: list[SegmentedPage] = []
        for ocr_page in ocr_document.pages:
            all_words = []
            for b in ocr_page.blocks:
                all_words.extend(b.words)

            detected_lines = self._line_detector.detect_lines(all_words)
            detected_blocks = self._block_detector.detect(detected_lines, ocr_page.height)
            columns = self._column_detector.assign_blocks(
                detected_blocks, ocr_page.width
            )
            sections = self._section_detector.detect_sections(detected_blocks)
            self._last_sections = sections
            avisos = self._detect_avisos(detected_blocks, sections)
            page_confidence = self._score_page_confidence(avisos, columns)
            page = SegmentedPage(
                page_number=ocr_page.page_number,
                width=ocr_page.width,
                height=ocr_page.height,
                columns=columns,
                avisos=avisos,
                confidence=page_confidence,
            )
            pages.append(page)
        return pages

    def _detect_avisos(
        self,
        blocks: list[DetectedBlock],
        sections: list[DetectedSection],
    ) -> list[DetectedAviso]:
        if not blocks:
            return []

        aviso_groups = self._group_blocks_into_avisos(blocks)
        avisos: list[DetectedAviso] = []

        for group in aviso_groups:
            header_text = self._find_header_text(group)
            group_sections = self._section_detector.detect_sections(group)
            group_bbox = self._compute_group_bbox(group)
            group_confidence = self._compute_group_confidence(group)
            is_portada = self._section_detector.detect_portada(
                "\n".join(b.text for b in group)
            )
            aviso = DetectedAviso(
                header_text=header_text,
                sections=group_sections,
                bbox=group_bbox,
                confidence=group_confidence,
                is_portada_resumen=is_portada,
                blocks=group,
            )
            avisos.append(aviso)

        return avisos

    def _group_blocks_into_avisos(
        self, blocks: list[DetectedBlock]
    ) -> list[list[DetectedBlock]]:
        groups: list[list[DetectedBlock]] = []
        current_group: list[DetectedBlock] = []
        for block in blocks:
            text = block.text.strip().lower()
            if any(text.startswith(h) for h in _REMATE_HEADERS):
                if current_group:
                    groups.append(current_group)
                current_group = [block]
            else:
                current_group.append(block)

        if current_group:
            groups.append(current_group)

        if not groups and blocks:
            groups.append(blocks)

        return groups

    def _find_header_text(self, blocks: list[DetectedBlock]) -> str:
        for block in blocks:
            text = block.text.strip().lower()
            for header in _REMATE_HEADERS:
                if text.startswith(header):
                    return block.text.strip()
        return ""

    def _compute_group_bbox(self, blocks: list[DetectedBlock]) -> BoundingBox:
        xs = [b.bbox.x0 for b in blocks if b.bbox]
        ys = [b.bbox.y0 for b in blocks if b.bbox]
        x1s = [b.bbox.x1 for b in blocks if b.bbox]
        y1s = [b.bbox.y1 for b in blocks if b.bbox]
        if not xs:
            return BoundingBox(0, 0, 0, 0)
        return BoundingBox(
            x0=min(xs), y0=min(ys), x1=max(x1s), y1=max(y1s),
        )

    def _compute_group_confidence(self, blocks: list[DetectedBlock]) -> float:
        if not blocks:
            return 0.0
        return round(
            sum(b.confidence for b in blocks if b.confidence > 0) / len(blocks), 4
        )

    def _score_page_confidence(
        self, avisos: list[DetectedAviso], columns: list[DetectedColumn]
    ) -> float:
        if not avisos:
            return 0.0
        aviso_conf = sum(a.confidence for a in avisos) / len(avisos)
        column_conf = len([c for c in columns if c.blocks]) / max(len(columns), 1)
        return round(aviso_conf * 0.7 + column_conf * 0.3, 4)

    def get_sections(self) -> list[DetectedSection]:
        return self._last_sections
