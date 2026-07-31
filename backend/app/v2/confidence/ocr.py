from typing import Any, Optional


class OCRConfidenceScorer:
    def score(self, ocr_document: dict) -> float:
        if not ocr_document:
            return 0.0
        pages = ocr_document.get("pages", [])
        if not pages:
            pages = ocr_document.get("ocr_pages", [])
        if not pages:
            return 0.0
        all_confs = []
        for page in pages:
            if isinstance(page, dict):
                words = page.get("words", [])
                for w in words:
                    c = w.get("confidence") if isinstance(w, dict) else None
                    if c is not None:
                        all_confs.append(float(c))
            elif hasattr(page, "words"):
                for w in page.words:
                    c = getattr(w, "confidence", 0) or 0
                    if c > 0:
                        all_confs.append(float(c))
        if not all_confs:
            return 0.0
        return round(sum(all_confs) / len(all_confs), 4)

    def per_word_average(self, words: list[dict]) -> float:
        if not words:
            return 0.0
        confs = [w.get("confidence", 0) for w in words if isinstance(w, dict) and w.get("confidence") is not None]
        if not confs:
            return 0.0
        return round(sum(float(c) for c in confs) / len(confs), 4)
