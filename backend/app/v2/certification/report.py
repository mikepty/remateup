from datetime import datetime
from typing import Any

from backend.app.v2.certification.models import CertDocument, CertAviso, CertDecision


class ProductionReportGenerator:
    def generate(self, documents: list[CertDocument]) -> dict:
        total_avisos = sum(len(d.all_avisos) for d in documents)
        all_avisos: list = []
        for d in documents:
            all_avisos.extend(d.all_avisos)

        valid = sum(1 for a in all_avisos if a.decision == CertDecision.VALID)
        invalid = sum(1 for a in all_avisos if a.decision == CertDecision.INVALID)
        duplicated = sum(1 for a in all_avisos if a.decision in (CertDecision.DUPLICATED, CertDecision.LIKELY_DUPLICATED))
        incomplete = sum(1 for a in all_avisos if a.decision == CertDecision.INCOMPLETE)
        inconsistent = sum(1 for a in all_avisos if a.decision == CertDecision.INCONSISTENT)
        review = sum(1 for a in all_avisos if a.decision == CertDecision.REQUIRES_REVIEW)

        total_time = sum(d.total_time_ms for d in documents)
        avg_time = total_time / max(len(documents), 1)

        all_avisos: list[CertAviso] = []
        for d in documents:
            all_avisos.extend(d.all_avisos)

        avg_score = sum(a.score for a in all_avisos if a.score > 0) / max(len([a for a in all_avisos if a.score > 0]), 1) if all_avisos else 0
        avg_conf = sum(a.confidence for a in all_avisos if a.confidence > 0) / max(len([a for a in all_avisos if a.confidence > 0]), 1) if all_avisos else 0

        return {
            "report_type": "production_validation",
            "generated_at": datetime.utcnow().isoformat(),
            "documents_processed": len(documents),
            "total_avisos": total_avisos,
            "aviso_decisions": {
                "valid": valid,
                "invalid": invalid,
                "duplicated": duplicated,
                "incomplete": incomplete,
                "inconsistent": inconsistent,
                "requires_review": review,
            },
            "performance": {
                "total_time_ms": round(total_time, 2),
                "avg_time_ms": round(avg_time, 2),
                "avg_score": round(avg_score, 4),
                "avg_confidence": round(avg_conf, 4),
            },
            "coverage": {
                "valid_pct": round(valid / max(total_avisos, 1) * 100, 2),
                "auto_approved_pct": round((valid + duplicated) / max(total_avisos, 1) * 100, 2),
                "manual_review_pct": round(review / max(total_avisos, 1) * 100, 2),
            },
            "documents": [d.to_dict() for d in documents],
        }
