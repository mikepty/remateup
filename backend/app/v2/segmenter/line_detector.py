from backend.app.v2.ocr.models import OCRWord
from backend.app.v2.segmenter.models import DetectedLine, BoundingBox


class LineDetector:
    def __init__(self, y_tolerance_ratio: float = 0.008, min_words_per_line: int = 1):
        self._y_tolerance_ratio = y_tolerance_ratio
        self._min_words_per_line = min_words_per_line

    def detect_lines(self, words: list[OCRWord]) -> list[DetectedLine]:
        if not words:
            return []

        sorted_words = sorted(words, key=lambda w: (w.y0, w.x0))
        lines: list[list[OCRWord]] = []
        current_line: list[OCRWord] = [sorted_words[0]]

        for w in sorted_words[1:]:
            ref_y = sum(ocw.y0 for ocw in current_line) / len(current_line)
            if abs(w.y0 - ref_y) <= self._y_tolerance(w, current_line):
                current_line.append(w)
            else:
                lines.append(current_line)
                current_line = [w]

        if current_line:
            lines.append(current_line)

        result = []
        for line_words in lines:
            line = self._build_line(line_words)
            if len(line_words) >= self._min_words_per_line:
                result.append(line)

        return result

    def _y_tolerance(self, word: OCRWord, current_line: list[OCRWord]) -> int:
        heights = [w.y1 - w.y0 for w in current_line]
        avg_height = sum(heights) / len(heights) if heights else 20
        return max(int(avg_height * self._y_tolerance_ratio), 3)

    def _build_line(self, line_words: list[OCRWord]) -> DetectedLine:
        sorted_w = sorted(line_words, key=lambda w: w.x0)
        text_parts: list[str] = []
        bboxes = []

        for i, w in enumerate(sorted_w):
            text_parts.append(w.text)
            if i < len(sorted_w) - 1:
                br = w.break_type
                if br == "LINE_BREAK":
                    text_parts.append("\n")
                elif br == "HYPHEN":
                    text_parts.append("-\n")
                elif br in ("SPACE", "EOL_SURE_SPACE", ""):
                    text_parts.append(" ")

            bboxes.append((w.x0, w.y0, w.x1, w.y1))

        text = "".join(text_parts)
        x0 = min(b[0] for b in bboxes)
        y0 = min(b[1] for b in bboxes)
        x1 = max(b[2] for b in bboxes)
        y1 = max(b[3] for b in bboxes)
        confidence = round(
            sum(w.confidence for w in sorted_w) / len(sorted_w), 4
        ) if sorted_w else 0.0

        return DetectedLine(
            words=sorted_w,
            text=text,
            bbox=BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1),
            confidence=confidence,
            y_center=(y0 + y1) / 2.0,
        )

    def merge_split_words(self, line_words: list[OCRWord]) -> list[OCRWord]:
        if len(line_words) < 2:
            return line_words

        merged: list[OCRWord] = []
        i = 0
        while i < len(line_words):
            w = line_words[i]
            should_merge = False
            if i > 0 or (merged and i == 0):
                prev = merged[-1] if merged else line_words[i - 1]
                x_gap = w.x0 - prev.x1
                char_width = max((w.x1 - w.x0) / max(len(w.text), 1), 1)
                if x_gap > 0 and x_gap < char_width * 2:
                    if len(w.text) == 1 or len(prev.text) == 1:
                        should_merge = True
            if should_merge:
                prev = merged.pop()
                merged_text = prev.text + w.text
                merged_word = OCRWord(
                    text=merged_text,
                    confidence=min(prev.confidence, w.confidence),
                    x0=prev.x0,
                    y0=min(prev.y0, w.y0),
                    x1=w.x1,
                    y1=max(prev.y1, w.y1),
                    page=prev.page,
                    break_type=w.break_type,
                )
                merged.append(merged_word)
            else:
                merged.append(w)
            i += 1

        return merged
