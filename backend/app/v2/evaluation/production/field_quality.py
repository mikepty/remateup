"""FASE 12 — Parte 6: Field Quality Report.

Para cada campo del catálogo, por país, por parser y por documento:

  FOUND, NOT_FOUND, REQUIRES_REVIEW, FOUND POR PARSER, FOUND POR KNOWLEDGE,
  FOUND POR IA, FOUND POR VALIDATOR, FOUND FINAL.

Fuentes reales por campo (resultado de pipeline):
- FOUND/NOT_FOUND/REQUIRES_REVIEW : estado del campo en `fields`.
- FOUND POR PARSER/KNOWLEDGE/IA    : campo FOUND con `source` = parser/knowledge/ai.
- FOUND POR VALIDATOR              : campo listado en `validation.fields_found`
                                      (campos que el validator aceptó).
- FOUND FINAL                      : campo FOUND en el conjunto final.
"""

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from backend.app.v2.schema.definitions import get_definitions


def _iter_fields(result: dict) -> list[tuple[str, dict]]:
    fields = result.get("fields", {}) or {}
    return [(fname, fdata) for fname, fdata in fields.items() if isinstance(fdata, dict)]


def _validation_found(result: dict) -> set[str]:
    validation = result.get("validation", {}) or {}
    found = validation.get("fields_found") or []
    return set(found) if isinstance(found, list) else set()


def generate_field_quality_report(
    results: list[dict],
    out_dir: Optional[str] = None,
) -> dict:
    catalog = {d.field_name: d for d in get_definitions()}
    stats: dict[str, dict] = {}
    per_country: dict[str, dict] = {}
    per_parser: dict[str, dict] = {}
    per_document: dict[str, dict] = {}

    def _counter():
        return {"FOUND": 0, "NOT_FOUND": 0, "REQUIRES_REVIEW": 0,
                "FOUND_PARSER": 0, "FOUND_KNOWLEDGE": 0, "FOUND_IA": 0,
                "FOUND_VALIDATOR": 0, "FOUND_FINAL": 0}

    def bucket(root: dict, key: str) -> dict:
        return root.setdefault(key, _counter())

    for result in results:
        country = str(result.get("country", "")).upper()
        parser_name = f"{country} REMATE"
        document_id = str(result.get("document_id", "unknown"))
        validation_found = _validation_found(result)
        for fname, fdata in _iter_fields(result):
            status = fdata.get("status", "NOT_FOUND")
            source = fdata.get("source", "parser")
            found_final = status == "FOUND"
            found_parser = found_final and source == "parser"
            found_knowledge = found_final and source == "knowledge"
            found_ai = found_final and source == "ai"
            found_validator = fname in validation_found

            counters = [
                bucket(stats, fname),
                bucket(per_country.setdefault(country, {}), fname),
                bucket(per_parser.setdefault(parser_name, {}), fname),
                bucket(per_document.setdefault(document_id, {}), fname),
            ]
            for c in counters:
                c[status] += 1
                c["FOUND_PARSER"] += int(found_parser)
                c["FOUND_KNOWLEDGE"] += int(found_knowledge)
                c["FOUND_IA"] += int(found_ai)
                c["FOUND_VALIDATOR"] += int(found_validator)
                c["FOUND_FINAL"] += int(found_final)

    def materialize(root: dict) -> dict:
        return {k: dict(v) for k, v in root.items()}

    return {
        "total_documentos": len(results),
        "campos_catalogo": list(catalog.keys()),
        "por_campo": materialize(stats),
        "por_pais": {c: materialize(m) for c, m in per_country.items()},
        "por_parser": {p: materialize(m) for p, m in per_parser.items()},
        "por_documento": {d: materialize(m) for d, m in per_document.items()},
    }


def field_quality_to_json(report: dict) -> str:
    return json.dumps(report, ensure_ascii=False, indent=1, default=str)


def field_quality_to_markdown(report: dict) -> str:
    lines = ["# Field Quality Report (FASE 12)", ""]
    lines.append(f"- Documentos: **{report['total_documentos']}**")
    lines.append(f"- Campos del catálogo: **{len(report['campos_catalogo'])}**")
    lines += ["", "## Por campo", "",
              "| campo | FOUND | NOT_FOUND | REQUIRES_REVIEW | Parser | Knowledge | IA | Validator | Final |",
              "|---|---|---|---|---|---|---|---|---|"]
    for fname in report["campos_catalogo"]:
        s = report["por_campo"].get(fname, {})
        lines.append(
            f"| {fname} | {s.get('FOUND', 0)} | {s.get('NOT_FOUND', 0)} | {s.get('REQUIRES_REVIEW', 0)} | "
            f"{s.get('FOUND_PARSER', 0)} | {s.get('FOUND_KNOWLEDGE', 0)} | {s.get('FOUND_IA', 0)} | "
            f"{s.get('FOUND_VALIDATOR', 0)} | {s.get('FOUND_FINAL', 0)} |"
        )
    for section, title in (("por_pais", "Por país"), ("por_parser", "Por parser"),
                           ("por_documento", "Por documento")):
        lines += ["", f"## {title}", ""]
        for key, fields in report.get(section, {}).items():
            lines.append(f"### {key}")
            lines.append("| campo | FOUND | NOT_FOUND | REQUIRES_REVIEW | Parser | Knowledge | IA | Validator | Final |")
            lines.append("|---|---|---|---|---|---|---|---|---|")
            for fname, s in sorted(fields.items()):
                lines.append(
                    f"| {fname} | {s.get('FOUND', 0)} | {s.get('NOT_FOUND', 0)} | {s.get('REQUIRES_REVIEW', 0)} | "
                    f"{s.get('FOUND_PARSER', 0)} | {s.get('FOUND_KNOWLEDGE', 0)} | {s.get('FOUND_IA', 0)} | "
                    f"{s.get('FOUND_VALIDATOR', 0)} | {s.get('FOUND_FINAL', 0)} |"
                )
    lines.append("")
    return "\n".join(lines)


def write_field_quality_report(report: dict, out_dir: str) -> tuple[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    jp = out / "field_quality.json"
    mp = out / "field_quality.md"
    jp.write_text(field_quality_to_json(report), encoding="utf-8")
    mp.write_text(field_quality_to_markdown(report), encoding="utf-8")
    return str(jp), str(mp)
