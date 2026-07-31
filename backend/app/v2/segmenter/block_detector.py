from backend.app.v2.ocr.models import OCRBlock
from backend.app.v2.segmenter.models import DetectedLine, DetectedBlock, BoundingBox


class BlockDetector:
    def __init__(
        self,
        vertical_gap_ratio: float = 1.5,
        min_block_lines: int = 1,
        merge_by_ocr_block: bool = True,
    ):
        self._vertical_gap_ratio = vertical_gap_ratio
        self._min_block_lines = min_block_lines
        self._merge_by_ocr_block = merge_by_ocr_block

    def detect(self, lines: list[DetectedLine], page_height: int = 0) -> list[DetectedBlock]:
        if not lines:
            return []

        blocks: list[DetectedBlock] = []
        current_lines: list[DetectedLine] = [lines[0]]

        for line in lines[1:]:
            prev = current_lines[-1]
            gap = line.y_center - prev.y_center
            avg_line_height = self._avg_line_height(current_lines)
            threshold = max(avg_line_height * self._vertical_gap_ratio, 10)

            if gap > threshold:
                block = self._build_block(current_lines)
                blocks.append(block)
                current_lines = [line]
            else:
                current_lines.append(line)

        if current_lines:
            blocks.append(self._build_block(current_lines))

        result = [b for b in blocks if len(b.lines) >= self._min_block_lines]

        if self._merge_by_ocr_block:
            result = self._merge_with_ocr_blocks(result)

        return result

    def _avg_line_height(self, lines: list[DetectedLine]) -> float:
        heights = [
            line.bbox.height() for line in lines if line.bbox
        ]
        return sum(heights) / len(heights) if heights else 20.0

    def _build_block(self, lines: list[DetectedLine]) -> DetectedBlock:
        sorted_lines = sorted(lines, key=lambda l: (l.y_center, l.bbox.x0 if l.bbox else 0))
        text = "\n".join(l.text for l in sorted_lines if l.text.strip())
        xs = [l.bbox.x0 for l in sorted_lines if l.bbox]
        ys = [l.bbox.y0 for l in sorted_lines if l.bbox]
        x1s = [l.bbox.x1 for l in sorted_lines if l.bbox]
        y1s = [l.bbox.y1 for l in sorted_lines if l.bbox]

        bbox = BoundingBox(
            x0=min(xs) if xs else 0,
            y0=min(ys) if ys else 0,
            x1=max(x1s) if x1s else 0,
            y1=max(y1s) if y1s else 0,
        ) if xs else None

        confidence = round(
            sum(l.confidence for l in sorted_lines) / len(sorted_lines), 4
        ) if sorted_lines else 0.0

        return DetectedBlock(
            lines=sorted_lines,
            text=text,
            bbox=bbox,
            confidence=confidence,
            block_type="text",
        )

    def _merge_with_ocr_blocks(self, blocks: list[DetectedBlock]) -> list[DetectedBlock]:
        return blocks

    def detect_from_ocr_blocks(self, ocr_blocks: list[OCRBlock]) -> list[DetectedBlock]:
        from backend.app.v2.segmenter.line_detector import LineDetector

        line_detector = LineDetector()
        all_lines: list[DetectedLine] = []

        for b in ocr_blocks:
            if not b.words:
                line = DetectedLine(
                    text=b.text,
                    bbox=BoundingBox(x0=b.x0, y0=b.y0, x1=b.x1, y1=b.y1),
                    confidence=b.confidence,
                    y_center=(b.y0 + b.y1) / 2.0,
                )
                all_lines.append(line)
            else:
                lines = line_detector.detect_lines(b.words)
                all_lines.extend(lines)

        return self.detect(all_lines)
