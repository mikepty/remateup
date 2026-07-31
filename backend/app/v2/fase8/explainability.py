"""FASE 8.6 — Explainability.

Generates human-readable explanations for pipeline decisions,
including why fields were accepted/rejected and what influenced
confidence scores.
"""

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))


@dataclass
class Explanation:
    decision: str
    reason: str
    confidence: float
    contributing_factors: list[dict] = field(default_factory=list)
    field_explanations: dict[str, str] = field(default_factory=dict)
    stage_explanations: dict[str, str] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "decision": self.decision,
            "reason": self.reason,
            "confidence": self.confidence,
            "contributing_factors": self.contributing_factors,
            "field_explanations": self.field_explanations,
            "stage_explanations": self.stage_explanations,
            "recommendations": self.recommendations,
        }


@dataclass
class FieldExplanation:
    field_name: str
    v2_field_name: str
    value: Any
    confidence: float
    confidence_reason: str
    confidence_sources: dict
    status: str
    source: str
    normalization_success: bool
    normalization_details: dict
    evidence_count: int
    explanation: str

    def to_dict(self) -> dict:
        return {
            "field_name": self.field_name,
            "v2_field_name": self.v2_field_name,
            "value": self.value,
            "confidence": self.confidence,
            "confidence_reason": self.confidence_reason,
            "confidence_sources": self.confidence_sources,
            "status": self.status,
            "source": self.source,
            "normalization_success": self.normalization_success,
            "normalization_details": self.normalization_details,
            "evidence_count": self.evidence_count,
            "explanation": self.explanation,
        }


