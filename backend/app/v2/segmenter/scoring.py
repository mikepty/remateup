from backend.app.v2.segmenter.models import (
    SegmentedDocument, SegmentedPage, DetectedAviso, DetectedColumn, DetectedBlock,
)


class SegmentationScorer:
    def __init__(self):
        self._min_avisos_per_page = 1
        self._expected_columns_newspaper = 2
        self._expected_columns_pdf = 1

    def score(self, segments: list[DetectedAviso], total_words: int) -> dict:
        if not segments or total_words == 0:
            return {
                "coverage": 0.0,
                "aviso_count_quality": 0.0,
                "overall": 0.0,
            }

        words_in_avisos = sum(
            sum(
                sum(len(b.text.split()) for b in col.blocks if isinstance(col, DetectedColumn))
                for col in getattr(p, "columns", [])
            )
            for p in getattr(segments[0], "_pages", []) if hasattr(segments[0], "_pages")
        )

        coverage = min(words_in_avisos / total_words, 1.0) if total_words > 0 else 0.0

        aviso_count_quality = min(len(segments) / max(self._min_avisos_per_page, 1), 1.0)

        overall = round((coverage * 0.6 + aviso_count_quality * 0.4), 4)

        return {
            "coverage": round(coverage, 4),
            "aviso_count_quality": round(aviso_count_quality, 4),
            "overall": overall,
        }

    def score_document(self, document: SegmentedDocument) -> float:
        if not document.pages:
            return 0.0

        page_scores: list[float] = []
        for page in document.pages:
            page_scores.append(self.score_page(page))

        return round(sum(page_scores) / len(page_scores), 4) if page_scores else 0.0

    def score_page(self, page: SegmentedPage) -> float:
        if page.width == 0 and page.height == 0:
            return 0.0

        column_score = self.score_columns(page.columns, self._expected_columns_newspaper)

        aviso_score = 0.0
        if page.avisos:
            valid_avisos = sum(1 for a in page.avisos if a.confidence > 0.3)
            aviso_score = valid_avisos / len(page.avisos) if page.avisos else 0.0

        page_score = round(column_score * 0.3 + aviso_score * 0.7, 4)
        return page_score

    def score_columns(
        self, detected_columns: list[DetectedColumn], expected_columns: int
    ) -> float:
        if expected_columns <= 0:
            return 1.0
        if not detected_columns:
            return 0.0
        detected = len([c for c in detected_columns if c.blocks])
        ratio = detected / expected_columns
        return round(min(ratio, 1.0), 4)

    def score_aviso(self, aviso: DetectedAviso) -> float:
        if not aviso.sections:
            return 0.3
        classified = sum(1 for s in aviso.sections if s.section_type.value != "unknown")
        section_score = classified / len(aviso.sections) if aviso.sections else 0.0
        return round(aviso.confidence * 0.5 + section_score * 0.5, 4)
