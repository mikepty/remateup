"""Newspaper Layout Segmentation — FASE 4.5

Transforms a stitched newspaper page into detected remate avisos:

  StitchedPage
      ↓
  ColumnAnalyzer → columns
      ↓
  NoticeDetector → avisos per column
      ↓
  DetectedAviso[]
"""

from backend.app.v2.document.stitching import StitchedPage, StitchedBlock
from backend.app.v2.segmenter.models import (
    BoundingBox, DetectedAviso, DetectedBlock, DetectedColumn,
)
from backend.app.v2.segmenter.column_analyzer import ColumnAnalyzer
from backend.app.v2.segmenter.notice_detector import NoticeDetector


class NewspaperLayout:
    def __init__(
        self,
        column_analyzer: ColumnAnalyzer = None,
        notice_detector: NoticeDetector = None,
    ):
        self._column_analyzer = column_analyzer or ColumnAnalyzer()
        self._notice_detector = notice_detector or NoticeDetector()

    def segment(self, stitched_page: StitchedPage) -> list[DetectedAviso]:
        blocks = self._to_detected_blocks(stitched_page)
        if not blocks:
            return []

        explicit_columns = {
            sb.column_index: block
            for sb, block in zip(stitched_page.blocks, blocks)
            if sb.column_index >= 0
        }
        if explicit_columns:
            columns = [
                DetectedColumn(index=index, bbox=block.bbox, blocks=[block])
                for index, block in sorted(explicit_columns.items())
            ]
        else:
            columns = self._column_analyzer.analyze(blocks, stitched_page.width, stitched_page.height)
        all_avisos: list[DetectedAviso] = []

        for col in columns:
            col_avisos = self._notice_detector.detect_avisos(col.blocks)
            all_avisos.extend(col_avisos)

        return all_avisos

    def _to_detected_blocks(self, stitched_page: StitchedPage) -> list[DetectedBlock]:
        blocks: list[DetectedBlock] = []
        for sb in stitched_page.blocks:
            detected = DetectedBlock(
                text=sb.text,
                bbox=BoundingBox(x0=sb.x0, y0=sb.y0, x1=sb.x1, y1=sb.y1),
                confidence=sb.confidence,
                block_type=sb.block_type,
            )
            blocks.append(detected)
        return blocks