class ExplainabilityEngine:
    V1_TO_V2_MAP = {
        "expediente": "expediente",
        "finca_matr": "finca",
        "base": "precio_base",
        "fecha": "fecha_remate",
        "demandante": "demandante",
        "demandado": "demandado",
        "fianza_porcentaje": "fianza_porcentaje",
        "minimo_porcentaje": "minimo_porcentaje",
        "lugar": "lugar",
        "proceso": "proceso",
        "provincia": "provincia",
        "categoria": "categoria",
    }

    def explain_validation(self, validation: dict) -> Explanation:
        decision = validation.get("decision", "REQUIRES_REVIEW")
        score = validation.get("score", 0.0)
        header_detected = validation.get("header_detected", "")
        header_valid = validation.get("header_valid", False)
        inconsistencies = validation.get("inconsistencies", [])
        rules_applied = validation.get("rules_applied", [])
        rules_failed = validation.get("rules_failed", [])

        factors = []
        field_explanations = {}
        stage_explanations = {}
        recommendations = []

        if header_valid:
            factors.append({
                "factor": "header_detection",
                "weight": 0.25,
                "passed": True,
                "detail": f"Valid header detected: '{header_detected}'",
            })
            stage_explanations["header"] = "Valid remate header found in text"
        else:
            factors.append({
                "factor": "header_detection",
                "weight": 0.25,
                "passed": False,
                "detail": f"No valid header detected. Found: '{header_detected}'",
            })
            stage_explanations["header"] = "No valid remate header found"
            recommendations.append("Ensure document contains a valid remate header (AVISO DE REMATE, REMATE JUDICIAL, etc.)")

        passed_rules = [r for r in rules_applied if r.get("passed")]
        failed_rules = rules_failed if rules_failed else [r for r in rules_applied if not r.get("passed")]

        for r in rules_applied:
            if r.get("passed"):
                factors.append({
                    "factor": r.get("rule_name", "unknown"),
                    "weight": r.get("weight", 0.1),
                    "passed": True,
                    "detail": r.get("detail", ""),
                })
            else:
                factors.append({
                    "factor": r.get("rule_name", "unknown"),
                    "weight": r.get("weight", 0.1),
                    "passed": False,
                    "detail": r.get("detail", ""),
                })
                recommendations.append(f"Review rule: {r.get('rule_name', 'unknown')}")

        if inconsistencies:
            for inc in inconsistencies:
                if isinstance(inc, dict):
                    factors.append({
                        "factor": "consistency_check",
                        "weight": 0.1,
                        "passed": False,
                        "detail": f"Inconsistency: {inc.get('field_1', '?')} vs {inc.get('field_2', '?')} - {inc.get('description', '')}",
                    })
                else:
                    factors.append({
                        "factor": "consistency_check",
                        "weight": 0.1,
                        "passed": False,
                        "detail": str(inc),
                    })
            stage_explanations["consistency"] = f"{len(inconsistencies)} inconsistency(ies) detected"
        else:
            stage_explanations["consistency"] = "No inconsistencies detected"

        dup_info = validation.get("duplicate_info", {})
        if dup_info:
            level = dup_info.get("level", "UNIQUE")
            if level != "UNIQUE":
                factors.append({
                    "factor": "duplicate_detection",
                    "weight": 0.1,
                    "passed": False,
                    "detail": f"Duplicate detected: level={level}, similarity={dup_info.get('similarity', 0)}",
                })
                recommendations.append("This aviso may be a duplicate of a previously processed notice")
            else:
                stage_explanations["duplicate"] = "No duplicates detected"

        reason = self._build_reason(decision, score, header_valid, len(inconsistencies), len(failed_rules))

        return Explanation(
            decision=decision,
            reason=reason,
            confidence=score,
            contributing_factors=factors,
            field_explanations=field_explanations,
            stage_explanations=stage_explanations,
            recommendations=recommendations,
        )

    def _build_reason(self, decision: str, score: float, header_valid: bool,
                      inconsistencies: int, failed_rules: int) -> str:
        parts = []
        parts.append(f"Decision: {decision}")
        parts.append(f"Score: {score:.2f}")

        if not header_valid:
            parts.append("Invalid or missing header")
        else:
            parts.append("Valid header detected")

        if inconsistencies > 0:
            parts.append(f"{inconsistencies} inconsistency(ies) found")

        if failed_rules > 0:
            parts.append(f"{failed_rules} rule(s) failed")

        return "; ".join(parts)

    def explain_field(self, field_name: str, field_data: dict) -> FieldExplanation:
        v2_name = self.V1_TO_V2_MAP.get(field_name, field_name)
        norm = field_data.get("normalization", {})
        sources = field_data.get("confidence_sources", {})
        confidence_reason = field_data.get("confidence_reason", "")

        if field_data.get("source") == "knowledge":
            explanation = f"Field '{field_name}' was enhanced by the knowledge engine"
        elif field_data.get("source") == "parser":
            explanation = f"Field '{field_name}' was extracted by the parser"
        else:
            explanation = f"Field '{field_name}' was extracted from the pipeline"

        if sources.get("knowledge_boost"):
            explanation += f" (knowledge boost: +{sources['knowledge_boost']})"
        if sources.get("validator_passed"):
            explanation += " (validator passed)"

        return FieldExplanation(
            field_name=field_name,
            v2_field_name=v2_name,
            value=field_data.get("value"),
            confidence=field_data.get("confidence", 0.0),
            confidence_reason=confidence_reason,
            confidence_sources=sources,
            status=field_data.get("status", "not_found"),
            source=field_data.get("source", "parser"),
            normalization_success=norm.get("success", False),
            normalization_details=norm,
            evidence_count=len(field_data.get("evidence", [])),
            explanation=explanation,
        )

    def explain_pipeline_result(self, pipeline_result: dict) -> dict:
        validation = pipeline_result.get("validation", {})
        explanation = self.explain_validation(validation)

        fields = pipeline_result.get("fields", {})
        field_explanations = {}
        for v1_name, v2_name in self.V1_TO_V2_MAP.items():
            fdata = fields.get(v2_name)
            if fdata and isinstance(fdata, dict):
                field_explanations[v1_name] = self.explain_field(v1_name, fdata).to_dict()

        stages = pipeline_result.get("stages", {})
        stage_explanations = {}
        for stage_name, stage_data in stages.items():
            if isinstance(stage_data, dict):
                status = stage_data.get("status", "unknown")
                duration = stage_data.get("duration_ms", 0)
                warnings = stage_data.get("warnings", [])
                errors = stage_data.get("errors", [])

                detail = f"Status: {status}, Duration: {duration}ms"
                if warnings:
                    detail += f", Warnings: {len(warnings)}"
                if errors:
                    detail += f", Errors: {len(errors)}"
                stage_explanations[stage_name] = detail

        return {
            "document_id": pipeline_result.get("document_id", ""),
            "country": pipeline_result.get("country", ""),
            "decision_explanation": explanation.to_dict(),
            "field_explanations": field_explanations,
            "stage_explanations": stage_explanations,
            "confidence_score": pipeline_result.get("confidence", 0.0),
            "recommendations": explanation.recommendations,
        }

    def generate_report(self, explanations: list[dict]) -> dict:
        total = len(explanations)
        decisions = {}
        total_fields = 0
        explained_fields = 0

        for exp in explanations:
            decision = exp.get("decision_explanation", {}).get("decision", "UNKNOWN")
            decisions[decision] = decisions.get(decision, 0) + 1
            field_exps = exp.get("field_explanations", {})
            total_fields += len(field_exps)
            explained_fields += len(field_exps)

        return {
            "total_documents": total,
            "decision_distribution": decisions,
            "total_fields_explained": total_fields,
            "avg_fields_per_document": round(total_fields / max(total, 1), 1),
            "explanations": explanations,
        }

    def save_report(self, report: dict, output_path: str):
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
