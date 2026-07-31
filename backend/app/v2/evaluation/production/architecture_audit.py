"""FASE 12 — Parte 9: Architecture Audit Final.

Auditor estático y determinista que responde automáticamente:

  - módulos muertos
  - código nunca ejecutado
  - clases nunca instanciadas
  - reglas nunca utilizadas
  - campos imposibles
  - dependencias circulares
  - productores sin consumidores
  - consumidores sin productores
  - alias redundantes
  - validaciones duplicadas

Método: análisis estático con `ast` sobre backend/app/v2 (grafo de imports,
definiciones y usos), lectura real de la base de conocimiento y del catálogo
de campos. Se documenta que "nunca ejecutado" es una aproximación estática
(referencia cruzada de definiciones vs usos).
"""

import ast
import json
import re
from pathlib import Path
from typing import Any, Optional

from backend.app.v2.schema.definitions import get_definitions
from backend.app.v2.parser.ai.policy import AI_ALLOWED_FIELDS

V2_ROOT = Path(__file__).resolve().parents[2]


class _ModuleInfo:
    def __init__(self, rel: str):
        self.rel = rel
        self.imports: set[str] = set()       # módulos v2 importados (rel paths)
        self.defined_classes: dict[str, int] = {}  # name -> lineno
        self.defined_functions: dict[str, int] = {}
        self.references: set[str] = set()    # nombres usados dentro del módulo


def _to_rel(module_name: str, current_rel: str) -> Optional[str]:
    """Resuelve un import a un rel-path de v2 o None si no es interno."""
    parts = module_name.split(".")
    if parts[:3] == ["backend", "app", "v2"]:
        return "/".join(parts[3:]) + ".py"
    if module_name == "backend.app.v2":
        return ""
    return None


def _parse_module(path: Path, rel: str, info: _ModuleInfo):
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, OSError):
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:  # import relativo
                depth = node.level - 1
                parts = rel.replace("\\", "/").split("/")[:-1]
                if depth > len(parts):
                    continue
                base_rel = "/".join(parts[: len(parts) - depth] if depth else parts)
                resolved = base
                if base:
                    resolved = (base_rel + "/" + base) if base_rel else base
                candidates = [resolved + ".py", resolved + "/__init__.py"]
                for c in candidates:
                    if (V2_ROOT / c).exists():
                        info.imports.add(c)
                        break
            else:
                r = _to_rel(base, rel)
                if r is not None:
                    info.imports.add(r + ".py" if r else "__init__.py")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                r = _to_rel(alias.name, rel)
                if r is not None:
                    info.imports.add(r + ".py" if r else "__init__.py")
        elif isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if isinstance(node, ast.ClassDef):
                info.defined_classes[node.name] = node.lineno
            else:
                info.defined_functions[node.name] = node.lineno
        if isinstance(node, ast.Name):
            info.references.add(node.id)
        elif isinstance(node, ast.Attribute):
            info.references.add(node.attr)


def _collect_modules() -> dict[str, _ModuleInfo]:
    modules: dict[str, _ModuleInfo] = {}
    for path in sorted(V2_ROOT.rglob("*.py")):
        if "tests" in path.parts or path.name == "__init__.py":
            continue
        rel = str(path.relative_to(V2_ROOT)).replace("\\", "/")
        info = _ModuleInfo(rel)
        _parse_module(path, rel, info)
        modules[rel] = info
    return modules


def find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    cycles: list[list[str]] = []
    seen: set[str] = set()

    def dfs(start: str, path: list[str], visited: set[str]):
        if start in visited:
            i = path.index(start)
            cycle = path[i:]
            if cycle not in cycles and sorted(cycle) not in [sorted(c) for c in cycles]:
                cycles.append(list(cycle))
            return
        visited.add(start)
        for nxt in graph.get(start, ()):
            dfs(nxt, path + [nxt], visited)
        visited.remove(start)

    for node in graph:
        if node in seen:
            continue
        dfs(node, [node], set())
    return cycles


