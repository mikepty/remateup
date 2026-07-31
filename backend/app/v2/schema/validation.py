"""FASE 8.10.4 / 8.10.6 / 8.10.9 — Dependency Validation, Compatibility
Checker and Auto Fix Suggestions.

Answers deterministically: who produces each field, who consumes it, who
validates it, who normalizes it, who certifies it. Generates a serializable
dependency graph, per-module compatibility verdicts and fix recommendations
(never modifies code automatically).
"""

import json
from typing import Optional

from backend.app.v2.schema.coverage import CoverageAnalyzer
from backend.app.v2.schema.field_registry import REGISTRY
from backend.app.v2.schema.models import (
    CompatibilityReport,
    ConsistencyIssue,
    DependencyEdge,
    MODULES,
)

PRODUCERS = ("parser", "knowledge")
VALIDATORS = ("validator",)
NORMALIZERS = ("normalizer",)
CERTIFIERS = ("certification",)


class DependencyValidator:
    def __init__(self, registry=None, analyzer: Optional[CoverageAnalyzer] = None):
        self.registry = registry or REGISTRY
        self.analyzer = analyzer or CoverageAnalyzer(self.registry)

    def who_produces(self, field_name: str) -> list[str]:
        coverage = self.analyzer.analyze_field(field_name)
        return [m for m in PRODUCERS if coverage.by_module.get(m)]

    def who_consumes(self, field_name: str) -> list[str]:
        coverage = self.analyzer.analyze_field(field_name)
        consumers = []
        for module in MODULES:
            if module in PRODUCERS:
                continue
            if coverage.by_module.get(module) or (module == "confidence"):
                consumers.append(module)
        return consumers

    def who_validates(self, field_name: str) -> list[str]:
        coverage = self.analyzer.analyze_field(field_name)
        return [m for m in VALIDATORS if coverage.by_module.get(m)]

    def who_normalizes(self, field_name: str) -> list[str]:
        coverage = self.analyzer.analyze_field(field_name)
        return [m for m in NORMALIZERS if coverage.by_module.get(m)]

    def who_certifies(self, field_name: str) -> list[str]:
        coverage = self.analyzer.analyze_field(field_name)
        return [m for m in CERTIFIERS if coverage.by_module.get(m)]

    def who_modifies(self, field_name: str) -> list[str]:
        return self.who_normalizes(field_name) + self.who_validates(field_name)

    def build_graph(self) -> dict:
        nodes = []
        edges = []
        for field_name in self.registry.field_names():
            nodes.append({
                "id": field_name,
                "produces": self.who_produces(field_name),
                "consumes": self.who_consumes(field_name),
                "validates": self.who_validates(field_name),
                "normalizes": self.who_normalizes(field_name),
                "certifies": self.who_certifies(field_name),
            })
            for producer in self.who_produces(field_name):
                for consumer in self.who_consumes(field_name):
                    edges.append(DependencyEdge(
                        field_name=field_name,
                        producer=producer,
                        consumer=consumer,
                    ).to_dict())
        return {"nodes": nodes, "edges": edges}

    def to_json(self) -> str:
        return json.dumps(self.build_graph(), indent=2, ensure_ascii=False)

    def to_markdown(self) -> str:
        graph = self.build_graph()
        lines = ["# DEPENDENCY GRAPH — FASE 8.10.4", "",
                 "| Campo | Produce | Consume | Valida | Normaliza | Certifica |",
                 "|---|---|---|---|---|---|"]
        for node in graph["nodes"]:
            lines.append(
                f"| `{node['id']}` | {', '.join(node['produces']) or '—'} | "
                f"{', '.join(node['consumes']) or '—'} | "
                f"{', '.join(node['validates']) or '—'} | "
                f"{', '.join(node['normalizes']) or '—'} | "
                f"{', '.join(node['certifies']) or '—'} |"
            )
        return "\n".join(lines) + "\n"


