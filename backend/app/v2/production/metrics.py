"""FASE 10 — Pipeline Metrics.

Aggregates operational metrics across pipeline results:

documentos procesados, avisos detectados, avisos válidos,
avisos descartados, duplicados, OCR promedio, Parser accuracy,
Knowledge usage, Validator acceptance, Certification rate,
errores, warnings, tiempo promedio.

Fully serializable.
"""

from typing import Any

CANONICAL_FIELDS = [
    "expediente", "finca", "precio_base", "fecha_remate",
    "demandante", "demandado", "fianza_porcentaje", "minimo_porcentaje",
]

VALID_DECISIONS = {"VALID", "CERTIFIED"}
DISCOUNTED_DECISIONS = {"INVALID", "REJECTED", "DUPLICATED", "LIKELY_DUPLICATED"}


def _cert_decision(result: dict) -> str:
    cert = result.get("certification", {})
    if not isinstance(cert, dict):
        return ""
    avisos = cert.get("all_avisos") or []
    if avisos:
        return str(avisos[0].get("decision", ""))
    return ""


def _validation_decision(result: dict) -> str:
    validation = result.get("validation", {})
    if not isinstance(validation, dict):
        return ""
    return str(validation.get("decision", ""))


class PipelineMetrics:
    def __init__(self) -> None:
        self.results: list[dict] = []

    def collect(self, results: list[dict]) -> dict:
        self.results = list(results)
        return self.to_dict()

    def to_dict(self) -> dict:
        total = len(self.results)
        if total == 0:
            return {
                "documentos_procesados": 0,
                "avisos_detectados": 0,
                "avisos_validos": 0,
                "avisos_descartados": 0,
                "duplicados": 0,
                "ocr_promedio": 0.0,
                "parser_accuracy": 0.0,
                "knowledge_usage": 0.0,
                "validator_acceptance": 0.0,
                "certification_rate": 0.0,
                "errores": 0,
                "warnings": 0,
                "tiempo_promedio_ms": 0.0,
            }

        avisos_detectados = sum(
            int(r.get("stages", {}).get("segmentation", {}).get("metrics", {}).get("avisos_detected", 0))
            if isinstance(r.get("stages"), dict) else 0
            for r in self.results
        )
        avisos_validos = sum(
            1 for r in self.results
            if _cert_decision(r) in VALID_DECISIONS
            or _validation_decision(r) in VALID_DECISIONS
        )
        avisos_descartados = sum(
            1 for r in self.results
            if _cert_decision(r) in DISCOUNTED_DECISIONS
            or _validation_decision(r) in DISCOUNTED_DECISIONS
        )
        duplicados = sum(
            1 for r in self.results
            if isinstance(r.get("validation"), dict)
            and r["validation"].get("duplicate_info") is not None
        )
        ocr_scores = [
            float(r.get("stages", {}).get("ocr", {}).get("metrics", {}).get("avg_confidence", 0.0))
            if isinstance(r.get("stages"), dict) else 0.0
            for r in self.results
        ]
        ocr_promedio = round(sum(ocr_scores) / total, 3)

        accuracy_per_doc = []
        knowledge_usage_docs = 0
        validator_scores = []
        for r in self.results:
            fields = r.get("fields", {})
            if isinstance(fields, dict):
                found = sum(
                    1 for f in CANONICAL_FIELDS
                    if f in fields and isinstance(fields[f], dict)
                    and fields[f].get("status") == "FOUND"
                )
                accuracy_per_doc.append(found / len(CANONICAL_FIELDS))
            knowledge = r.get("stages", {}).get("knowledge", {}).get("metrics", {})
            if isinstance(knowledge, dict) and knowledge.get("rules_applied", 0) > 0:
                knowledge_usage_docs += 1
            validation = r.get("validation", {})
            if isinstance(validation, dict) and isinstance(validation.get("score"), (int, float)):
                validator_scores.append(float(validation["score"]))

        parser_accuracy = round(sum(accuracy_per_doc) / max(len(accuracy_per_doc), 1) * 100, 2)
        knowledge_usage = round(knowledge_usage_docs / total * 100, 2)
        validator_acceptance = round(
            sum(validator_scores) / max(len(validator_scores), 1) * 100, 2
        ) if validator_scores else 0.0
        certification_rate = round(avisos_validos / total * 100, 2)

        errores = sum(len(r.get("errors", [])) if isinstance(r.get("errors"), list) else 0 for r in self.results)
        warnings = sum(len(r.get("warnings", [])) if isinstance(r.get("warnings"), list) else 0 for r in self.results)
        tiempos = [float(r.get("total_time_ms", 0.0)) for r in self.results if r.get("total_time_ms") is not None]

        return {
            "documentos_procesados": total,
            "avisos_detectados": avisos_detectados,
            "avisos_validos": avisos_validos,
            "avisos_descartados": avisos_descartados,
            "duplicados": duplicados,
            "ocr_promedio": ocr_promedio,
            "parser_accuracy": parser_accuracy,
            "knowledge_usage": knowledge_usage,
            "validator_acceptance": validator_acceptance,
            "certification_rate": certification_rate,
            "errores": errores,
            "warnings": warnings,
            "tiempo_promedio_ms": round(sum(tiempos) / max(len(tiempos), 1), 2),
        }


def collect_metrics(results: list[dict]) -> dict:
    return PipelineMetrics().collect(results)