def run_architecture_audit(
    repository=None,
    out_dir: Optional[str] = None,
    include_dead_module_details: bool = True,
) -> dict:
    modules = _collect_modules()
    names = list(modules)

    # Grafo de imports interno
    graph: dict[str, set[str]] = {n: set() for n in names}
    for rel, info in modules.items():
        for imp in info.imports:
            if imp in modules:
                graph[rel].add(imp)

    # 1. Módulos muertos: nadie los importa y no son scripts ejecutables
    imported_by: dict[str, set[str]] = {n: set() for n in names}
    for src, targets in graph.items():
        for t in targets:
            imported_by[t].add(src)
    dead_modules = []
    for rel, info in modules.items():
        if imported_by[rel]:
            continue
        text = (V2_ROOT / rel).read_text(encoding="utf-8", errors="replace")
        is_script = "__main__" in text or 'argparse' in text
        if not is_script:
            dead_modules.append({"modulo": rel, "tipo": "no_importado_no_script"})

    # 2. Código nunca ejecutado (aprox. estática): funciones/classes sin uso externo
    references = {n: set() for n in names}
    for rel, info in modules.items():
        references[rel] = set(info.references) | {imp.split("/")[-1][:-3] for imp in info.imports}
    never_executed = []
    for rel, info in modules.items():
        for fname in list(info.defined_functions):
            used = any(
                fname in references[other] for other in names if other != rel
            )
            if not used and not fname.startswith("_"):
                never_executed.append({"modulo": rel, "tipo": "funcion", "nombre": fname})
        for cname in list(info.defined_classes):
            used = any(cname in references[other] for other in names if other != rel)
            if not used:
                never_executed.append({"modulo": rel, "tipo": "clase", "nombre": cname})

    # 3. Clases nunca instanciadas: el nombre no aparece seguido de "(" fuera de su módulo
    never_instantiated = []
    for rel, info in modules.items():
        for cname in info.defined_classes:
            instantiated = False
            for other in names:
                if other == rel:
                    continue
                text = (V2_ROOT / other).read_text(encoding="utf-8", errors="replace")
                if re.search(r"\b" + re.escape(cname) + r"\s*\(", text):
                    instantiated = True
                    break
            if not instantiated:
                never_instantiated.append({"modulo": rel, "clase": cname})

    # 4. Reglas nunca utilizadas (base de conocimiento real)
    from backend.app.v2.knowledge.repository import KnowledgeRepository

    repo = repository or KnowledgeRepository()
    rules = repo.get_rules()
    reglas_nunca_usadas = [
        {"rule_id": r.rule_id, "campo": r.field_name, "estado": r.status}
        for r in rules if (r.usage_count or 0) == 0
    ]

    # 5-8. Catálogo: productores/consumidores/campos imposibles
    defs = get_definitions()
    ai_allowed = set(AI_ALLOWED_FIELDS)
    campos_imposibles = []
    productores_sin_consumidores = []
    consumidores_sin_productores = []
    for d in defs:
        producer = d.parser_supported or d.golden_dataset_supported
        consumer = d.validator_supported or d.certification_supported or d.regression_supported
        if not producer and not consumer and not d.normalizer_supported and d.field_name not in ai_allowed:
            campos_imposibles.append({
                "campo": d.field_name,
                "razon": "sin parser, sin golden, sin validator/certification/regression, sin normalizer y fuera de AI_ALLOWED_FIELDS",
            })
        if producer and not consumer:
            productores_sin_consumidores.append({
                "campo": d.field_name,
                "productores": [s for s, v in (("parser", d.parser_supported), ("golden", d.golden_dataset_supported)) if v],
                "razon": "nadie lo valida, certifica ni usa en regression",
            })
        if consumer and not producer and d.field_name not in ai_allowed:
            consumidores_sin_productores.append({
                "campo": d.field_name,
                "consumidores": [s for s, v in (("validator", d.validator_supported),
                                                ("certification", d.certification_supported),
                                                ("regression", d.regression_supported)) if v],
                "razon": "nadie lo produce (parser/golden/IA no lo producen)",
            })

    # 9. Alias redundantes: pares bidireccionales + alias duplicados en el catálogo
    canonical_by_name = {d.field_name: d for d in defs}
    redundant_aliases = []
    for d in defs:
        for alias in d.aliases:
            if alias in canonical_by_name:
                other = canonical_by_name[alias]
                if d.field_name in other.aliases:
                    redundant_aliases.append({
                        "alias": alias,
                        "par": [d.field_name, other.field_name],
                        "razon": "par bidireccional V1<->V2 declarado en ambos sentidos",
                    })
    alias_duplicates = []
    for d in defs:
        seen = set()
        for alias in d.aliases:
            if alias in seen:
                alias_duplicates.append({"campo": d.field_name, "alias": alias, "razon": "alias repetido dentro del mismo campo"})
            seen.add(alias)

    # 10. Validaciones duplicadas: patrones/reglas repetidas entre módulos de validator
    duplicated_validations = _find_duplicated_validations()

    audit = {
        "modulos_analizados": len(names),
        "modulos_muertos": dead_modules,
        "codigo_nunca_ejecutado": never_executed,
        "clases_nunca_instanciadas": never_instantiated,
        "reglas_nunca_utilizadas": reglas_nunca_usadas,
        "campos_imposibles": campos_imposibles,
        "dependencias_circulares": find_cycles(graph),
        "productores_sin_consumidores": productores_sin_consumidores,
        "consumidores_sin_productores": consumidores_sin_productores,
        "alias_redundantes": redundant_aliases,
        "alias_duplicados": alias_duplicates,
        "validaciones_duplicadas": duplicated_validations,
        "metodologia": [
            "analisis estatico con ast sobre backend/app/v2 (grafo de imports, definiciones, referencias)",
            "codigo_nunca_ejecutado es una aproximacion estatica (referencia cruzada de definiciones vs usos); no es un profile de ejecucion",
            "reglas/alias leidos de la base de conocimiento real (knowledge.db)",
            "campos evaluados contra el catalogo de schema/definitions.py y AI_ALLOWED_FIELDS",
        ],
    }

    if out_dir:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "architecture_audit.json").write_text(
            json.dumps(audit, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        (out / "architecture_audit.md").write_text(audit_to_markdown(audit), encoding="utf-8")
    return audit


def _find_duplicated_validations() -> list[dict]:
    """Busca patrones/reglas duplicadas entre módulos de validator y knowledge."""
    duplicates: list[dict] = []
    pattern_owner: dict[str, str] = {}
    v2_root = V2_ROOT

    for rel in ("validator/production_rules.py", "validator/notice_validator.py",
                "validator/consistency.py", "validator/duplicate_detector.py",
                "validator/orchestrator.py"):
        path = v2_root / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r'r(?:"|\')(?P<pat>[^"\']{8,120})(?:"|\')', text):
            pat = m.group("pat")
            if pat in pattern_owner and pattern_owner[pat] != rel:
                duplicates.append({"patron": pat[:100], "modulos": [pattern_owner[pat], rel]})
            else:
                pattern_owner.setdefault(pat, rel)

    # Grupos de campos solapados entre categorías de validación
    from backend.app.v2.validator.production_rules import STRONG_FIELDS, MEDIUM_FIELDS, WEAK_FIELDS
    overlap = sorted((STRONG_FIELDS | MEDIUM_FIELDS | WEAK_FIELDS) - WEAK_FIELDS - MEDIUM_FIELDS - STRONG_FIELDS) if False else []
    overlap = sorted((STRONG_FIELDS & MEDIUM_FIELDS) | (MEDIUM_FIELDS & WEAK_FIELDS) | (STRONG_FIELDS & WEAK_FIELDS))
    if overlap:
        duplicates.append({
            "tipo": "campo_en_varias_categorias_validator",
            "campos": overlap,
        })
    return duplicates


def audit_to_markdown(audit: dict) -> str:
    lines = ["# Architecture Audit Final (FASE 12)", ""]
    lines.append(f"- Módulos analizados: **{audit['modulos_analizados']}**")
    lines.append("")
    lines.append(f"## Módulos muertos: **{len(audit['modulos_muertos'])}**")
    for m in audit["modulos_muertos"]:
        lines.append(f"- `{m['modulo']}`")
    lines.append("")
    lines.append(f"## Código nunca ejecutado (aprox. estática): **{len(audit['codigo_nunca_ejecutado'])}**")
    for m in audit["codigo_nunca_ejecutado"][:30]:
        lines.append(f"- `{m['modulo']}` {m['tipo']} `{m['nombre']}`")
    if len(audit["codigo_nunca_ejecutado"]) > 30:
        lines.append(f"- ... y {len(audit['codigo_nunca_ejecutado']) - 30} más (ver JSON)")
    lines.append("")
    lines.append(f"## Clases nunca instanciadas: **{len(audit['clases_nunca_instanciadas'])}**")
    for m in audit["clases_nunca_instanciadas"][:20]:
        lines.append(f"- `{m['modulo']}` → `{m['clase']}`")
    lines.append("")
    lines.append(f"## Reglas nunca utilizadas: **{len(audit['reglas_nunca_utilizadas'])}**")
    for r in audit["reglas_nunca_utilizadas"]:
        lines.append(f"- `{r['rule_id']}` campo=`{r['campo']}` estado=`{r['estado']}`")
    lines.append("")
    lines.append(f"## Campos imposibles: **{len(audit['campos_imposibles'])}**")
    for c in audit["campos_imposibles"]:
        lines.append(f"- `{c['campo']}` — {c['razon']}")
    lines.append("")
    cycles = audit["dependencias_circulares"]
    lines.append(f"## Dependencias circulares: **{len(cycles)}**")
    for c in cycles:
        lines.append(f"- {' -> '.join(c)}")
    lines.append("")
    lines.append(f"## Productores sin consumidores: **{len(audit['productores_sin_consumidores'])}**")
    for p in audit["productores_sin_consumidores"]:
        lines.append(f"- `{p['campo']}` — {p['razon']}")
    lines.append("")
    lines.append(f"## Consumidores sin productores: **{len(audit['consumidores_sin_productores'])}**")
    for c in audit["consumidores_sin_productores"]:
        lines.append(f"- `{c['campo']}` — {c['razon']}")
    lines.append("")
    lines.append(f"## Alias redundantes: **{len(audit['alias_redundantes'])}**")
    for a in audit["alias_redundantes"]:
        lines.append(f"- `{a['alias']}` ({a['par'][0]} <-> {a['par'][1]}) — {a['razon']}")
    lines.append(f"## Alias duplicados: **{len(audit['alias_duplicados'])}**")
    for a in audit["alias_duplicados"]:
        lines.append(f"- `{a['campo']}` -> `{a['alias']}` — {a['razon']}")
    lines.append("")
    lines.append(f"## Validaciones duplicadas: **{len(audit['validaciones_duplicadas'])}**")
    for v in audit["validaciones_duplicadas"]:
        if "campos" in v:
            lines.append(f"- {v['tipo']}: {v['campos']}")
        else:
            lines.append(f"- patrón `{v['patron']}` en {v['modulos']}")
    lines += ["", "## Metodología", ""]
    for m in audit["metodologia"]:
        lines.append(f"- {m}")
    lines.append("")
    return "\n".join(lines)
