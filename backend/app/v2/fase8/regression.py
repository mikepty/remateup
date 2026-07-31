"""FASE 8.2 — Regression Framework.

Runs the V2 pipeline against the golden dataset and compares results
to detect any regression in extraction accuracy.
"""

import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from backend.app.v2.fase8.golden_dataset import GoldenDatasetManager, GoldenRecord
from backend.app.v2.parser.factory import ParserFactory
from backend.app.v2.parser.context import ParserContext
from backend.app.v2.parser.result import ParseResult


COMPARISON_FIELDS = [
    "expediente", "demandante", "demandado", "base",
    "fianza_porcentaje", "minimo_porcentaje", "finca_matr",
    "fecha", "provincia", "lugar", "proceso", "categoria",
]

V1_TO_V2_FIELD_MAP = {
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


def normalize_value(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip().upper()
    for a, b in (("Á", "A"), ("É", "E"), ("Í", "I"), ("Ó", "O"), ("Ú", "U"), ("Ñ", "N")):
        s = s.replace(a, b)
    s = s.replace(".", "").replace(",", "").replace("$", "").replace(" ", "")
    return s


def values_match(expected: Any, actual: Any, strict: bool = False) -> bool:
    if expected is None and actual is None:
        return True
    if expected is None or actual is None:
        return False
    if strict:
        return str(expected).strip() == str(actual).strip()
    return normalize_value(expected) == normalize_value(actual)


@dataclass
class FieldResult:
    field_name: str
    expected: Any
    actual: Any
    match: bool
    normalized_match: bool
    v2_field_name: str

    def to_dict(self) -> dict:
        return {
            "field": self.field_name,
            "v2_field": self.v2_field_name,
            "expected": self.expected,
            "actual": self.actual,
            "match": self.match,
            "normalized_match": self.normalized_match,
        }


@dataclass
class AvisoRegressionResult:
    record_id: str
    expediente: str
    field_results: list[FieldResult] = field(default_factory=list)
    overall_match: bool = False
    match_score: float = 0.0
    processing_time_ms: float = 0.0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "record_id": self.record_id,
            "expediente": self.expediente,
            "fields": [
                {
                    "field": fr.field_name,
                    "v2_field": fr.v2_field_name,
                    "expected": fr.expected,
                    "actual": fr.actual,
                    "match": fr.match,
                    "normalized_match": fr.normalized_match,
                }
                for fr in self.field_results
            ],
            "overall_match": self.overall_match,
            "match_score": self.match_score,
            "processing_time_ms": round(self.processing_time_ms, 2),
            "errors": self.errors,
        }


@dataclass
class RegressionReport:
    timestamp: str
    total_records: int
    total_matches: int
    regressions: list[AvisoRegressionResult]
    summary: dict[str, Any]
    overall_match_rate: float
    avg_processing_time_ms: float

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "total_records": self.total_records,
            "total_matches": self.total_matches,
            "overall_match_rate": self.overall_match_rate,
            "avg_processing_time_ms": round(self.avg_processing_time_ms, 2),
            "summary": self.summary,
            "regressions": [r.to_dict() for r in self.regressions],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


class RegressionFramework:
    def __init__(self, golden_path: Optional[str] = None):
        self.golden = GoldenDatasetManager(golden_path)
        self.factory = ParserFactory()
        self.results: list[AvisoRegressionResult] = []

    def _build_test_text(self, record: GoldenRecord) -> str:
        lines = ["AVISO DE REMATE"]
        if record.expediente:
            lines.append(f"EXPEDIENTE: {record.expediente}")
        if record.demandante:
            lines.append(f"DEMANDANTE: {record.demandante}")
        if record.demandado:
            lines.append(f"DEMANDADO: {record.demandado}")
        if record.finca_matr:
            lines.append(f"FINCA: {record.finca_matr}")
            lines.append(f"MATRICULA INMOBILIARIA: {record.finca_matr}")
        if record.base:
            lines.append(f"BASE: {record.base}")
            lines.append(f"PRECIO BASE: ${record.base:,.2f}")
        if record.fianza_porcentaje:
            lines.append(f"FIANZA: {record.fianza_porcentaje}%")
        if record.minimo_porcentaje:
            lines.append(f"MINIMO: {record.minimo_porcentaje}%")
        if record.fecha:
            lines.append(f"FECHA: {record.fecha}")
        if record.lugar:
            lines.append(f"LUGAR: {record.lugar}")
        if record.proceso:
            lines.append(f"PROCESO: {record.proceso}")
        if record.provincia:
            lines.append(f"PROVINCIA: {record.provincia}")
        if record.categoria:
            lines.append(f"CATEGORIA: {record.categoria}")
        if record.descripcion:
            lines.append(f"DESCRIPCION: {record.descripcion}")
        return "\n".join(lines)

    def run_regression(self, country: Optional[str] = None, max_records: Optional[int] = None) -> RegressionReport:
        records = self.golden.get_all_records()
        if country:
            records = [r for r in records if self._find_suite_country(r) == country]

        if max_records:
            records = records[:max_records]

        results: list[AvisoRegressionResult] = []
        total_matches = 0

        for record in records:
            r = self._test_record(record)
            results.append(r)
            if r.overall_match:
                total_matches += 1

        overall_match_rate = round(total_matches / max(len(results), 1) * 100, 2)
        avg_time = round(
            sum(r.processing_time_ms for r in results) / max(len(results), 1), 2
        )

        field_summary = {}
        for r in results:
            for fr in r.field_results:
                if fr.field_name not in field_summary:
                    field_summary[fr.field_name] = {"matches": 0, "total": 0}
                field_summary[fr.field_name]["total"] += 1
                if fr.match:
                    field_summary[fr.field_name]["matches"] += 1

        for fname, stats in field_summary.items():
            stats["accuracy"] = round(stats["matches"] / max(stats["total"], 1) * 100, 1)

        summary = {
            "total_records": len(results),
            "total_matches": total_matches,
            "overall_match_rate": overall_match_rate,
            "avg_processing_time_ms": avg_time,
            "field_accuracy": field_summary,
            "by_country": self._summarize_by_country(results),
        }

        return RegressionReport(
            timestamp=datetime.utcnow().isoformat(),
            total_records=len(results),
            total_matches=total_matches,
            regressions=results,
            summary=summary,
            overall_match_rate=overall_match_rate,
            avg_processing_time_ms=avg_time,
        )

    def _find_suite_country(self, record: GoldenRecord) -> str:
        suites = self.golden.get_suites()
        for s in suites:
            for r in s.expected_avisos:
                if r.id == record.id:
                    return s.pais
        return "PA"

    def _test_record(self, record: GoldenRecord) -> AvisoRegressionResult:
        country = self._find_suite_country(record)
        text = self._build_test_text(record)

        start = time.perf_counter()
        field_results: list[FieldResult] = []
        errors: list[str] = []

        try:
            parser = self.factory.get_parser(country.upper(), "REMATE")
            if parser is None:
                errors.append(f"No parser for country {country}")
            else:
                ctx = ParserContext(country=country.upper(), document_type="REMATE", text=text)
                parsed = parser.parse(ctx)

                for v1_field, v2_field in V1_TO_V2_FIELD_MAP.items():
                    expected = getattr(record, v1_field, None)
                    if expected is None:
                        continue

                    pr: Optional[ParseResult] = parsed.get(v2_field)
                    actual = pr.value if pr and pr.is_found else None

                    match = values_match(expected, actual, strict=False)
                    norm_match = values_match(expected, actual, strict=True)

                    field_results.append(FieldResult(
                        field_name=v1_field,
                        expected=expected,
                        actual=actual,
                        match=match,
                        normalized_match=norm_match,
                        v2_field_name=v2_field,
                    ))
        except Exception as e:
            errors.append(str(e))

        elapsed_ms = (time.perf_counter() - start) * 1000

        matched_fields = sum(1 for fr in field_results if fr.match)
        total_fields = len(field_results)
        match_score = round(matched_fields / max(total_fields, 1), 4) if total_fields else 0.0
        overall_match = matched_fields == total_fields and total_fields > 0

        return AvisoRegressionResult(
            record_id=record.id,
            expediente=record.expediente,
            field_results=field_results,
            overall_match=overall_match,
            match_score=match_score,
            processing_time_ms=elapsed_ms,
            errors=errors,
        )

    def _summarize_by_country(self, results: list[AvisoRegressionResult]) -> dict:
        countries = {}
        for r in results:
            country = self._find_suite_country(
                self.golden.get_record(r.record_id) or GoldenRecord(
                    id=r.record_id, expediente=r.expediente, demandante="", demandado=None, base=0
                )
            )
            if country not in countries:
                countries[country] = {"matches": 0, "total": 0}
            countries[country]["total"] += 1
            if r.overall_match:
                countries[country]["matches"] += 1

        return {
            c: {
                "match_rate": round(d["matches"] / max(d["total"], 1) * 100, 1),
                "matches": d["matches"],
                "total": d["total"],
            }
            for c, d in countries.items()
        }

    def save_report(self, report: RegressionReport, output_path: str):
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(report.to_json())
