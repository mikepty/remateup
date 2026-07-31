"""FASE 8.20 — Canonical Schema Completion & Final Architecture Audit.

Architecture-only audit. NO new parsers, NO OCR changes, NO knowledge rules,
NO validator changes, NO regexes, NO new fields. Verifies for EVERY
FieldDefinition: Schema, Parser, Knowledge, Validator, Normalizer, Database,
API, Frontend, Export, Golden Dataset, producer, consumer, alias, correct
type, correct format, valid dependencies, documentation.

Adds automatic detection of: orphan fields, missing consumers, missing
producers, ambiguous aliases, duplicate aliases, incompatible types,
incompatible formats, circular dependencies, never-certified fields and
never-evaluated fields.
"""

import json
import os
import re
from typing import Any, Optional

from backend.app.v2.schema.coverage import CoverageAnalyzer
from backend.app.v2.schema.field_registry import REGISTRY
from backend.app.v2.schema.models import FieldDefinition

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

DB_COMPAT = {
    "text": {"String", "Text"},
    "name": {"String", "Text"},
    "location": {"String", "Text"},
    "date": {"String", "Text"},
    "number": {"Float", "Integer", "Numeric", "REAL", "INTEGER"},
    "currency": {"Float", "Integer", "Numeric", "REAL", "INTEGER"},
}

FORMAT_REGEX = {
    "date": re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    "number": re.compile(r"^-?\d+(\.\d+)?$"),
    "currency": re.compile(r"^-?\d+(\.\d+)?$"),
}

V1_TO_V2_PAIRS = {
    ("base", "precio_base"),
    ("finca_matr", "finca"),
    ("fecha", "fecha_remate"),
}


class StackProbe:
    """Reads the REAL field catalogs of database, API, frontend and export."""

    def database_fields(self) -> dict[str, str]:
        try:
            from backend.app.models import Aviso
            result = {}
            for col in Aviso.__table__.columns:
                raw = str(col.type).upper()
                if raw.startswith("VARCHAR"):
                    raw = "String"
                elif raw == "TEXT":
                    raw = "Text"
                elif raw == "FLOAT":
                    raw = "Float"
                elif raw == "INTEGER":
                    raw = "Integer"
                elif raw == "BOOLEAN":
                    raw = "Boolean"
                elif raw == "NUMERIC":
                    raw = "Numeric"
                result[col.name] = raw
            return result
        except Exception:
            return {}

    def api_fields(self) -> list[str]:
        try:
            path = os.path.join(REPO_ROOT, "backend", "app", "main.py")
            code = open(path, encoding="utf-8").read()
            m = re.search(r"campos_permitidos\s*=\s*\[(.*?)\]", code, re.DOTALL)
            if not m:
                return []
            return re.findall(r'"(\w+)"', m.group(1))
        except Exception:
            return []

    def frontend_fields(self) -> list[str]:
        try:
            path = os.path.join(REPO_ROOT, "frontend", "public", "index.html")
            html = open(path, encoding="utf-8").read()
            ids = set(re.findall(r'id=["\'](\w+)["\']', html))
            names = set(re.findall(r'name=["\'](\w+)["\']', html))
            fields = set()
            for f in ids | names:
                if f.startswith("ed_"):
                    fields.add(f[3:])
                elif any(f == known for known in (
                    "base", "fianza_porcentaje", "minimo_porcentaje", "finca_matr",
                    "expediente", "demandante", "demandado", "fecha", "hora",
                )):
                    fields.add(f)
            return sorted(fields)
        except Exception:
            return []

    def export_fields(self) -> list[str]:
        try:
            path = os.path.join(REPO_ROOT, "backend", "app", "routers", "exports.py")
            code = open(path, encoding="utf-8").read()
            fields = set(re.findall(r'\ba\.([a-z_]+)\b', code))
            return sorted(fields)
        except Exception:
            return []


