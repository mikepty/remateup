"""Multi-column detection for newspaper page layout.

Uses vertical projection histogram and whitespace gap analysis
to detect newspaper column structure from block coordinates.
"""

from backend.app.v2.segmenter.models import BoundingBox, DetectedColumn


class ColumnAnalyzer:
    MIN_TEXT_DENSITY = 3
    MIN_COLUMN_WIDTH_RATIO = 0.08
    MAX_COLUMNS = 4

    def analyze(self, blocks: list, page_width: int, page_height: int) -> list[DetectedColumn]:
        if not blocks or page_width == 0:
            return [DetectedColumn(index=0)]

        block_ranges = []
        for b in blocks:
            x0 = getattr(b, "x0", 0)
            x1 = getattr(b, "x1", 0) or getattr(getattr(b, "bbox", None), "x1", 0)
            bbox = getattr(b, "bbox", None)
            if bbox:
                x0 = bbox.x0
                x1 = bbox.x1
            if x1 > x0:
                block_ranges.append((x0, x1))

        if not block_ranges:
            return [DetectedColumn(index=0)]

        profile = self._build_profile(block_ranges, page_width)
        gaps = self._find_gaps(profile, page_width)
        columns = self._build_columns(gaps, page_width, page_height, blocks)

        return columns if columns else [DetectedColumn(index=0)]

    def _build_profile(self, block_ranges: list[tuple[int, int]], page_width: int) -> list[int]:
        profile = [0] * page_width
        for x0, x1 in block_ranges:
            x0 = max(0, min(x0, page_width - 1))
            x1 = max(x0 + 1, min(x1, page_width - 1))
            for x in range(x0, x1):
                if 0 <= x < page_width:
                    profile[x] += 1
        return profile

    def _find_gaps(self, profile: list[int], page_width: int) -> list[int]:
        gap_threshold = max(1, page_width // 100)
        margin = page_width // 20
        gaps = [margin]
        in_gap = False
        gap_start = 0
        for x in range(margin, page_width - margin):
            if profile[x] < self.MIN_TEXT_DENSITY:
                if not in_gap:
                    gap_start = x
                    in_gap = True
            else:
                if in_gap:
                    gap_width = x - gap_start
                    if gap_width >= gap_threshold:
                        gaps.append((gap_start + x) // 2)
                    in_gap = False
        if in_gap:
            gap_width = (page_width - margin) - gap_start
            if gap_width >= gap_threshold:
                gaps.append((gap_start + (page_width - margin)) // 2)
        gaps.append(page_width - margin)
        return sorted(set(gaps))

    def _build_columns(self, gaps: list[int], page_width: int, page_height: int,
                       blocks: list) -> list[DetectedColumn]:
        columns: list[DetectedColumn] = []
        for i in range(len(gaps) - 1):
            col_x0 = gaps[i]
            col_x1 = gaps[i + 1]
            col_width = col_x1 - col_x0
            if col_width < page_width * self.MIN_COLUMN_WIDTH_RATIO:
                continue

            col_blocks = []
            for b in blocks:
                bx0 = getattr(b, "x0", 0)
                bx1 = getattr(b, "x1", 0)
                bbox = getattr(b, "bbox", None)
                if bbox:
                    bx0 = bbox.x0
                    bx1 = bbox.x1
                center = (bx0 + bx1) / 2
                if col_x0 <= center < col_x1:
                    col_blocks.append(b)

            if not col_blocks:
                continue

            ys = []
            for b in col_blocks:
                by0 = getattr(b, "y0", 0)
                by1 = getattr(b, "y1", 0)
                bbox = getattr(b, "bbox", None)
                if bbox:
                    by0 = bbox.y0
                    by1 = bbox.y1
                ys.append(by0)
                ys.append(by1)

            columns.append(DetectedColumn(
                index=len(columns),
                bbox=BoundingBox(x0=col_x0, y0=min(ys), x1=col_x1, y1=max(ys)),
                blocks=col_blocks,
            ))

            if len(columns) >= self.MAX_COLUMNS:
                break

        return columns
