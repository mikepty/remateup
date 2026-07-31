import json
from typing import Optional
from sqlalchemy.orm import Session
from .models import Evidence, ExtractedField


class EvidenceRepository:
    def __init__(self, db: Session):
        self.db = db

    def save_evidence(self, evidence: Evidence, aviso_id: int) -> dict:
        raise NotImplementedError("Database migration pending. Use memory storage for now.")

    def get_evidence_for_field(self, aviso_id: int, field_name: str) -> list[Evidence]:
        raise NotImplementedError("Database migration pending.")

    def get_all_evidence_for_aviso(self, aviso_id: int) -> list[Evidence]:
        raise NotImplementedError("Database migration pending.")

    def save_extracted_field(self, field: ExtractedField) -> dict:
        raise NotImplementedError("Database migration pending.")


class MemoryEvidenceStore:
    def __init__(self):
        self._evidence: dict[int, list[dict]] = {}
        self._counter = 0

    def store(self, aviso_id: int, evidence: Evidence) -> int:
        self._counter += 1
        eid = self._counter
        d = evidence.to_dict()
        d["id"] = eid
        self._evidence.setdefault(aviso_id, []).append(d)
        return eid

    def get_for_aviso(self, aviso_id: int) -> list[dict]:
        return self._evidence.get(aviso_id, [])

    def get_for_field(self, aviso_id: int, field_name: str) -> list[dict]:
        return [e for e in self._evidence.get(aviso_id, []) if e["field_name"] == field_name]

    def clear(self):
        self._evidence.clear()
        self._counter = 0
