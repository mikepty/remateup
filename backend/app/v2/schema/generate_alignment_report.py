"""FASE 8.20 — Generate the final completion audit reports.

Produces in backend/app/v2/schema/output/:
  alignment_report.json / alignment_report.md
  canonical_matrix.json  / canonical_matrix.md
  blocked_fields.json    / blocked_fields.md
  architecture_score.json / architecture_score.md
"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from backend.app.v2.schema.completion import (
    ArchitectureScoreReport,
    BlockedFieldsReport,
    CanonicalMatrixBuilder,
    CompletionAuditor,
)
from backend.app.v2.schema.coverage import ConsistencyReportGenerator, FieldMatrixGenerator
from backend.app.v2.schema.field_registry import REGISTRY

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _write(name: str, data) -> None:
    path = OUTPUT_DIR / name
    if name.endswith(".json"):
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    else:
        path.write_text(data, encoding="utf-8")
    print(f"  {path.relative_to(OUTPUT_DIR)}")


def main():
    auditor = CompletionAuditor()
    audit = auditor.run_full_audit()

    matrix_builder = CanonicalMatrixBuilder(auditor)
    blocked_report = BlockedFieldsReport(auditor)
    arch_score = ArchitectureScoreReport(auditor)

    print("Generating FASE 8.20 reports...")

    alignment = {
        "fase": "8.20",
        "titulo": "Canonical Schema Completion & Final Architecture Audit",
        "generado_en": datetime.now().isoformat(),
        "resumen": {
            "overall_alignment": audit["overall_alignment"],
            "total_fields": len(REGISTRY.field_names()),
            "certified_fields": audit["certified_fields"],
            "blocked_fields": audit["blocked_fields"],
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
        },
        "detalle_por_campo": audit["fields"],
        "scores": audit["scores"],
        "nota": (
            "Auditoria arquitectonica: no se modificaron parsers, OCR, knowledge, "
            "validator ni se agregaron campos. La Fase 9 solo podra iniciar cuando "
            "la lista de campos bloqueantes este resuelta."
        ),
    }
    alignment_md = [
        "# ALIGNMENT REPORT — FASE 8.20",
        "",
        f"**Generado:** {alignment['generado_en']}",
        f"**Overall alignment:** {audit['overall_alignment']}%",
        f"**Total campos:** {len(REGISTRY.field_names())}",
        f"**Certificados:** {len(audit['certified_fields'])} — {', '.join(f'`{f}`' for f in audit['certified_fields'])}",
        "",
        "## Verificaciones por campo (17 checks)",
        "",
        "| Campo | Schema | Parser | Knowledge | Validator | Normalizer | DB | API | Frontend | Export | Golden | Productor | Consumidor | Alias | Tipo | Formato | Deps | Doc |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for check in audit["fields"]:
        alignment_md.append(
            f"| `{check['field']}` | {'✔' if check['in_schema'] else '✘'} | "
            f"{'✔' if check['in_parser'] else '✘'} | "
            f"{'✔' if check['in_knowledge'] else '✘'} | "
            f"{'✔' if check['in_validator'] else '✘'} | "
            f"{'✔' if check['in_normalizer'] else '✘'} | "
            f"{'✔' if check['in_database'] else '✘'} | "
            f"{'✔' if check['in_api'] else '✘'} | "
            f"{'✔' if check['in_frontend'] else '✘'} | "
            f"{'✔' if check['in_export'] else '✘'} | "
            f"{'✔' if check['in_golden'] else '✘'} | "
            f"{'✔' if check['has_producer'] else '✘'} | "
            f"{'✔' if check['has_consumer'] else '✘'} | "
            f"{'✔' if check['has_alias'] else '✘'} | "
            f"{'✔' if check['type_ok'] else '✘'} | "
            f"{'✔' if check['format_ok'] else '✘'} | "
            f"{'✔' if check['deps_ok'] else '✘'} | "
            f"{'✔' if check['has_documentation'] else '✘'} |"
        )
    alignment_md += [
        "",
        "## Scores de alineación",
        "",
        "| Campo | Score |",
        "|---|---|",
    ]
    for f, score in audit["scores"].items():
        alignment_md.append(f"| `{f}` | {score}% |")
    alignment_md.append("")

    _write("alignment_report.json", alignment)
    _write("alignment_report.md", "\n".join(alignment_md))

    _write("canonical_matrix.json", matrix_builder.build())
    _write("canonical_matrix.md", matrix_builder.to_markdown())

    blocked_data = blocked_report.generate()
    _write("blocked_fields.json", blocked_data)
    _write("blocked_fields.md", blocked_report.to_markdown(blocked_data))

    arch_data = arch_score.generate()
    _write("architecture_score.json", arch_data)
    _write("architecture_score.md", arch_score.to_markdown(arch_data))

    print("Done.")


if __name__ == "__main__":
    main()
