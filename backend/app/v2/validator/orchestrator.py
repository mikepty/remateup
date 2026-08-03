"""ValidationOrchestrator — ties NoticeValidator + ConsistencyEngine + DuplicateDetector + NoticeScorer."""

from typing import Optional

from backend.app.v2.validator.models import (
    Decision, NoticeDecision, ValidationResult,
)
from backend.app.v2.validator.notice_validator import NoticeValidator
from backend.app.v2.validator.consistency import ConsistencyEngine
from backend.app.v2.validator.duplicate_detector import DuplicateDetector
from backend.app.v2.validator.scoring import NoticeScorer


class ValidationOrchestrator:
    def __init__(self):
        self._validator = NoticeValidator()
        self._consistency = ConsistencyEngine()
        self._dedup = DuplicateDetector()
        self._scorer = NoticeScorer()

    def reset(self):
        self._dedup.reset()

    def export_duplicate_state(self) -> list[dict]:
        """Memoria de avisos vistos por el detector de duplicados, lista para
        persistir y reutilizar en una futura sesión (ver DuplicateDetector)."""
        return self._dedup.export_state()

    def load_duplicate_state(self, state: Optional[list[dict]]) -> None:
        """Restaura memoria de avisos vistos de una sesión anterior, para que
        la detección de duplicados funcione entre documentos procesados en
        distintas corridas (no solo dentro del mismo lote)."""
        self._dedup.load_state(state)

    def validate_notice(
        self,
        aviso_id: str,
        text: str,
        fields_found: dict,
        bbox: Optional[dict] = None,
    ) -> NoticeDecision:
        decision = self._validator.validate(
            aviso_id=aviso_id, text=text, fields_found=fields_found,
        )

        inconsistencies = self._consistency.check(
            fields_found=fields_found, text=text,
        )
        decision.inconsistencies = inconsistencies

        dup_info = self._dedup.check(
            aviso_id=aviso_id, fields_found=fields_found,
            text=text, bbox=bbox,
        )
        decision.duplicate_info = dup_info

        if dup_info.level.value == "DUPLICATED":
            decision.decision = Decision.DUPLICATED
        elif dup_info.level.value == "LIKELY_DUPLICATED" and decision.decision == Decision.VALID:
            decision.decision = Decision.LIKELY_DUPLICATED

        if inconsistencies and decision.decision == Decision.VALID:
            high_sev = any(i.severity == "high" for i in inconsistencies)
            if high_sev:
                decision.decision = Decision.INCONSISTENT
            else:
                decision.decision = Decision.INCONSISTENT

        decision.score = self._scorer.score(decision)

        return decision

    def validate_batch(
        self,
        avisos: list[dict],
        reset_duplicates: bool = True,
    ) -> ValidationResult:
        if reset_duplicates:
            self.reset()
        decisions: list[NoticeDecision] = []
        for aviso in avisos:
            d = self.validate_notice(
                aviso_id=aviso.get("id", ""),
                text=aviso.get("text", ""),
                fields_found=aviso.get("fields", {}),
                bbox=aviso.get("bbox"),
            )
            decisions.append(d)

        result = ValidationResult(decisions=decisions)
        result.total_avisos = len(decisions)
        for d in decisions:
            if d.decision == Decision.VALID:
                result.valid_count += 1
            elif d.decision == Decision.INVALID:
                result.invalid_count += 1
            elif d.decision in (Decision.DUPLICATED, Decision.LIKELY_DUPLICATED):
                result.duplicated_count += 1
            elif d.decision == Decision.INCOMPLETE:
                result.incomplete_count += 1
            elif d.decision == Decision.INCONSISTENT:
                result.inconsistent_count += 1
            elif d.decision == Decision.REQUIRES_REVIEW:
                result.review_count += 1

        scores = [d.score for d in decisions if d.score > 0]
        result.avg_score = round(
            sum(scores) / max(len(scores), 1), 4
        ) if scores else 0.0

        return result
