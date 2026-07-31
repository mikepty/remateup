import re
from typing import Optional

from backend.app.v2.segmenter.models import (
    AvisoFragment, CompleteAviso,
    BoundingBox, DetectedBlock, DetectedAviso,
)


_RE_AVISO_HEADER = re.compile(
    r"^(?:AVISO\s+DE\s+[A-Z]{0,2}E[MN]ATE|EDICTO\s+EMPLAZATORIO)",
    re.IGNORECASE,
)
_RE_ENDS_WITH_HYPHEN = re.compile(r"-\s*$")
_RE_ENDS_INCOMPLETE = re.compile(
    r"(?:,\s*$|:\s*$|-\s*$|(?:Y|E|O|DE|LA|EL|LOS|LAS|DEL|CON|POR|PARA|SIN)\s*$|^[a-z])",
    re.IGNORECASE,
)
_RE_STARTS_LOWERCASE = re.compile(r"^[a-z]")
_RE_COLUMN_LABEL = re.compile(
    r"^\s*(?:FINCA|EXPEDIENTE|BASE|DEMANDANTE|DEMANDADO|FIANZA|MINIMO|PROVINCIA|LUGAR|JUZGADO)",
    re.IGNORECASE,
)
_RE_ENDS_WITH_LABEL_VALUE_PREFIX = re.compile(
    r"(?:FINCA|EXPEDIENTE|BASE|FIANZA|DEMANDANTE|DEMANDADO|PROVINCIA|LUGAR)\s*[:\s]*$",
    re.IGNORECASE,
)