class CompletionAuditor:
    """Runs the 17 existence checks per field plus the 10 new validations."""

    def __init__(self, registry=None, analyzer: Optional[CoverageAnalyzer] = None):
        self.registry = registry or REGISTRY
        self.analyzer = analyzer or CoverageAnalyzer(self.registry)
        self.probe = StackProbe()
        self._db_fields = self.probe.database_fields()
        self._api_fields = set(self.probe.api_fields())
        self._frontend_fields = set(self.probe.frontend_fields())
        self._export_fields = set(self.probe.export_fields())
        self._golden_fields = self._load_golden_fields()

    def _load_golden_fields(self) -> dict[str, list]:
        try:
            from backend.app.v2.fase8.golden_dataset import GoldenDatasetManager
            manager = GoldenDatasetManager()
            return {
                f: [getattr(r, f) for r in manager.get_all_records()
                    if getattr(r, f, None) is not None]
                for f in manager.get_field_coverage().keys()
            }
        except Exception:
            return {}

    # ─── 17 checks per field ────────────────────────────────────────────────

    def check_field(self, field_name: str) -> dict:
        definition = self.registry.resolve(field_name)
        if definition is None:
            return {
                "field": field_name, "in_schema": False,
                "in_parser": False, "in_knowledge": False, "in_validator": False,
                "in_normalizer": False, "in_database": False, "in_api": False,
                "in_frontend": False, "in_export": False, "in_golden": False,
                "has_producer": False, "has_consumer": False, "has_alias": False,
                "type_ok": True, "format_ok": True, "deps_ok": True,
                "has_documentation": False,
            }
        coverage = self.analyzer.analyze_field(field_name)
        in_parser = coverage.by_module.get("parser", False)
        in_knowledge = coverage.by_module.get("knowledge", False)
        in_validator = coverage.by_module.get("validator", False)
        in_normalizer = coverage.by_module.get("normalizer", False)
        has_producer = in_parser or in_knowledge or self._has_equivalent_producer(definition)
        consumers = [
            m for m in ("validator", "normalizer",
                        "certification", "regression")
            if coverage.by_module.get(m)
        ]
        in_db = field_name in self._db_fields or any(
            a in self._db_fields for a in definition.aliases
        )
        in_api = field_name in self._api_fields or any(
            a in self._api_fields for a in definition.aliases
        )
        in_frontend = field_name in self._frontend_fields or any(
            a in self._frontend_fields for a in definition.aliases
        )
        in_export = field_name in self._export_fields or any(
            a in self._export_fields for a in definition.aliases
        )
        in_golden = coverage.by_module.get("golden_dataset", False)
        type_ok = self.check_type(definition) == []
        format_ok = self.check_format(definition) == []
        deps_ok = self._check_deps(definition) == []
        has_doc = bool(definition.description.strip()) and bool(definition.examples)
        return {
            "field": field_name,
            "in_schema": True,
            "in_parser": in_parser,
            "in_knowledge": in_knowledge,
            "in_validator": in_validator,
            "in_normalizer": in_normalizer,
            "in_database": in_db,
            "in_api": in_api,
            "in_frontend": in_frontend,
            "in_export": in_export,
            "in_golden": in_golden,
            "has_producer": has_producer,
            "has_consumer": len(consumers) > 0 or in_db or in_api,
            "has_alias": len(definition.aliases) > 0,
            "type_ok": type_ok,
            "format_ok": format_ok,
            "deps_ok": deps_ok,
            "has_documentation": has_doc,
        }

    def check_all(self) -> list[dict]:
        return [self.check_field(f) for f in self.registry.field_names()]

    def _has_equivalent_producer(self, definition: FieldDefinition) -> bool:
        for alias in definition.aliases:
            target = self.registry.resolve(alias)
            if target and target.field_name != definition.field_name:
                if self.analyzer.analyze_field(target.field_name).by_module.get("parser"):
                    return True
        return False

    # ─── type conflicts (validation 6) ──────────────────────────────────────

    def check_type(self, definition: FieldDefinition) -> list[dict]:
        conflicts = []
        db_type = self._db_fields.get(definition.field_name)
        if db_type is None:
            for alias in definition.aliases:
                if alias in self._db_fields:
                    db_type = self._db_fields[alias]
                    break
        if db_type and definition.data_type in DB_COMPAT:
            if not any(t in db_type for t in DB_COMPAT[definition.data_type]):
                conflicts.append({
                    "field": definition.field_name, "layer": "database",
                    "expected": definition.data_type, "found": db_type,
                })
        if definition.field_name in self._golden_fields:
            for value in self._golden_fields[definition.field_name][:10]:
                if isinstance(value, (int, float)) and definition.data_type in ("text", "name", "location"):
                    conflicts.append({
                        "field": definition.field_name, "layer": "golden_dataset",
                        "expected": definition.data_type,
                        "found": type(value).__name__,
                    })
                    break
        return conflicts

    def detect_type_conflicts(self) -> list[dict]:
        result = []
        for d in self.registry.all():
            result.extend(self.check_type(d))
        return result

    # ─── format conflicts (validation 7) ────────────────────────────────────

    def check_format(self, definition: FieldDefinition) -> list[dict]:
        if definition.data_type not in FORMAT_REGEX:
            return []
        pattern = FORMAT_REGEX[definition.data_type]
        conflicts = []
        for example in definition.examples:
            if not pattern.match(str(example)):
                conflicts.append({
                    "field": definition.field_name, "layer": "examples",
                    "expected_format": "ISO YYYY-MM-DD" if definition.data_type == "date"
                    else "numeric", "found": str(example),
                })
        for value in self._golden_fields.get(definition.field_name, [])[:10]:
            if isinstance(value, (int, float)):
                continue
            if not pattern.match(str(value)):
                conflicts.append({
                    "field": definition.field_name, "layer": "golden_dataset",
                    "expected_format": "ISO YYYY-MM-DD" if definition.data_type == "date"
                    else "numeric", "found": str(value),
                })
        return conflicts

    def detect_format_conflicts(self) -> list[dict]:
        result = []
        for d in self.registry.all():
            result.extend(self.check_format(d))
        return result

    # ─── circular dependencies (validation 8) ───────────────────────────────

    def _check_deps(self, definition: FieldDefinition) -> list[dict]:
        problems = []
        for dep in definition.depends_on:
            if self.registry.resolve(dep) is None:
                problems.append({
                    "field": definition.field_name,
                    "depends_on": dep,
                    "problem": "dependency not defined in the schema",
                })
        return problems

    def detect_circular_dependencies(self) -> list[dict]:
        circular = []
        by_name = {d.field_name: d for d in self.registry.all()}
        for name, definition in by_name.items():
            for dep in definition.depends_on:
                if dep in by_name and name in by_name[dep].depends_on:
                    circular.append({
                        "a": name, "b": dep,
                        "type": "dependencia_circular",
                        "problem": f"field '{name}' depends on '{dep}' and '{dep}' depends on '{name}'",
                    })
        for a_name, a in by_name.items():
            for b_name, b in by_name.items():
                if a_name < b_name and a_name in b.aliases and b_name in a.aliases:
                    circular.append({
                        "a": a_name, "b": b_name,
                        "type": "alias_circular",
                        "problem": f"'{a_name}' and '{b_name}' are mutual aliases (V1/V2 pair)",
                    })
        return circular

    # ─── alias ambiguity (validation 4) ─────────────────────────────────────

    def detect_ambiguous_aliases(self) -> list[dict]:
        alias_owners: dict[str, list[str]] = {}
        for d in self.registry.all():
            for alias in d.aliases:
                alias_owners.setdefault(alias, []).append(d.field_name)
        return [
            {"alias": alias, "owners": owners,
             "problem": f"alias '{alias}' is declared by more than one field"}
            for alias, owners in sorted(alias_owners.items())
            if len(set(owners)) > 1
        ]

    # ─── duplicate aliases (validation 5) ───────────────────────────────────

    def detect_duplicate_aliases(self) -> list[dict]:
        result = []
        for d in self.registry.all():
            seen = set()
            for alias in d.aliases:
                if alias in seen:
                    result.append({"field": d.field_name, "alias": alias,
                                   "problem": f"alias '{alias}' repeated in '{d.field_name}'"})
                seen.add(alias)
        all_aliases: dict[str, list[str]] = {}
        for d in self.registry.all():
            for alias in d.aliases:
                all_aliases.setdefault(alias, []).append(d.field_name)
        for alias, owners in sorted(all_aliases.items()):
            if len(set(owners)) > 1:
                result.append({"field": ", ".join(sorted(set(owners))), "alias": alias,
                               "problem": f"alias '{alias}' shared by multiple fields"})
        return result

    def detect_invalid_aliases(self) -> list[dict]:
        invalid = self.detect_ambiguous_aliases() + self.detect_duplicate_aliases()
        filtered = []
        for issue in invalid:
            owner_names = {f.strip() for f in issue["field"].split(",")}
            pair_ok = len(owner_names) == 2 and (
                tuple(sorted(owner_names)) in V1_TO_V2_PAIRS
                or tuple(sorted(owner_names)) in {tuple(sorted(p)) for p in V1_TO_V2_PAIRS}
            )
            if not pair_ok:
                filtered.append(issue)
        return filtered

    # ─── orphan / unused / producer / consumer (validations 1-3) ────────────

    def detect_orphan_fields(self) -> list[str]:
        orphans = []
        for check in self.check_all():
            if not any((check[k] for k in (
                "in_parser", "in_knowledge", "in_validator", "in_normalizer",
                "in_database", "in_api", "in_frontend", "in_export", "in_golden",
            ))):
                orphans.append(check["field"])
        return orphans

    def detect_missing_consumers(self) -> list[str]:
        missing = []
        for check in self.check_all():
            if check["has_producer"] and not check["has_consumer"]:
                missing.append(check["field"])
        return missing

    def detect_missing_producers(self) -> list[str]:
        missing = []
        for check in self.check_all():
            definition = self.registry.resolve(check["field"])
            if definition and definition.required and not check["has_producer"]:
                missing.append(check["field"])
        return missing

    # ─── never certified / never evaluated (validations 9-10) ───────────────

    def certified_fields(self) -> list[str]:
        return [c["field"] for c in self.check_all()
                if self.score_field(c["field"]) >= 100]

    def never_certified_fields(self) -> list[str]:
        all_fields = self.registry.field_names()
        return sorted(set(all_fields) - set(self.certified_fields()))

    def _evaluated_fields(self) -> set:
        from backend.app.v2.fase8.regression import COMPARISON_FIELDS
        evaluated = set(COMPARISON_FIELDS)
        evaluated.update(self._golden_fields.keys())
        for v1_name, v2_name in (
            ("base", "precio_base"), ("finca_matr", "finca"), ("fecha", "fecha_remate"),
        ):
            if v1_name in evaluated:
                evaluated.add(v2_name)
        return evaluated

    def never_evaluated_fields(self) -> list[str]:
        evaluated = self._evaluated_fields()
        return sorted(f for f in self.registry.field_names() if f not in evaluated)

    # ─── alignment score per field ──────────────────────────────────────────

    def score_field(self, field_name: str) -> int:
        check = self.check_field(field_name)
        if not check["in_schema"]:
            return 0
        if not check["has_producer"] and not check["has_consumer"]:
            return 25 if check["in_golden"] else 0
        if not check["has_producer"]:
            return 50
        if not check["has_consumer"]:
            return 75
        if not check["has_documentation"]:
            return 90
        return 100

    def scores(self) -> dict[str, int]:
        return {f: self.score_field(f) for f in self.registry.field_names()}

    def overall_alignment(self) -> float:
        scores = self.scores()
        return round(sum(scores.values()) / max(len(scores), 1), 1)

    def blocked_fields(self) -> list[dict]:
        blocked = []
        for f in self.registry.field_names():
            score = self.score_field(f)
            if score < 100:
                check = self.check_field(f)
                reasons = []
                if score == 0:
                    reasons.append("campo roto")
                elif score == 25:
                    reasons.append("solo existe en golden")
                elif score == 50:
                    reasons.append("sin productor")
                elif score == 75:
                    reasons.append("sin consumidor")
                elif score == 90:
                    reasons.append("falta documentación")
                if not check["type_ok"]:
                    reasons.append("tipo incompatible")
                if not check["format_ok"]:
                    reasons.append("formato incompatible")
                if not check["deps_ok"]:
                    reasons.append("dependencia inválida")
                blocked.append({
                    "field": f, "score": score,
                    "state": "BLOCKED", "reasons": reasons or ["no alineado"],
                })
        return blocked

    def run_full_audit(self) -> dict:
        return {
            "fields": self.check_all(),
            "orphan_fields": self.detect_orphan_fields(),
            "missing_consumers": self.detect_missing_consumers(),
            "missing_producers": self.detect_missing_producers(),
            "ambiguous_aliases": self.detect_ambiguous_aliases(),
            "duplicate_aliases": self.detect_duplicate_aliases(),
            "invalid_aliases": self.detect_invalid_aliases(),
            "type_conflicts": self.detect_type_conflicts(),
            "format_conflicts": self.detect_format_conflicts(),
            "circular_dependencies": self.detect_circular_dependencies(),
            "never_certified": self.never_certified_fields(),
            "never_evaluated": self.never_evaluated_fields(),
            "scores": self.scores(),
            "overall_alignment": self.overall_alignment(),
            "certified_fields": self.certified_fields(),
            "blocked_fields": self.blocked_fields(),
        }


