"""FASE 8.5 — Audit Trail.

Tracks field-level provenance through the pipeline: which source
(parser, knowledge, OCR, normalization) contributed each field value,
with confidence scores and timestamps.
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
class FieldProvenance:
    field_name: str
    v2_field_name: str
    value: Any
    source: str
    confidence: float
    stage: str
    timestamp: str = ""
    normalization: dict = field(default_factory=dict)
    evidence: list = field(default_factory=list)
    raw_value: Any = None
    normalized_value: Any = None
    status: str = "FOUND"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "field_name": self.field_name,
            "v2_field_name": self.v2_field_name,
            "value": self.value,
            "raw_value": self.raw_value,
            "normalized_value": self.normalized_value,
            "source": self.source,
            "stage": self.stage,
            "confidence": self.confidence,
            "status": self.status,
            "timestamp": self.timestamp,
            "normalization": self.normalization,
            "evidence": self.evidence,
            "warnings": self.warnings,
        }


@dataclass
class AuditTrail:
    document_id: str
    country: str
    source_type: str
    pipeline_version: str
    timestamp: str
    fields: list[FieldProvenance] = field(default_factory=list)
    stage_results: dict = field(default_factory=dict)
    total_time_ms: float = 0.0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_field(self, prov: FieldProvenance):
        self.fields.append(prov)

    def get_field(self, field_name: str) -> Optional[FieldProvenance]:
        for f in self.fields:
            if f.field_name == field_name or f.v2_field_name == field_name:
                return f
        return None

    def get_by_source(self, source: str) -> list[FieldProvenance]:
        return [f for f in self.fields if f.source == source]

    def get_by_stage(self, stage: str) -> list[FieldProvenance]:
        return [f for f in self.fields if f.stage == stage]

    def to_dict(self) -> dict:
        return {
            "document_id": self.document_id,
            "country": self.country,
            "source_type": self.source_type,
            "pipeline_version": self.pipeline_version,
            "timestamp": self.timestamp,
            "total_time_ms": round(self.total_time_ms, 2),
            "fields": [f.to_dict() for f in self.fields],
            "stage_results": self.stage_results,
            "errors": self.errors,
            "warnings": self.warnings,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def summary(self) -> dict:
        sources = {}
        for f in self.fields:
            sources[f.source] = sources.get(f.source, 0) + 1

        stages = {}
        for f in self.fields:
            stages[f.stage] = stages.get(f.stage, 0) + 1

        avg_conf = sum(f.confidence for f in self.fields) / max(len(self.fields), 1)

        return {
            "total_fields": len(self.fields),
            "sources": sources,
            "stages": stages,
            "avg_confidence": round(avg_conf, 4),
            "errors": len(self.errors),
            "warnings": len(self.warnings),
        }


class AuditTrailBuilder:
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

    def __init__(self):
        self.trails: dict[str, AuditTrail] = {}

    def create_trail(self, document_id: str, country: str, source_type: str,
                     pipeline_version: str = "8.0.0") -> AuditTrail:
        trail = AuditTrail(
            document_id=document_id,
            country=country,
            source_type=source_type,
            pipeline_version=pipeline_version,
            timestamp=datetime.utcnow().isoformat(),
        )
        self.trails[document_id] = trail
        return trail

    def extract_from_pipeline_result(self, pipeline_result: dict, document_id: str) -> AuditTrail:
        trail = AuditTrail(
            document_id=document_id,
            country=pipeline_result.get("country", "PA"),
            source_type=pipeline_result.get("source_type", ""),
            pipeline_version=pipeline_result.get("version", "8.0.0"),
            timestamp=pipeline_result.get("timestamp", datetime.utcnow().isoformat()),
            total_time_ms=pipeline_result.get("total_time_ms", 0),
            errors=pipeline_result.get("errors", []),
            warnings=pipeline_result.get("warnings", []),
            stage_results=pipeline_result.get("stages", {}),
        )

        fields = pipeline_result.get("fields", {})
        for v1_name, v2_name in self.V1_TO_V2_MAP.items():
            fdata = fields.get(v2_name, {})
            if isinstance(fdata, dict) and fdata.get("value") is not None:
                prov = FieldProvenance(
                    field_name=v1_name,
                    v2_field_name=v2_name,
                    value=fdata.get("value"),
                    raw_value=fdata.get("value"),
                    normalized_value=fdata.get("normalized"),
                    source=fdata.get("source", "parser"),
                    confidence=fdata.get("confidence", 0.0),
                    stage="final",
                    status=fdata.get("status", "FOUND"),
                    timestamp=datetime.utcnow().isoformat(),
                    normalization=fdata.get("normalization", {}),
                    evidence=fdata.get("evidence", []),
                    warnings=[],
                )
                trail.add_field(prov)

        self.trails[document_id] = trail
        return trail

    def get_trail(self, document_id: str) -> Optional[AuditTrail]:
        return self.trails.get(document_id)

    def save_trail(self, trail: AuditTrail, output_dir: str):
        path = Path(output_dir)
        path.mkdir(parents=True, exist_ok=True)
        file_path = path / f"{trail.document_id}_audit.json"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(trail.to_json())