class ContinuityEngine:
    def __init__(self, column_tolerance_ratio: float = 0.02):
        self._column_tolerance_ratio = column_tolerance_ratio

    def detect_continuity(
        self, fragments: list[AvisoFragment]
    ) -> list[CompleteAviso]:
        if not fragments:
            return []

        top_fragments = [f for f in fragments if f.position == "top"]
        bottom_fragments = [f for f in fragments if f.position == "bottom"]

        if not top_fragments and not bottom_fragments:
            return [self._fragment_to_complete(f) for f in fragments]

        if not bottom_fragments:
            return [self._fragment_to_complete(f) for f in top_fragments]

        if not top_fragments:
            return [self._fragment_to_complete(f) for f in bottom_fragments]

        completed: list[CompleteAviso] = []

        used_bottom: set[int] = set()

        for tf in top_fragments:
            match = self._find_continuation(tf, bottom_fragments, used_bottom)
            if match is not None:
                bf = bottom_fragments[match]
                used_bottom.add(match)
                signals = self._detect_signals(tf, bf)
                merged_text = self._merge_texts(tf, bf, signals)
                all_blocks = tf.blocks + bf.blocks

                xs = [b.bbox.x0 for b in all_blocks if b.bbox]
                ys = [b.bbox.y0 for b in all_blocks if b.bbox]
                x1s = [b.bbox.x1 for b in all_blocks if b.bbox]
                y1s = [b.bbox.y1 for b in all_blocks if b.bbox]
                merged_bbox = BoundingBox(
                    x0=min(xs) if xs else 0, y0=min(ys) if ys else 0,
                    x1=max(x1s) if x1s else 0, y1=max(y1s) if y1s else 0,
                ) if xs else None

                confidence = round(
                    (tf.confidence + bf.confidence) / 2, 4
                ) if tf.confidence and bf.confidence else max(tf.confidence, bf.confidence)

                completed.append(CompleteAviso(
                    fragments=[tf, bf],
                    text=merged_text,
                    bbox=merged_bbox,
                    confidence=confidence,
                    aviso_type="continuacion_aviso",
                    continuity_signals=signals,
                ))
            else:
                completed.append(self._fragment_to_complete(tf))

        for i, bf in enumerate(bottom_fragments):
            if i not in used_bottom:
                completed.append(self._fragment_to_complete(bf))

        return completed

    def _find_continuation(
        self, top: AvisoFragment,
        bottom_candidates: list[AvisoFragment],
        used: set[int],
    ) -> Optional[int]:
        best_idx: Optional[int] = None
        best_score = -1

        for i, bf in enumerate(bottom_candidates):
            if i in used:
                continue

            score = self._continuity_score(top, bf)
            if score > 0 and score > best_score:
                best_score = score
                best_idx = i

        return best_idx

    def _continuity_score(self, top: AvisoFragment, bottom: AvisoFragment) -> float:
        score = 0.0

        if bottom.has_header:
            return -1.0

        if self._columns_aligned(top, bottom):
            score += 3.0

        if self._vertical_near(top, bottom):
            score += 2.0

        if top.ends_with_hyphen:
            score += 2.0

        if _RE_STARTS_LOWERCASE.search(bottom.leading_text):
            score += 2.0

        if top.ends_incomplete:
            score += 1.5

        if self._label_value_continuous(top, bottom):
            score += 2.0

        if self._context_similar(top, bottom):
            score += 1.0

        return score

    def _columns_aligned(self, top: AvisoFragment, bottom: AvisoFragment) -> bool:
        if not top.bbox or not bottom.bbox:
            return False
        col_width = max(top.bbox.width(), 1)
        tolerance = max(int(col_width * self._column_tolerance_ratio), 5)
        return abs(top.bbox.x0 - bottom.bbox.x0) <= tolerance

    def _vertical_near(self, top: AvisoFragment, bottom: AvisoFragment) -> bool:
        if not top.bbox or not bottom.bbox:
            return False
        gap = bottom.bbox.y0 - top.bbox.y1
        return 0 <= gap < 200

    def _label_value_continuous(self, top: AvisoFragment, bottom: AvisoFragment) -> bool:
        top_has_label_prefix = bool(_RE_ENDS_WITH_LABEL_VALUE_PREFIX.search(top.trailing_text))
        bottom_starts_with_value = bool(_RE_STARTS_LOWERCASE.search(bottom.leading_text))
        top_ends_lowercase_label = bool(re.search(r"\b(?:finca|base|expediente|fianza|demandante|demandado|provincia|lugar)\s*[:\s]*$", top.trailing_text, re.IGNORECASE))

        if top_ends_lowercase_label:
            return True

        if top_has_label_prefix and not bottom.has_header:
            return True

        return False

    def _context_similar(self, top: AvisoFragment, bottom: AvisoFragment) -> bool:
        top_words = set(top.trailing_text.lower().split()[-5:]) if top.trailing_text else set()
        bottom_words = set(bottom.leading_text.lower().split()[:5]) if bottom.leading_text else set()
        if not top_words or not bottom_words:
            return False
        overlap = top_words & bottom_words
        return len(overlap) >= 1

    def _detect_signals(self, top: AvisoFragment, bottom: AvisoFragment) -> list[str]:
        signals: list[str] = []
        if self._columns_aligned(top, bottom):
            signals.append("column_alignment")
        if self._vertical_near(top, bottom):
            signals.append("vertical_proximity")
        if top.ends_with_hyphen:
            signals.append("hyphenated_word")
        if _RE_STARTS_LOWERCASE.search(bottom.leading_text):
            signals.append("lowercase_start")
        if top.ends_incomplete:
            signals.append("incomplete_ending")
        if self._label_value_continuous(top, bottom):
            signals.append("label_value_continuity")
        if self._context_similar(top, bottom):
            signals.append("context_similarity")
        return signals

    def _merge_texts(
        self, top: AvisoFragment, bottom: AvisoFragment, signals: list[str]
    ) -> str:
        top_text = top.trailing_text if top.trailing_text else ""
        bottom_text = bottom.leading_text if bottom.leading_text else ""

        if "hyphenated_word" in signals:
            clean = re.sub(r"-\s*$", "", top_text)
            return clean + bottom_text

        return top_text + " " + bottom_text

    def _fragment_to_complete(self, fragment: AvisoFragment) -> CompleteAviso:
        return CompleteAviso(
            fragments=[fragment],
            text=fragment.trailing_text or "",
            bbox=fragment.bbox,
            confidence=fragment.confidence,
            aviso_type="aviso_completo" if fragment.has_header else "unknown",
            continuity_signals=[],
        )

    def build_fragment_from_aviso(
        self,
        aviso: DetectedAviso,
        source_image: str = "",
        page_number: int = 0,
        position: str = "",
    ) -> AvisoFragment:
        text = aviso.full_text or ""
        trailing = text[-100:] if len(text) > 100 else text
        leading = text[:100] if len(text) > 100 else text

        return AvisoFragment(
            source_image=source_image,
            page_number=page_number,
            position=position,
            blocks=aviso.blocks,
            bbox=aviso.bbox,
            confidence=aviso.confidence,
            column_index=0,
            ends_incomplete=bool(_RE_ENDS_INCOMPLETE.search(trailing)) if trailing else False,
            ends_with_hyphen=bool(_RE_ENDS_WITH_HYPHEN.search(trailing)) if trailing else False,
            has_header=bool(_RE_AVISO_HEADER.search(text)) if text else False,
            trailing_text=text,
            leading_text=text,
        )