class AlignmentScorer:
    """Field alignment score per the FASE 8.20 scale:
    100 aligned, 90 missing docs, 75 missing consumer, 50 missing producer,
    25 only in golden, 0 broken."""

    def __init__(self, auditor: Optional[CompletionAuditor] = None):
        self.auditor = auditor or CompletionAuditor()

    def score_field(self, field_name: str) -> dict:
        score = self.auditor.score_field(field_name)
        if score >= 100:
            label = "completamente alineado"
        elif score >= 90:
            label = "falta documentación"
        elif score >= 75:
            label = "falta consumidor"
        elif score >= 50:
            label = "falta productor"
        elif score >= 25:
            label = "solo existe en golden"
        else:
            label = "campo roto"
        return {"field": field_name, "score": score, "status": label}

    def all(self) -> list[dict]:
        return [self.score_field(f) for f in self.auditor.registry.field_names()]

    def to_json(self) -> str:
        return json.dumps(self.all(), indent=2, ensure_ascii=False)

    def to_markdown(self) -> str:
        lines = ["| Campo | Score | Estado |", "|---|---|---|"]
        for item in self.all():
            lines.append(f"| `{item['field']}` | {item['score']}% | {item['status']} |")
        return "\n".join(lines) + "\n"


class CanonicalMatrixBuilder:
    """Final matrix: Campo / Productor / Consumidores / Knowledge / Validator /
    Database / API / Frontend / Export / Golden / Estado."""

    def __init__(self, auditor: Optional[CompletionAuditor] = None):
        self.auditor = auditor or CompletionAuditor()

    def build(self) -> list[dict]:
        rows = []
        for check in self.auditor.check_all():
            score = self.auditor.score_field(check["field"])
            rows.append({
                "campo": check["field"],
                "productor": "parser" if check["in_parser"] else ("knowledge" if check["in_knowledge"] else "✘"),
                "consumidores": "validator" if check["in_validator"] else (
                    "normalizer" if check["in_normalizer"] else "✘"),
                "knowledge": check["in_knowledge"],
                "validator": check["in_validator"],
                "database": check["in_database"],
                "api": check["in_api"],
                "frontend": check["in_frontend"],
                "export": check["in_export"],
                "golden": check["in_golden"],
                "estado": "CERTIFIED" if score >= 100 else "BLOCKED",
                "score": score,
            })
        return rows

    def to_json(self) -> str:
        return json.dumps(self.build(), indent=2, ensure_ascii=False)

    def to_markdown(self) -> str:
        header = ["Campo", "Productor", "Consumidor", "Knowledge", "Validator",
                  "Database", "API", "Frontend", "Export", "Golden", "Estado", "Score"]
        lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
        for r in self.build():
            lines.append(
                "| " + " | ".join([
                    f"`{r['campo']}`", r["productor"], r["consumidores"],
                    "✔" if r["knowledge"] else "✘", "✔" if r["validator"] else "✘",
                    "✔" if r["database"] else "✘", "✔" if r["api"] else "✘",
                    "✔" if r["frontend"] else "✘", "✔" if r["export"] else "✘",
                    "✔" if r["golden"] else "✘",
                    r["estado"], f"{r['score']}%",
                ]) + " |"
            )
        return "\n".join(lines) + "\n"


