from typing import Any, Optional

from backend.app.v2.document.models import Document
from backend.app.v2.evidence.models import (
    Evidence, ExtractedField, EvidenceType, ExtractionState,
)
from backend.app.v2.evidence.repository import MemoryEvidenceStore


class EvidenceService:
    def __init__(self, store: Optional[MemoryEvidenceStore] = None):
        self._store = store or MemoryEvidenceStore()
        self._fields: dict[str, ExtractedField] = {}
        self._evidence_log: list[Evidence] = []

    def register_evidence(self, field_name: str, value: Any, raw_value: Any,
                          evidence_type: EvidenceType, confidence: float,
                          source: str, state: Optional[ExtractionState] = None,
                          bounding_box: Optional[dict] = None,
                          page: int = 0) -> Evidence:
        if state is None:
            if value is not None and raw_value is not None:
                state = ExtractionState.FOUND
            else:
                state = ExtractionState.NOT_FOUND
        if value is not None and confidence is not None:
            try:
                if float(confidence) < 0.5:
                    state = ExtractionState.REQUIRES_REVIEW
            except (ValueError, TypeError):
                pass

        ev = Evidence(
            field_name=field_name,
            value=value,
            raw_value=raw_value,
            state=state,
            evidence_type=evidence_type,
            confidence=float(confidence) if confidence else 0.0,
            source=source,
            page=page,
            bounding_box=bounding_box,
        )
        self._evidence_log.append(ev)
        return ev

    def register_text_evidence(self, field_name: str, text: str,
                                source: str = "ocr_text",
                                confidence: float = 1.0) -> Evidence:
        return self.register_evidence(
            field_name=field_name,
            value=text,
            raw_value=text,
            evidence_type=EvidenceType.OCR_TEXT,
            confidence=confidence,
            source=source,
        )

    def register_label_value_evidence(self, field_name: str, label: str,
                                       value: Any, confidence: float = 0.9) -> Evidence:
        return self.register_evidence(
            field_name=field_name,
            value=value,
            raw_value=value,
            evidence_type=EvidenceType.LABEL_VALUE_RELATION,
            confidence=confidence,
            source=f"label_value:{label}",
        )

    def register_correction(self, field_name: str, old_value: Any,
                             new_value: Any, aviso_id: int) -> Evidence:
        return self.register_evidence(
            field_name=field_name,
            value=new_value,
            raw_value=old_value,
            evidence_type=EvidenceType.MANUAL_CORRECTION,
            confidence=1.0,
            source=f"user_correction:aviso_{aviso_id}",
        )

    def build_field(self, field_name: str) -> ExtractedField:
        related = [e for e in self._evidence_log if e.field_name == field_name]
        if not related:
            return ExtractedField.not_found(field_name)
        best = max(related, key=lambda e: e.confidence)
        return ExtractedField(
            field_name=field_name,
            value=best.value,
            raw_value=best.raw_value,
            state=best.state,
            evidence=related,
            confidence=best.confidence,
        )

    def build_all_fields(self, field_names: list[str]) -> dict[str, ExtractedField]:
        self._fields = {fn: self.build_field(fn) for fn in field_names}
        return self._fields

    def get_field(self, field_name: str) -> Optional[ExtractedField]:
        return self._fields.get(field_name)

    def has_evidence(self, field_name: str) -> bool:
        return any(e.field_name == field_name for e in self._evidence_log)

    def get_evidence_for_field(self, field_name: str) -> list[Evidence]:
        return [e for e in self._evidence_log if e.field_name == field_name]

    def apply_to_document(self, doc: Document) -> Document:
        for field_name in doc.fields:
            extracted = self.build_field(field_name)
            if extracted.is_found and field_name in doc.fields:
                df = doc.fields[field_name]
                df.value = extracted.value
                df.confidence = extracted.confidence
                df.state = extracted.state.value
                df.evidence = [e.to_dict() for e in extracted.evidence]
        return doc

    def summary(self) -> dict:
        found = sum(1 for e in self._evidence_log if e.state == ExtractionState.FOUND)
        not_found = sum(1 for e in self._evidence_log if e.state == ExtractionState.NOT_FOUND)
        review = sum(1 for e in self._evidence_log if e.state == ExtractionState.REQUIRES_REVIEW)
        return {
            "total_evidence": len(self._evidence_log),
            "found": found,
            "not_found": not_found,
            "requires_review": review,
            "unique_fields": len(set(e.field_name for e in self._evidence_log)),
        }

    def save_for_aviso(self, aviso_id: int) -> int:
        count = 0
        for ev in self._evidence_log:
            self._store.store(aviso_id, ev)
            count += 1
        return count

    def clear(self):
        self._fields.clear()
        self._evidence_log.clear()