class CompatibilityChecker:
    def __init__(self, registry=None, analyzer: Optional[CoverageAnalyzer] = None):
        self.registry = registry or REGISTRY
        self.analyzer = analyzer or CoverageAnalyzer(self.registry)

    def check_module(self, module: str) -> CompatibilityReport:
        issues: list[ConsistencyIssue] = []
        if module == "parser":
            missing = self.analyzer.detect_never_produced()
            for field in missing:
                definition = self.registry.resolve(field)
                if definition and (definition.required or definition.golden_dataset_supported):
                    issues.append(ConsistencyIssue(
                        issue_type="campo_critico_sin_productor",
                        module="parser",
                        field=field,
                        problem="critical or golden-required field is never produced",
                        solution=f"add '{field}' to the parser _PATTERNS (CO/PA)",
                    ))
        elif module == "knowledge":
            coverage = self.analyzer.analyze_all()
            for c in coverage:
                if c.coverage_pct > 0 and not c.by_module.get("knowledge"):
                    definition = self.registry.resolve(c.field_name)
                    if definition and definition.required:
                        issues.append(ConsistencyIssue(
                            issue_type="conocimiento_faltante",
                            module="knowledge",
                            field=c.field_name,
                            problem="required field has no knowledge rule",
                            solution=f"seed a knowledge rule for '{c.field_name}'",
                        ))
        elif module == "validator":
            from backend.app.v2.validator.production_rules import ALL_FIELDS
            for field in sorted(ALL_FIELDS):
                if self.registry.resolve(field) is None:
                    issues.append(ConsistencyIssue(
                        issue_type="campo_faltante",
                        module="validator",
                        field=field,
                        problem="validator uses a field unknown to the schema registry",
                        solution=f"define '{field}' in the schema registry",
                    ))
        elif module == "normalizer":
            from backend.app.v2.normalization.normalizer import FIELD_NORMALIZERS
            for field in sorted(FIELD_NORMALIZERS.keys()):
                definition = self.registry.resolve(field)
                if definition is None:
                    issues.append(ConsistencyIssue(
                        issue_type="campo_faltante",
                        module="normalizer",
                        field=field,
                        problem="normalizer handles a field unknown to the schema registry",
                        solution=f"define '{field}' in the schema registry",
                    ))
        elif module == "confidence":
            pass
        elif module == "golden_dataset":
            for d in self.analyzer.detect_broken_dependencies():
                issues.append(ConsistencyIssue(
                    issue_type="dependencia_rota",
                    module="golden_dataset",
                    field=d["field"],
                    problem=d["problem"],
                    solution=f"add producer support for '{d['field']}'",
                ))
        elif module == "certification":
            blockers = self.find_certification_blockers()
            for field in blockers:
                issues.append(ConsistencyIssue(
                    issue_type="bloqueante_certificacion",
                    module="certification",
                    field=field,
                    problem="CERTIFIED forbidden: field required by golden dataset has no producer",
                    solution=f"add producer support for '{field}' before certifying",
                ))
        elif module == "regression":
            from backend.app.v2.fase8.regression import COMPARISON_FIELDS
            for field in COMPARISON_FIELDS:
                if self.registry.resolve(field) is None:
                    issues.append(ConsistencyIssue(
                        issue_type="campo_faltante",
                        module="regression",
                        field=field,
                        problem="regression compares a field unknown to the schema registry",
                        solution=f"define '{field}' in the schema registry",
                    ))
        return CompatibilityReport(module=module, compatible=len(issues) == 0, issues=issues)

    def check_all(self) -> list[CompatibilityReport]:
        return [self.check_module(m) for m in MODULES]

    def all_compatible(self) -> bool:
        return all(r.compatible for r in self.check_all())

    def find_certification_blockers(self) -> list[str]:
        blockers = []
        for d in self.analyzer.detect_broken_dependencies():
            definition = self.registry.resolve(d["field"])
            if definition and definition.required:
                blockers.append(d["field"])
        return sorted(set(blockers))


class AutoFixSuggestions:
    def __init__(self, registry=None, analyzer: Optional[CoverageAnalyzer] = None):
        self.registry = registry or REGISTRY
        self.analyzer = analyzer or CoverageAnalyzer(self.registry)

    def generate(self) -> list[dict]:
        suggestions = []
        never_produced = self.analyzer.detect_never_produced()
        for field in never_produced:
            definition = self.registry.resolve(field)
            if definition is None:
                continue
            required_by = []
            if definition.golden_dataset_supported:
                required_by.append("Golden Dataset")
            if definition.validator_supported:
                required_by.append("Validator")
            if definition.certification_supported:
                required_by.append("Certification")
            if definition.required:
                required_by.append("Campo obligatorio")
            if not required_by:
                continue
            target = "ColombiaRemateParser" if "CO" in definition.country else "PanamaRemateParser"
            if "CO" in definition.country and "PA" in definition.country:
                target = "ColombiaRemateParser / PanamaRemateParser"
            suggestions.append({
                "accion": "agregar_campo",
                "campo": field,
                "modulo": "parser",
                "archivo": f"backend/app/v2/parser/documents/{target.lower().replace(' / ', '_').split('_')[0]}_remate.py",
                "recomendacion": f"add '{field}' to {target} because it is required by {', '.join(required_by)}",
                "porque": f"required by {', '.join(required_by)}",
            })
        for alias in self.analyzer.detect_redundant_aliases():
            suggestions.append({
                "accion": "eliminar_alias",
                "campo": alias,
                "modulo": "definitions",
                "archivo": "backend/app/v2/schema/definitions.py",
                "recomendacion": f"remove redundant alias '{alias}'",
                "porque": "alias duplicates an existing field name",
            })
        missing = self._registry_missing_fields()
        for module, fields in missing.items():
            for field in fields:
                suggestions.append({
                    "accion": "agregar_campo",
                    "campo": field,
                    "modulo": "definitions",
                    "archivo": "backend/app/v2/schema/definitions.py",
                    "recomendacion": f"add '{field}' to the schema registry",
                    "porque": f"used by {module} but not defined in the registry",
                })
        return suggestions

    def _registry_missing_fields(self) -> dict[str, list[str]]:
        from backend.app.v2.schema.coverage import _probe_catalog
        registry_names = set(self.registry.field_names())
        result = {}
        for module in MODULES:
            real = _probe_catalog(module)
            missing = [f for f in real
                       if f not in registry_names and self.registry.resolve(f) is None]
            if missing:
                result[module] = missing
        return result
