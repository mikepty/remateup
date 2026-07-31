"""FASE 8.10.3 / 8.10.7 / 8.10.8 — Coverage Analyzer, Field Matrix and
Consistency Report.

Automatically reviews every field against every module and reports:
orphan fields, never-produced fields, never-consumed fields, duplicated
fields, inconsistent names, redundant aliases, duplicate regexes, broken
dependencies and the overall alignment percentage.
"""

import json
from typing import Any, Optional

from backend.app.v2.schema.field_registry import REGISTRY
from backend.app.v2.schema.models import (
    COUNTRY_CO,
    COUNTRY_PA,
    ConsistencyIssue,
    FieldCoverage,
    MODULES,
)

# Modules included in coverage computation (field matrix columns, 8.10.7).
MATRIX_MODULES = [
    "parser",
    "knowledge",
    "validator",
    "normalizer",
    "confidence",
    "golden_dataset",
    "certification",
]

# Fields with real, current knowledge support (seeded rules/patterns).
KNOWLEDGE_FIELDS_REAL = {
    "expediente", "finca", "demandante", "demandado",
    "precio_base", "base", "fecha_remate", "fecha",
}

PRODUCERS = ("parser", "knowledge")
CONSUMERS = ("validator", "normalizer", "confidence", "golden_dataset",
             "certification", "regression")


def _probe_catalog(module: str) -> list[str]:
    """Read the REAL field catalog of a module directly from its code."""
    try:
        if module == "validator":
            from backend.app.v2.validator.production_rules import ALL_FIELDS
            return sorted(ALL_FIELDS)
        if module == "normalizer":
            from backend.app.v2.normalization.normalizer import FIELD_NORMALIZERS
            return sorted(FIELD_NORMALIZERS.keys())
        if module == "regression":
            from backend.app.v2.fase8.regression import COMPARISON_FIELDS
            return sorted(COMPARISON_FIELDS)
        if module == "parser":
            fields = set()
            import backend.app.v2.parser.documents.panama_remate as pa_mod
            import backend.app.v2.parser.documents.colombia_remate as co_mod
            fields.update(pa_mod._PATTERNS.keys())
            fields.update(co_mod._PATTERNS.keys())
            return sorted(fields)
        if module == "golden_dataset":
            from backend.app.v2.fase8.golden_dataset import GoldenDatasetManager
            manager = GoldenDatasetManager()
            return sorted(set(manager.get_field_coverage().keys())
                          | set(manager.get_critical_fields()))
    except Exception:
        return []
    return []


