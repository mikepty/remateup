from backend.app.v2.segmenter.models import BoundingBox, DetectedColumn, DetectedBlock


class ColumnDetector:
    def __init__(self, min_words_per_column: int = 3, column_gap_ratio: float = 0.02):
        self._min_words_per_column = min_words_per_column
        self._column_gap_ratio = column_gap_ratio

    def detect(self, blocks: list[DetectedBlock], page_width: int) -> list[DetectedColumn]:
        if not blocks or page_width == 0:
            return [DetectedColumn(index=0, blocks=blocks)]

        centers = []
        for b in blocks:
            if b.bbox:
                centers.append(b.bbox.center_x())
        if not centers:
            return [DetectedColumn(index=0, blocks=blocks)]

        min_x = min(c for c in centers)
        max_x = max(c for c in centers)
        span = max_x - min_x
        if span < page_width * 0.15:
            return [DetectedColumn(index=0, blocks=blocks)]

        bucket_size = max(1, page_width // 4)
        histogram: dict[int, int] = {}
        for c in centers:
            bucket = int(c // bucket_size)
            histogram[bucket] = histogram.get(bucket, 0) + 1

        sorted_buckets = sorted(histogram.keys())
        merged: list[tuple[int, int]] = []
        current_start = sorted_buckets[0]
        current_end = sorted_buckets[0]
        for b in sorted_buckets[1:]:
            if b - current_end <= 1:
                current_end = b
            else:
                merged.append((current_start, current_end))
                current_start = b
                current_end = b
        merged.append((current_start, current_end))

        significant = [
            (s, e) for s, e in merged
            if histogram.get(s, 0) >= self._min_words_per_column
        ]
        if len(significant) < 2:
            return [DetectedColumn(index=0, blocks=blocks)]

        columns: list[DetectedColumn] = []
        for col_idx, (s, e) in enumerate(significant):
            col_min = s * bucket_size
            col_max = (e + 1) * bucket_size
            col_blocks = [
                b for b in blocks
                if b.bbox and col_min <= b.bbox.center_x() < col_max
            ]
            columns.append(DetectedColumn(
                index=col_idx,
                bbox=BoundingBox(x0=col_min, y0=0, x1=col_max, y1=0),
                blocks=col_blocks,
            ))

        if not columns:
            return [DetectedColumn(index=0, blocks=blocks)]

        for col_idx, col in enumerate(columns):
            ys = [b.bbox.y0 for b in col.blocks if b.bbox]
            if ys:
                col.bbox.y0 = min(ys)
                col.bbox.y1 = max(b.bbox.y1 for b in col.blocks if b.bbox)

        return columns

    def assign_to_column(self, center_x: float, columns: list[DetectedColumn]) -> int:
        for col in columns:
            if col.bbox and col.bbox.x0 <= center_x < col.bbox.x1:
                return col.index
        return 0

    def assign_blocks(self, blocks: list[DetectedBlock], page_width: int) -> list[DetectedColumn]:
        return self.detect(blocks, page_width)
