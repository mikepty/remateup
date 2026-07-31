"""FASE 4.4 — Newspaper Page Reconstruction (Stitching)

Merges top+bottom OCR pages into a single stitched page while preserving:
- bounding boxes (Y-adjusted for bottom fragment)
- X coordinates (unchanged)
- reading order (top blocks first, then bottom blocks)
- column structure
"""

from dataclasses import dataclass, field
from typing import Optional

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

        stitched_blocks: list[StitchedBlock] = []

        for bi, block in enumerate(top_page.blocks):
            sb = StitchedBlock(
                text=block.text,
                x0=block.x0, y0=block.y0, x1=block.x1, y1=block.y1,
                words=list(block.words),
                confidence=block.confidence,
                block_type=block.block_type,
                source_position="top",
                original_block_index=bi,
            )
            stitched_blocks.append(sb)

        for bi, block in enumerate(bottom_page.blocks):
            sb = StitchedBlock(
                text=block.text,
                x0=block.x0,
                y0=block.y0 + y_offset,
                x1=block.x1,
                y1=block.y1 + y_offset,
                words=list(block.words),
                confidence=block.confidence,
                block_type=block.block_type,
                source_position="bottom",
                original_block_index=bi,
            )
            stitched_blocks.append(sb)

        return StitchedPage(
            page_number=page_number,
            width=max(top_page.width, bottom_page.width),
            height=top_page.height + bottom_page.height,
            blocks=stitched_blocks,
            fragment_mapping=mapping,
        )

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