class CoverageAnalyzer:
    def __init__(self, registry=None):
        self.registry = registry or REGISTRY

    def analyze_field(self, field_name: str) -> FieldCoverage:
        definition = self.registry.resolve(field_name)
        if definition is None:
            return FieldCoverage(field_name=field_name, by_module={m: False for m in MATRIX_MODULES},
                                 coverage_pct=0.0)
        by_module: dict[str, bool] = {}
        for module in MATRIX_MODULES:
            if module == "knowledge":
                supported = field_name in KNOWLEDGE_FIELDS_REAL
            elif module == "confidence":
                supported = True
            else:
                supported = definition.is_supported_by(module)
            by_module[module] = supported
        coverage = sum(1 for v in by_module.values() if v) / max(len(by_module), 1) * 100
        return FieldCoverage(
            field_name=definition.field_name,
            by_module=by_module,
            coverage_pct=round(coverage, 1),
        )

    def analyze_all(self) -> list[FieldCoverage]:
        return [self.analyze_field(f) for f in self.registry.field_names()]

    def get_coverage(self, field_name: str) -> float:
        return self.analyze_field(field_name).coverage_pct

    def coverage_by_country(self, country: str) -> dict[str, float]:
        return {
            f: self.get_coverage(f)
            for f in self.registry.by_country(country)
        }

    def coverage_by_document_type(self, doc_type: str) -> dict[str, float]:
        result = {}
        for d in self.registry.all():
            if doc_type in d.document_type:
                result[d.field_name] = self.get_coverage(d.field_name)
        return result

    def coverage_by_stage(self) -> dict[str, dict]:
        stages = {
            "produccion": PRODUCERS,
            "validacion": ("validator",),
            "normalizacion": ("normalizer",),
            "confianza": ("confidence",),
            "certificacion": ("certification",),
        }
        result = {}
        for stage, modules in stages.items():
            result[stage] = {
                f: sum(1 for m in modules if self.analyze_field(f).by_module.get(m))
                / max(len(modules), 1) * 100
                for f in self.registry.field_names()
            }
        return result

    def detect_orphan_fields(self) -> list[str]:
        orphans = []
        for f in self.registry.field_names():
            coverage = self.analyze_field(f)
            produced = any(coverage.by_module.get(m) for m in PRODUCERS)
            consumed = any(coverage.by_module.get(m) for m in CONSUMERS)
            if not produced and not consumed:
                orphans.append(f)
        return sorted(orphans)

    def detect_never_produced(self) -> list[str]:
        result = []
        for f in self.registry.field_names():
            coverage = self.analyze_field(f)
            if not any(coverage.by_module.get(m) for m in PRODUCERS):
                result.append(f)
        return sorted(result)

    def detect_never_consumed(self) -> list[str]:
        result = []
        for f in self.registry.field_names():
            coverage = self.analyze_field(f)
            if not any(coverage.by_module.get(m) for m in CONSUMERS):
                result.append(f)
        return sorted(result)

    def detect_duplicated_fields(self) -> list[str]:
        duplicated = set()
        for d in self.registry.all():
            for alias in d.aliases:
                target = self.registry.resolve(alias)
                if target and target.field_name != d.field_name:
                    duplicated.add(d.field_name)
                    duplicated.add(target.field_name)
        return sorted(duplicated)

    def detect_inconsistent_names(self) -> list[dict]:
        result = []
        for d in self.registry.all():
            for alias in d.aliases:
                target = self.registry.resolve(alias)
                if target and target.field_name != d.field_name:
                    result.append({
                        "canonical": d.field_name,
                        "alias": alias,
                        "resolves_to": target.field_name,
                    })
        return result

    def detect_redundant_aliases(self) -> list[str]:
        redundant = []
        for d in self.registry.all():
            for alias in d.aliases:
                if any(other.field_name == alias for other in self.registry.all()):
                    redundant.append(alias)
        return sorted(set(redundant))

    def detect_duplicate_regexes(self) -> list[str]:
        seen: dict[str, str] = {}
        dupes = []
        for d in self.registry.all():
            for pattern in d.regex_patterns:
                if pattern in seen and seen[pattern] != d.field_name:
                    dupes.append(pattern)
                else:
                    seen[pattern] = d.field_name
        return sorted(set(dupes))

    def detect_broken_dependencies(self) -> list[dict]:
        broken = []
        for f in self.registry.field_names():
            coverage = self.analyze_field(f)
            if coverage.by_module.get("golden_dataset") and not any(
                coverage.by_module.get(m) for m in PRODUCERS
            ):
                broken.append({"field": f, "requester": "golden_dataset",
                               "problem": "required by Golden Dataset but no module produces it"})
        return broken

    def alignment_pct(self) -> float:
        total = len(self.registry.field_names())
        if total == 0:
            return 0.0
        problematic = set(self.detect_never_produced())
        problematic.update(self.detect_never_consumed())
        return round((total - len(problematic)) / total * 100, 1)

    def run_full_analysis(self) -> dict:
        return {
            "total_fields": len(self.registry.field_names()),
            "fields": [c.to_dict() for c in self.analyze_all()],
            "orphan_fields": self.detect_orphan_fields(),
            "never_produced": self.detect_never_produced(),
            "never_consumed": self.detect_never_consumed(),
            "duplicated_fields": self.detect_duplicated_fields(),
            "inconsistent_names": self.detect_inconsistent_names(),
            "redundant_aliases": self.detect_redundant_aliases(),
            "duplicate_regexes": self.detect_duplicate_regexes(),
            "broken_dependencies": self.detect_broken_dependencies(),
            "coverage_by_country": {c: self.coverage_by_country(c) for c in (COUNTRY_PA, COUNTRY_CO)},
            "coverage_by_stage": self.coverage_by_stage(),
            "alignment_pct": self.alignment_pct(),
        }


class FieldMatrixGenerator:
    def __init__(self, registry=None, analyzer: Optional[CoverageAnalyzer] = None):
        self.registry = registry or REGISTRY
        self.analyzer = analyzer or CoverageAnalyzer(self.registry)

    def generate_matrix(self) -> list[dict]:
        rows = []
        for f in self.registry.field_names():
            definition = self.registry.resolve(f)
            coverage = self.analyzer.analyze_field(f)
            problems = []
            if f in self.analyzer.detect_never_produced():
                problems.append("sin_productor")
            if f in self.analyzer.detect_never_consumed():
                problems.append("sin_consumidor")
            if f in self.analyzer.detect_orphan_fields():
                problems.append("huerfano")
            rows.append({
                "campo": f,
                "tipo": definition.data_type if definition else "text",
                "PA": COUNTRY_PA in (definition.country if definition else set()),
                "CO": COUNTRY_CO in (definition.country if definition else set()),
                "parser": coverage.by_module.get("parser", False),
                "knowledge": coverage.by_module.get("knowledge", False),
                "validator": coverage.by_module.get("validator", False),
                "normalizer": coverage.by_module.get("normalizer", False),
                "confidence": coverage.by_module.get("confidence", False),
                "golden": coverage.by_module.get("golden_dataset", False),
                "certification": coverage.by_module.get("certification", False),
                "cobertura": coverage.coverage_pct,
                "obligatorio": bool(definition and definition.required),
                "opcional": bool(definition and not definition.required),
                "estado": "inconsistente" if problems else "ok",
            })
        return rows

    def to_json(self) -> str:
        return json.dumps(self.generate_matrix(), indent=2, ensure_ascii=False)

    def to_markdown(self) -> str:
        rows = self.generate_matrix()
        header = ["Campo", "Tipo", "PA", "CO", "Parser", "Knowledge", "Validator",
                  "Normalizer", "Confidence", "Golden", "Certification",
                  "Cobertura", "Obligatorio", "Estado"]
        lines = ["| " + " | ".join(header) + " |",
                 "|" + "---|" * len(header)]
        for r in rows:
            lines.append(
                "| " + " | ".join([
                    f"`{r['campo']}`", r["tipo"],
                    "✔" if r["PA"] else "✘", "✔" if r["CO"] else "✘",
                    "✔" if r["parser"] else "✘", "✔" if r["knowledge"] else "✘",
                    "✔" if r["validator"] else "✘", "✔" if r["normalizer"] else "✘",
                    "✔" if r["confidence"] else "✘", "✔" if r["golden"] else "✘",
                    "✔" if r["certification"] else "✘",
                    f"{r['cobertura']:.0f}%",
                    "Sí" if r["obligatorio"] else "No",
                    r["estado"],
                ]) + " |"
            )
        return "\n".join(lines)


