from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
import json
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))


@dataclass
class GoldenRecord:
    id: str
    expediente: str
    demandante: str
    demandado: Optional[str]
    base: float
    fianza_porcentaje: Optional[float] = None
    minimo_porcentaje: Optional[float] = None
    finca_matr: Optional[str] = None
    fecha: Optional[str] = None
    provincia: Optional[str] = None
    lugar: Optional[str] = None
    proceso: Optional[str] = None
    categoria: Optional[str] = None
    descripcion: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "expediente": self.expediente,
            "demandante": self.demandante,
        }
        if self.demandado is not None:
            d["demandado"] = self.demandado
        d["base"] = self.base
        if self.fianza_porcentaje is not None:
            d["fianza_porcentaje"] = self.fianza_porcentaje
        if self.minimo_porcentaje is not None:
            d["minimo_porcentaje"] = self.minimo_porcentaje
        if self.finca_matr is not None:
            d["finca_matr"] = self.finca_matr
        if self.fecha is not None:
            d["fecha"] = self.fecha
        if self.provincia is not None:
            d["provincia"] = self.provincia
        if self.lugar is not None:
            d["lugar"] = self.lugar
        if self.proceso is not None:
            d["proceso"] = self.proceso
        if self.categoria is not None:
            d["categoria"] = self.categoria
        if self.descripcion is not None:
            d["descripcion"] = self.descripcion
        if self.extra:
            d["extra"] = self.extra
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "GoldenRecord":
        expediente = d.get("expediente", "")
        return cls(
            id=d.get("id", expediente),
            expediente=expediente,
            demandante=d.get("demandante", ""),
            demandado=d.get("demandado"),
            base=float(d.get("base", 0)),
            fianza_porcentaje=d.get("fianza_porcentaje"),
            minimo_porcentaje=d.get("minimo_porcentaje"),
            finca_matr=d.get("finca_matr"),
            fecha=d.get("fecha"),
            provincia=d.get("provincia"),
            lugar=d.get("lugar"),
            proceso=d.get("proceso"),
            categoria=d.get("categoria"),
            descripcion=d.get("descripcion"),
            extra={k: v for k, v in d.items() if k not in (
                "id", "expediente", "demandante", "demandado", "base",
                "fianza_porcentaje", "minimo_porcentaje", "finca_matr",
                "fecha", "provincia", "lugar", "proceso", "categoria", "descripcion",
            )},
        )


@dataclass
class TestSuite:
    id: str
    name: str
    doc_type: str
    pais: str
    document_id: int
    files: list[str]
    expected_count: int
    critical_fields: list[str]
    expected_avisos: list[GoldenRecord]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.doc_type,
            "pais": self.pais,
            "document_id": self.document_id,
            "files": self.files,
            "expected_count": self.expected_count,
            "critical_fields": self.critical_fields,
            "expected_avisos": [a.to_dict() for a in self.expected_avisos],
        }


class GoldenDatasetManager:
    DEFAULT_PATH = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "..",
        "evaluation", "golden_dataset", "records.json"
    ))

    def __init__(self, path: Optional[str] = None):
        self.path = path or self.DEFAULT_PATH
        self._data: Optional[dict] = None
        self._suites: list[TestSuite] = []

    def load(self) -> dict:
        if self._data is None:
            with open(self.path, encoding="utf-8") as f:
                self._data = json.load(f)
        return self._data

    def get_suites(self) -> list[TestSuite]:
        if not self._suites:
            data = self.load()
            for raw in data.get("test_suites", []):
                avisos = [GoldenRecord.from_dict(a) for a in raw.get("expected_avisos", [])]
                self._suites.append(TestSuite(
                    id=raw["id"],
                    name=raw["name"],
                    doc_type=raw["type"],
                    pais=raw["pais"],
                    document_id=raw["document_id"],
                    files=raw["files"],
                    expected_count=raw["expected_count"],
                    critical_fields=raw["critical_fields"],
                    expected_avisos=avisos,
                ))
        return self._suites

    def get_suite(self, suite_id: str) -> Optional[TestSuite]:
        for s in self.get_suites():
            if s.id == suite_id:
                return s
        return None

    def get_all_records(self) -> list[GoldenRecord]:
        records = []
        for s in self.get_suites():
            records.extend(s.expected_avisos)
        return records

    def get_record(self, record_id: str) -> Optional[GoldenRecord]:
        for r in self.get_all_records():
            if r.id == record_id:
                return r
        return None

    def get_records_by_country(self, pais: str) -> list[GoldenRecord]:
        records = []
        for s in self.get_suites():
            if s.pais == pais:
                records.extend(s.expected_avisos)
        return records

    def validate(self) -> dict:
        data = self.load()
        suites = self.get_suites()

        issues = []
        total_records = 0

        for s in suites:
            total_records += len(s.expected_avisos)
            if len(s.expected_avisos) < s.expected_count:
                pass
            elif len(s.expected_avisos) > s.expected_count:
                issues.append(
                    f"Suite '{s.id}': expected_count={s.expected_count} "
                    f"but found {len(s.expected_avisos)} records"
                )
            for r in s.expected_avisos:
                if not r.expediente:
                    issues.append(f"Suite '{s.id}', record '{r.id}': missing expediente")
                if not r.demandante:
                    issues.append(f"Suite '{s.id}', record '{r.id}': missing demandante")
                if r.base is None or r.base <= 0:
                    issues.append(f"Suite '{s.id}', record '{r.id}': invalid base={r.base}")

        for suite in data.get("test_suites", []):
            for fname in suite.get("files", []):
                upload_dir = os.path.abspath(os.path.join(
                    os.path.dirname(__file__), "..", "..", "..", "..",
                    "backend", "data", "uploads"
                ))
                if not os.path.exists(os.path.join(upload_dir, fname)):
                    issues.append(
                        f"Suite '{suite['id']}': file '{fname}' not found in data/uploads/"
                    )

        return {
            "valid": len(issues) == 0,
            "total_records": total_records,
            "total_suites": len(suites),
            "issues": issues,
            "version": data.get("version", "1.0"),
            "created": data.get("created", ""),
        }

    def get_critical_fields(self) -> list[str]:
        all_fields = set()
        for s in self.get_suites():
            all_fields.update(s.critical_fields)
        return sorted(all_fields)

    def get_field_coverage(self) -> dict[str, dict]:
        all_records = self.get_all_records()
        fields = ["expediente", "demandante", "demandado", "base",
                   "fianza_porcentaje", "minimo_porcentaje", "finca_matr",
                   "fecha", "provincia", "lugar", "proceso", "categoria",
                   "descripcion"]
        coverage = {}
        for f in fields:
            present = sum(1 for r in all_records if getattr(r, f, None) is not None)
            coverage[f] = {
                "present": present,
                "total": len(all_records),
                "coverage_pct": round(present / max(len(all_records), 1) * 100, 1),
            }
        return coverage
