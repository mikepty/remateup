"""FASE 12 — Parte 5: Knowledge Impact Report.

Reporte histórico por regla de conocimiento:

  veces usada, aciertos, fallos, accuracy, último uso, primer uso, campo,
  país, categoría, top reglas, top reglas fallidas, reglas nunca usadas,
  reglas expiradas.

Limitaciones reales documentadas:
- La tabla knowledge_rules NO almacena el país de la regla: se deriva de la
  tabla corrections cuando la regla nació de una corrección; si no, "N/A".
- La tabla NO almacena el instante del primer uso: `created_at` es la fecha de
  alta (proxy documentado con `primer_uso_exacto: false`).
- `updated_at` se actualiza en cada uso/guardado: se reporta como último uso.
"""

import json
from datetime import datetime
from typing import Any, Optional

from backend.app.v2.knowledge.repository import KnowledgeRepository


def _iso_to_date(value: str) -> str:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except (ValueError, TypeError, AttributeError):
        return str(value)


def generate_knowledge_impact_report(
    repository: Optional[KnowledgeRepository] = None,
    out_dir: Optional[str] = None,
) -> dict:
    repo = repository or KnowledgeRepository()
    rules = repo.get_rules()
    corrections = repo.get_corrections()

    country_by_doc: dict[str, str] = {}
    for c in corrections:
        if c.document_id:
            country_by_doc.setdefault(c.document_id, c.country)

    def country_for(rule) -> str:
        origin = rule.created_from_correction or ""
        if origin and origin in country_by_doc:
            return country_by_doc[origin]
        return "N/A"

    per_rule: list[dict] = []
    for rule in rules:
        uses = rule.usage_count or 0
        success = rule.success_count or 0
        fail = rule.fail_count or 0
        per_rule.append({
            "rule_id": rule.rule_id,
            "campo": rule.field_name,
            "categoria": rule.category or "N/A",
            "pais": country_for(rule),
            "estado": rule.status,
            "veces_usada": uses,
            "aciertos": success,
            "fallos": fail,
            "accuracy": round(success / uses, 4) if uses else 0.0,
            "ultimo_uso": _iso_to_date(rule.updated_at),
            "primer_uso": _iso_to_date(rule.created_at),
            "primer_uso_exacto": False,
            "confianza": rule.confidence,
            "pattern": rule.pattern[:120],
        })

    used = [r for r in per_rule if r["veces_usada"] > 0]
    failed = [r for r in used if r["fallos"] > 0]
    never_used = [r for r in per_rule if r["veces_usada"] == 0]
    expired = [r for r in per_rule if r["estado"] == "INACTIVE"]

    report = {
        "total_reglas": len(per_rule),
        "reglas_usadas": len(used),
        "reglas_nunca_usadas": never_used,
        "reglas_nunca_usadas_count": len(never_used),
        "reglas_expiradas": expired,
        "reglas_expiradas_count": len(expired),
        "top_reglas": sorted(used, key=lambda r: r["veces_usada"], reverse=True)[:10],
        "top_reglas_fallidas": sorted(failed, key=lambda r: r["fallos"], reverse=True)[:10],
        "por_regla": per_rule,
        "limitaciones": [
            "pais_no_almacenado_en_knowledge_rules: derivado de corrections cuando la regla nacio de una correccion, si no N/A",
            "primer_uso_exacto_no_almacenado: se usa created_at (alta) como proxy",
            "ultimo_uso = updated_at (se actualiza en cada uso y cada guardado)",
        ],
    }

    if out_dir:
        from pathlib import Path

        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "knowledge_impact.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        (out / "knowledge_impact.md").write_text(_to_markdown(report), encoding="utf-8")
    return report


def _to_markdown(report: dict) -> str:
    lines = [
        "# Knowledge Impact Report (FASE 12)",
        "",
        f"- Total reglas: **{report['total_reglas']}**",
        f"- Reglas usadas: **{report['reglas_usadas']}**",
        f"- Reglas nunca usadas: **{report['reglas_nunca_usadas_count']}**",
        f"- Reglas expiradas (INACTIVE): **{report['reglas_expiradas_count']}**",
        "",
        "## Top reglas",
        "",
        "| rule_id | campo | categoría | país | usos | aciertos | fallos | accuracy |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in report["top_reglas"]:
        lines.append(
            f"| {r['rule_id']} | {r['campo']} | {r['categoria']} | {r['pais']} | "
            f"{r['veces_usada']} | {r['aciertos']} | {r['fallos']} | {r['accuracy']} |"
        )
    lines += ["", "## Top reglas fallidas", "", "| rule_id | campo | fallos | usos | accuracy |", "|---|---|---|---|---|"]
    for r in report["top_reglas_fallidas"]:
        lines.append(
            f"| {r['rule_id']} | {r['campo']} | {r['fallos']} | {r['veces_usada']} | {r['accuracy']} |"
        )
    lines += ["", "## Reglas nunca usadas", ""]
    for r in report["reglas_nunca_usadas"]:
        lines.append(f"- `{r['rule_id']}` campo=`{r['campo']}` estado=`{r['estado']}`")
    lines += ["", "## Reglas expiradas", ""]
    for r in report["reglas_expiradas"]:
        lines.append(f"- `{r['rule_id']}` campo=`{r['campo']}` accuracy={r['accuracy']}")
    lines += ["", "## Limitaciones", ""]
    for l in report["limitaciones"]:
        lines.append(f"- {l}")
    lines.append("")
    return "\n".join(lines)