class ConsistencyReportGenerator:
    def __init__(self, registry=None, analyzer: Optional[CoverageAnalyzer] = None):
        self.registry = registry or REGISTRY
        self.analyzer = analyzer or CoverageAnalyzer(self.registry)

    def generate(self) -> dict:
        issues: list[ConsistencyIssue] = []
        registry_names = set(self.registry.field_names())

        for module in MODULES:
            real = _probe_catalog(module)
            for field in real:
                if field not in registry_names and self.registry.resolve(field) is None:
                    issues.append(ConsistencyIssue(
                        issue_type="campo_faltante",
                        module=module,
                        field=field,
                        problem=f"field used by {module} but missing from the schema registry",
                        solution=f"add '{field}' to backend/app/v2/schema/definitions.py",
                    ))

        for f in self.analyzer.detect_never_produced():
            issues.append(ConsistencyIssue(
                issue_type="campo_nunca_producido",
                module="parser",
                field=f,
                problem="field is expected by consumers but no module produces it",
                solution=f"add '{f}' to the parser _PATTERNS or a knowledge rule",
            ))

        for d in self.analyzer.detect_broken_dependencies():
            issues.append(ConsistencyIssue(
                issue_type="dependencia_rota",
                module="golden_dataset",
                field=d["field"],
                problem=d["problem"],
                solution=f"add producer support for '{d['field']}'",
            ))

        for pair in self.analyzer.detect_inconsistent_names():
            issues.append(ConsistencyIssue(
                issue_type="nombre_inconsistente",
                module="definitions",
                field=pair["canonical"],
                problem=f"alias '{pair['alias']}' also resolves to '{pair['resolves_to']}'",
                solution="keep a single canonical name and document V1 names as aliases",
            ))

        for alias in self.analyzer.detect_redundant_aliases():
            issues.append(ConsistencyIssue(
                issue_type="alias_redundante",
                module="definitions",
                field=alias,
                problem=f"alias '{alias}' duplicates an existing field name",
                solution=f"remove the redundant alias '{alias}'",
            ))

        for pattern in self.analyzer.detect_duplicate_regexes():
            issues.append(ConsistencyIssue(
                issue_type="regex_duplicada",
                module="definitions",
                field=pattern,
                problem=f"regex pattern '{pattern}' is used by more than one field",
                solution="share one pattern or differentiate the regexes",
            ))

        return {
            "campos_faltantes": [i.to_dict() for i in issues if i.issue_type == "campo_faltante"],
            "campos_duplicados": [i.to_dict() for i in issues if i.issue_type == "campo_nunca_producido"],
            "campos_inconsistentes": [i.to_dict() for i in issues if i.issue_type == "nombre_inconsistente"],
            "alias_redundantes": [i.to_dict() for i in issues if i.issue_type == "alias_redundante"],
            "regex_duplicadas": [i.to_dict() for i in issues if i.issue_type == "regex_duplicada"],
            "dependencias_rotas": [i.to_dict() for i in issues if i.issue_type == "dependencia_rota"],
            "cobertura_general": self.analyzer.alignment_pct(),
            "porcentaje_alineacion": self.analyzer.alignment_pct(),
            "issues": [i.to_dict() for i in issues],
        }

    def to_markdown(self, report: dict) -> str:
        lines = ["# CONSISTENCY REPORT — FASE 8.10.8", "",
                 f"**Porcentaje de alineación:** {report['porcentaje_alineacion']}%", "",
                 f"**Campos faltantes:** {len(report['campos_faltantes'])}",
                 f"**Campos duplicados:** {len(report['campos_duplicados'])}",
                 f"**Campos inconsistentes:** {len(report['campos_inconsistentes'])}",
                 f"**Alias redundantes:** {len(report['alias_redundantes'])}",
                 f"**Regex duplicadas:** {len(report['regex_duplicadas'])}",
                 f"**Dependencias rotas:** {len(report['dependencias_rotas'])}", ""]
        for issue in report["issues"]:
            lines.append(f"- [{issue['issue_type']}] `{issue['field']}` ({issue['module']}): {issue['problem']}")
            if issue["solution"]:
                lines.append(f"  → {issue['solution']}")
        return "\n".join(lines) + "\n"
