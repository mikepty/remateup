"""FASE 4.4 ??? Newspaper Page Reconstruction (Stitching)

Merges top+bottom OCR pages into a single stitched page while preserving:
- bounding boxes (Y-adjusted for bottom fragment)
- X coordinates (unchanged)
- reading order (top blocks first, then bottom blocks)
- column structure
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from backend.app.v2.ocr.models import OCRPage, OCRBlock, OCRWord
from backend.app.v2.segmenter.models import BoundingBox


@dataclass
class FragmentMapping:
    page_number: int
    top_page_index: int = 0
    bottom_page_index: int = 1
    top_height: int = 0
    bottom_height: int = 0
    y_offset: int = 0


@dataclass
class StitchedBlock:
    text: str = ""
    x0: int = 0
    y0: int = 0
    x1: int = 0
    y1: int = 0
    words: list[OCRWord] = field(default_factory=list)
    confidence: float = 0.0
    block_type: str = "text"
    source_position: str = ""
    original_block_index: int = 0
    column_index: int = -1

    @property
    def bbox(self) -> BoundingBox:
        return BoundingBox(x0=self.x0, y0=self.y0, x1=self.x1, y1=self.y1)

    def to_ocr_block(self, page: int) -> OCRBlock:
        return OCRBlock(
            text=self.text, confidence=self.confidence, block_type=self.block_type,
            x0=self.x0, y0=self.y0, x1=self.x1, y1=self.y1, page=page,
            words=list(self.words),
        )


@dataclass
class StitchedPage:
    page_number: int = 0
    width: int = 0
    height: int = 0
    blocks: list[StitchedBlock] = field(default_factory=list)
    fragment_mapping: Optional[FragmentMapping] = None

    @property
    def total_blocks(self) -> int:
        return len(self.blocks)

    @property
    def top_blocks(self) -> list[StitchedBlock]:
        return [b for b in self.blocks if b.source_position == "top"]

    @property
    def bottom_blocks(self) -> list[StitchedBlock]:
        return [b for b in self.blocks if b.source_position == "bottom"]

    @property
    def is_partial(self) -> bool:
        fm = self.fragment_mapping
        if fm is None:
            return False
        return fm.top_height == 0 or fm.bottom_height == 0

    @property
    def missing_side(self) -> str:
        fm = self.fragment_mapping
        if fm is None:
            return ""
        if fm.top_height == 0:
            return "top"
        if fm.bottom_height == 0:
            return "bottom"
        return ""

    @property
    def full_text(self) -> str:
        return "\n".join(b.text for b in self.blocks)

    def to_ocr_page(self) -> OCRPage:
        return OCRPage(
            page_number=self.page_number,
            width=self.width,
            height=self.height,
            blocks=[b.to_ocr_block(self.page_number) for b in self.blocks],
            text=self.full_text,
        )

    def to_dict(self) -> dict:
        return {
            "page_number": self.page_number,
            "width": self.width,
            "height": self.height,
            "total_blocks": self.total_blocks,
            "top_blocks": len(self.top_blocks),
            "bottom_blocks": len(self.bottom_blocks),
            "full_text_preview": self.full_text[:300],
        }


class PageStitcher:
    DENSE_BLOCK_MIN_WORDS = 200
    DENSE_BLOCK_WIDTH_RATIO = 0.85
    NEWSPAPER_COLUMNS = 4
    SEGMENT_GAP_MULTIPLIER = 4.0
    MIN_SEGMENT_WORDS = 10
    HEADER_RE = re.compile(r"AVISO\s+DE\s+REMATE|REMATE\s+JUDICIAL|SUBASTA\s+JUDICIAL", re.IGNORECASE)
    REMAINDER_RE = re.compile(r"RENTA|AVALUO DE LA EDIF|EDIFICIO|AVALUO\s+DE\s+LA\s+EDIFI", re.IGNORECASE)

    def stitch(
        self, top_page: OCRPage, bottom_page: OCRPage, page_number: int = 1
    ) -> StitchedPage:
        y_offset = top_page.height
        mapping = FragmentMapping(
            page_number=page_number,
            top_page_index=top_page.page_number,
            bottom_page_index=bottom_page.page_number,
            top_height=top_page.height,
            bottom_height=bottom_page.height,
            y_offset=y_offset,
        )

        def _shift_word(w: OCRWord) -> OCRWord:
            return OCRWord(
                text=w.text, confidence=w.confidence, x0=w.x0, y0=w.y0 + y_offset,
                x1=w.x1, y1=w.y1 + y_offset, page=w.page, break_type=w.break_type,
            )

        top_blocks = [
            StitchedBlock(
                text=block.text,
                x0=block.x0, y0=block.y0, x1=block.x1, y1=block.y1,
                words=list(block.words),
                confidence=block.confidence,
                block_type=block.block_type,
                source_position="top",
                original_block_index=bi,
                column_index=bi,
            )
            for bi, block in enumerate(top_page.blocks)
        ]
        bottom_blocks = [
            StitchedBlock(
                text=block.text,
                x0=block.x0,
                y0=block.y0 + y_offset,
                x1=block.x1,
                y1=block.y1 + y_offset,
                words=[_shift_word(w) for w in block.words],
                confidence=block.confidence,
                block_type=block.block_type,
                source_position="bottom",
                original_block_index=bi,
                column_index=bi,
            )
            for bi, block in enumerate(bottom_page.blocks)
        ]

        stitched_blocks = top_blocks + bottom_blocks

        # Si las páginas vienen colapsadas en bloques densos (columnas del
        # periódico unidas), reconstruir las cuatro columnas.
        page_width = max(top_page.width, bottom_page.width)
        dense_reconstruction = self._reconstruct_dense_columns(stitched_blocks, page_width)
        if dense_reconstruction:
            stitched_blocks = dense_reconstruction
        else:
            stitched_blocks.sort(key=lambda block: (block.y0, block.column_index))

        return StitchedPage(
            page_number=page_number,
            width=page_width,
            height=top_page.height + bottom_page.height,
            blocks=stitched_blocks,
            fragment_mapping=mapping,
        )

    def _reconstruct_dense_columns(
        self, blocks: list[StitchedBlock], page_width: int
    ) -> list[StitchedBlock]:
        """Recupera el orden de lectura cuando las páginas densas colapsan
        varias columnas del periódico en uno o más bloques que ocupan casi
        todo el ancho. En ese caso el texto del bloque viene intercalado por
        renglón, pero las coordenadas de palabra siguen utilizables, así que
        reconstruimos las cuatro columnas y aplicamos el merge de segmentos."""
        if page_width <= 0:
            return []
        is_dense = any(
            len(block.words) >= self.DENSE_BLOCK_MIN_WORDS
            and block.x1 - block.x0 >= page_width * self.DENSE_BLOCK_WIDTH_RATIO
            for block in blocks
        )
        if not is_dense:
            return []

        words = [word for block in blocks for word in block.words if word.text.strip()]
        if len(words) < self.DENSE_BLOCK_MIN_WORDS:
            return []

        min_x = min(word.x0 for word in words)
        max_x = max(word.x1 for word in words)
        content_width = max_x - min_x
        if content_width <= 0:
            return []

        band_width = content_width / self.NEWSPAPER_COLUMNS
        bands: list[list[OCRWord]] = [[] for _ in range(self.NEWSPAPER_COLUMNS)]
        for word in words:
            center_x = (word.x0 + word.x1) / 2
            index = int((center_x - min_x) / band_width)
            index = max(0, min(self.NEWSPAPER_COLUMNS - 1, index))
            bands[index].append(word)

        column_blocks: list[StitchedBlock] = []
        for index, band_words in enumerate(bands):
            if not band_words:
                continue
            segments = self._split_band_into_segments(band_words)
            for seg_words in segments:
                if not seg_words:
                    continue
                text = self._join_column_words(seg_words)
                column_blocks.append(StitchedBlock(
                    text=text,
                    x0=int(min_x + index * band_width),
                    y0=min(word.y0 for word in band_words),
                    x1=int(min_x + (index + 1) * band_width),
                    y1=max(word.y1 for word in band_words),
                    words=seg_words,
                    confidence=sum(word.confidence for word in seg_words) / len(seg_words),
                    source_position="top",
                    original_block_index=index,
                    column_index=index,
                ))
        if column_blocks:
            column_blocks.sort(key=lambda block: (block.y0, block.column_index))
            return column_blocks
        return []

    def _is_header_line(self, words_line: list[OCRWord]) -> bool:
        text = self._join_column_words(words_line).upper()
        return bool(self.HEADER_RE.search(text))

    def _join_column_words(self, words: list[OCRWord]) -> str:
        heights = [max(1, w.y1 - w.y0) for w in words] if words else [1]
        heights.sort()
        median_height = heights[len(heights) // 2] if heights else 1
        lines: list[list[OCRWord]] = []
        current: list[OCRWord] = []
        line_y = 0.0
        for word in words:
            if current and word.y0 - line_y > median_height * 0.6:
                lines.append(current)
                current = []
            if not current:
                line_y = word.y0
            current.append(word)
        if current:
            lines.append(current)

        output: list[str] = []
        for line in lines:
            line.sort(key=lambda word: word.x0)
            parts: list[str] = []
            for word in line:
                text = word.text[:-1] if word.break_type == "HYPHEN" and word.text.endswith("-") else word.text
                parts.append(text)
                if word.break_type != "HYPHEN":
                    parts.append(" ")
            output.append("".join(parts).strip())
        return "\n".join(output)

    def _classify_span(self, words: list[OCRWord]) -> tuple[bool, bool]:
        text = self._join_column_words(words).upper()
        has_header = bool(self.HEADER_RE.search(text))
        has_remainder = bool(self.REMAINDER_RE.search(text))
        return has_header, has_remainder

    def _split_band_into_segments(self, band_words: list[OCRWord]) -> list[list[OCRWord]]:
        """Dentro de una banda x fija, divide las palabras en segmentos
        (avisos) cortando en las grietas horizontales grandes: un salto que
        deje un espacio vertical de >4× la altura mediana indica cambio de
        aviso. Luego reúne los fragmentos huérfanos que pertenecen al mismo
        aviso, sin unir el cuerpo del inmueble/edificio (RENTA/AVALUO) al
        remate anterior."""
        sorted_words = sorted(band_words, key=lambda word: (word.y0, word.x0))
        if not sorted_words:
            return []
        heights = [max(1, w.y1 - w.y0) for w in sorted_words]
        heights.sort()
        median_height = heights[len(heights) // 2] if heights else 1
        split_threshold = median_height * self.SEGMENT_GAP_MULTIPLIER

        spans: list[list[OCRWord]] = []
        current: list[OCRWord] = []
        for word in sorted_words:
            if current and word.y0 - current[-1].y1 > split_threshold:
                spans.append(current)
                current = []
            current.append(word)
        if current:
            spans.append(current)

        if len(spans) <= 1:
            return [s for s in spans if len(s) >= self.MIN_SEGMENT_WORDS]

        band_top = min(w.y0 for w in band_words)
        band_bottom = max(w.y1 for w in band_words)
        band_height = max(1, band_bottom - band_top)

        merged: list[list[OCRWord]] = []
        for span in spans:
            if len(span) < self.MIN_SEGMENT_WORDS:
                if merged:
                    merged[-1].extend(span)
                continue
            if merged:
                prev = merged[-1]
                prev_has_header, prev_has_remainder = self._classify_span(prev)
                span_has_header, span_has_remainder = self._classify_span(span)
                prev_bottom = max(w.y1 for w in prev)
                gap = span[0].y0 - prev_bottom
                span_text_start = " ".join(w.text.upper() for w in span[:8])
                if span_has_header and prev_has_header:
                    merged.append(span)
                elif (not span_has_header and not span_has_remainder
                        and gap <= band_height * 0.5):
                    prev.extend(span)
                elif (span_has_header and not prev_has_header
                        and not prev_has_remainder and gap <= band_height * 0.5
                        and not self.HEADER_RE.search(span_text_start.strip())):
                    prev.extend(span)
                elif (span_has_remainder and gap <= band_height * 0.5):
                    prev.extend(span)
                else:
                    merged.append(span)
            else:
                merged.append(span)
        return [s for s in merged if len(s) >= self.MIN_SEGMENT_WORDS]

    def stitch_ocr_pages(
        self, ocr_pages: list[OCRPage], page_count: int
    ) -> list[StitchedPage]:
        result: list[StitchedPage] = []
        for i in range(page_count):
            top_idx = i * 2
            bottom_idx = i * 2 + 1
            if top_idx >= len(ocr_pages):
                break
            top_page = ocr_pages[top_idx]
            if bottom_idx < len(ocr_pages):
                bottom_page = ocr_pages[bottom_idx]
            else:
                bottom_page = OCRPage(page_number=0, width=0, height=0)
            result.append(self.stitch(top_page, bottom_page, page_number=i + 1))
        return result
