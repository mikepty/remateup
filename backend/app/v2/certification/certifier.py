from datetime import datetime
from typing import Any, Optional

from backend.app.v2.certification.models import (
    CertDocument, CertAviso, CertField, CertPage, CertDecision,
)


class Certifier:
    VERSION = "7.0.0"

    def build_certification(
        self,
        document_id: str,
        source_type: str,
        country: str,
        pipeline_result: dict,
        knowledge_version: str = "",
        validator_version: str = "",
    ) -> CertDocument:
        cert = CertDocument(
            document_id=document_id,
            source_type=source_type,
            country=country,
            version=self.VERSION,
            knowledge_version=knowledge_version,
            validator_version=validator_version,
            total_time_ms=pipeline_result.get("total_time_ms", 0),
            errors=pipeline_result.get("errors", []),
        )

        fields = pipeline_result.get("fields", {})
        validation = pipeline_result.get("validation", {})
        confidence_data = pipeline_result.get("confidence", 0.0)
        stages = pipeline_result.get("stages", {})

        avisos = stages.get("layout", {}).get("avisos_detected", 0)
        present = stages.get("validation", {}).get("present", [])
        missing = stages.get("validation", {}).get("missing", [])

        decision_str = validation.get("decision", "REQUIRES_REVIEW")
        decision = CertDecision(decision_str) if decision_str else CertDecision.REQUIRES_REVIEW

        cert_aviso = CertAviso(
            id=document_id,
            decision=decision,
            score=validation.get("score", 0.0),
            confidence=confidence_data,
            header_detected=validation.get("header_detected", ""),
            header_valid=validation.get("header_valid", False),
            inconsistencies=validation.get("inconsistencies", []),
            duplicate_info=validation.get("duplicate_info"),
            rules_applied=validation.get("rules_applied", []),
            rules_failed=validation.get("rules_failed", []),
            fields_missing=missing,
        )

        for fname, fdata in fields.items():
            cf = CertField(
                name=fname,
                value=fdata.get("value") if isinstance(fdata, dict) else fdata,
                raw_value=fdata.get("value") if isinstance(fdata, dict) else fdata,
                normalized_value=fdata.get("normalized"),
                confidence=fdata.get("confidence", 0) if isinstance(fdata, dict) else 0,
                confidence_reason=fdata.get("confidence_reason", "") if isinstance(fdata, dict) else "",
                confidence_sources=fdata.get("confidence_sources", {}) if isinstance(fdata, dict) else {},
                status=fdata.get("status", "not_found") if isinstance(fdata, dict) else "found",
                source=fdata.get("source", "parser") if isinstance(fdata, dict) else "parser",
                evidence=fdata.get("evidence", []) if isinstance(fdata, dict) else [],
                normalization=fdata.get("normalization", {}) if isinstance(fdata, dict) else {},
            )
            cert_aviso.fields.append(cf)

        if decision == CertDecision.VALID:
            cert.valid_count = 1
        elif decision == CertDecision.DUPLICATED:
            cert.duplicated_count = 1
        elif decision == CertDecision.INCOMPLETE:
            cert.incomplete_count = 1
        elif decision == CertDecision.INCONSISTENT:
            cert.inconsistent_count = 1
        elif decision == CertDecision.INVALID:
            cert.invalid_count = 1
        else:
            cert.review_count = 1

        cert.all_avisos = [cert_aviso]

        cert.statistics = {
            "total_fields": len(fields),
            "fields_present": len(present),
            "fields_missing": len(missing),
            "avisos_detected": avisos,
            "stages_completed": list(stages.keys()),
            "processing_timestamp": datetime.utcnow().isoformat(),
        }

        return cert

    def build_batch_certification(
        self,
        pipeline_results: list[dict],
        knowledge_version: str = "",
        validator_version: str = "",
    ) -> list[CertDocument]:
        certs = []
        for r in pipeline_results:
            c = self.build_certification(
                document_id=r.get("document_id", ""),
                source_type=r.get("source_type", ""),
                country=r.get("country", ""),
                pipeline_result=r,
                knowledge_version=knowledge_version,
                validator_version=validator_version,
            )
            certs.append(c)
        return certs
