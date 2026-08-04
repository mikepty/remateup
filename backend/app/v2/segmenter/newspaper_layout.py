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

from collections import defaultdict

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

        # Agrupar bloques por column_index (puede haber múltiples bloques
        # por columna — ej. 2 avisos en la misma columna del periódico).
        col_groups: dict[int, list[DetectedBlock]] = defaultdict(list)
        for sb, block in zip(stitched_page.blocks, blocks):
            if sb.column_index >= 0:
                col_groups[sb.column_index].append(block)

        if col_groups:
            columns = []
            for index in sorted(col_groups.keys()):
                col_blocks = col_groups[index]
                # Bounding box que engloba todos los bloques de la columna
                x0 = min(b.bbox.x0 for b in col_blocks)
                y0 = min(b.bbox.y0 for b in col_blocks)
                x1 = max(b.bbox.x1 for b in col_blocks)
                y1 = max(b.bbox.y1 for b in col_blocks)
                columns.append(DetectedColumn(
                    index=index,
                    bbox=BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1),
                    blocks=col_blocks,
                ))
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