class BlockedFieldsReport:
    def __init__(self, auditor: Optional[CompletionAuditor] = None):
        self.auditor = auditor or CompletionAuditor()

    def generate(self) -> dict:
        return {
            "total_blocked": len(self.auditor.blocked_fields()),
            "blocked_fields": self.auditor.blocked_fields(),
            "total_certified": len(self.auditor.certified_fields()),
            "certified_fields": self.auditor.certified_fields(),
        }

    def to_markdown(self, report: dict) -> str:
        lines = ["# BLOCKED FIELDS — FASE 8.20", "",
                 f"**Total bloqueados:** {report['total_blocked']}",
                 f"**Total certificados:** {report['total_certified']}", ""]
        for b in report["blocked_fields"]:
            lines.append(f"- `{b['field']}` — score {b['score']}% — {', '.join(b['reasons'])}")
        return "\n".join(lines) + "\n"


class ArchitectureScoreReport:
    def __init__(self, auditor: Optional[CompletionAuditor] = None):
        self.auditor = auditor or CompletionAuditor()

    def generate(self) -> dict:
        audit = self.auditor.run_full_audit()
        counts = {status: 0 for status in ("100", "90", "75", "50", "25", "0")}
        for score in audit["scores"].values():
            bucket = "100" if score >= 100 else "90" if score >= 90 else \
                "75" if score >= 75 else "50" if score >= 50 else \
                "25" if score >= 25 else "0"
            counts[bucket] += 1
        return {
            "overall_alignment": audit["overall_alignment"],
            "score_distribution": counts,
            "total_fields": len(self.auditor.registry.field_names()),
            "certified": len(audit["certified_fields"]),
            "blocked": len(audit["blocked_fields"]),
            "orphan_fields": audit["orphan_fields"],
            "unused_fields": audit["missing_consumers"],
            "missing_producers": audit["missing_producers"],
            "missing_consumers": audit["missing_consumers"],
            "invalid_aliases": audit["invalid_aliases"],
            "type_conflicts": audit["type_conflicts"],
            "format_conflicts": audit["format_conflicts"],
            "circular_dependencies": audit["circular_dependencies"],
            "never_certified": audit["never_certified"],
            "never_evaluated": audit["never_evaluated"],
        }

    def to_markdown(self, report: dict) -> str:
        lines = [
            "# ARCHITECTURE SCORE — FASE 8.20", "",
            f"**Overall alignment:** {report['overall_alignment']}%",
            f"**Total fields:** {report['total_fields']}",
            f"**Certified:** {report['certified']}",
            f"**Blocked:** {report['blocked']}", "",
            "## Distribución de scores", "",
            "| Score | Campos |", "|---|---|",
        ]
        for bucket, count in report["score_distribution"].items():
            label = {"100": "100% alineado", "90": "90% falta doc",
                     "75": "75% falta consumidor", "50": "50% falta productor",
                     "25": "25% solo golden", "0": "0% roto"}[bucket]
            lines.append(f"| {label} | {count} |")
        lines += ["", "## Hallazgos", "",
                  f"- **Huérfanos:** {report['orphan_fields']}",
                  f"- **Consumidores faltantes:** {report['missing_consumers']}",
                  f"- **Productores faltantes:** {report['missing_producers']}",
                  f"- **Alias inválidos:** {len(report['invalid_aliases'])}",
                  f"- **Conflictos de tipo:** {len(report['type_conflicts'])}",
                  f"- **Conflictos de formato:** {len(report['format_conflicts'])}",
                  f"- **Dependencias circulares:** {len(report['circular_dependencies'])}",
                  f"- **Nunca certificados:** {len(report['never_certified'])}",
                  f"- **Nunca evaluados:** {len(report['never_evaluated'])}", ""]
        for tc in report["type_conflicts"]:
            lines.append(f"- Tipo: `{tc['field']}` espera {tc['expected']} en {tc['layer']}, encontrado {tc['found']}")
        return "\n".join(lines) + "\n"
