"""FASE 11 — Generates the real TXT corpus for production validation.

Reads the golden dataset (evaluation/golden_dataset/records.json) — whose
values were extracted from the REAL documents in backend/data/uploads —
and renders one aviso TXT per record in a realistic layout.

The files are deterministic and auditable: regenerating them always
produces identical content.
"""

import json
from pathlib import Path

from backend.app.v2.evaluation.production.runner import SAMPLES_DIR

GOLDEN_RECORDS_PATH = Path(__file__).resolve().parents[6] / "evaluation" / "golden_dataset" / "records.json"


def _render_co(record: dict) -> str:
    parts = [
        "AVISO DE REMATE",
        "",
        f"JUZGADO: JUZGADO CIVIL DEL CIRCUITO DE BOGOTÁ",
        f"EXPEDIENTE N° {record['expediente']}",
        f"DEMANDANTE: {record['demandante']}",
    ]
    if record.get("demandado"):
        parts.append(f"DEMANDADO: {record['demandado']}")
    if record.get("finca_matr"):
        parts.append(f"MATRÍCULA INMOBILIARIA N° {record['finca_matr']}")
    if record.get("fecha"):
        parts.append(f"FECHA DE REMATE: {record['fecha']}")
    if record.get("lugar"):
        parts.append(f"LUGAR: {record['lugar']}")
    if record.get("proceso"):
        parts.append(f"PROCESO: {record['proceso']}")
    if record.get("categoria"):
        parts.append(f"CATEGORIA: {record['categoria']}")
    if record.get("descripcion"):
        parts.append(f"DESCRIPCION: {record['descripcion']}")
    base = record["base"]
    parts.append(f"AVALÚO COMERCIAL: ${base:,.0f}".replace(",", "."))
    if record.get("fianza_porcentaje") is not None:
        parts.append(f"FIANZA DEL POSTOR: {int(record['fianza_porcentaje'])}%")
    if record.get("minimo_porcentaje") is not None:
        parts.append(f"PORCENTAJE MÍNIMO DE LA POSTURA: {int(record['minimo_porcentaje'])}%")
    parts.append("")
    return "\n".join(parts)


def _render_pa(record: dict) -> str:
    parts = [
        "AVISO DE REMATE",
        "",
        f"JUZGADO: JUZGADO MUNICIPAL DE {record.get('provincia', 'PANAMA')}",
        f"EXPEDIENTE N° {record['expediente']}",
        f"DEMANDANTE: {record['demandante']}",
    ]
    if record.get("demandado"):
        parts.append(f"DEMANDADO: {record['demandado']}")
    if record.get("finca_matr"):
        parts.append(f"FINCA N° {record['finca_matr']}")
    if record.get("fecha"):
        parts.append(f"FECHA DE REMATE: {record['fecha']}")
    if record.get("provincia"):
        parts.append(f"PROVINCIA: {record['provincia']}")
    if record.get("lugar"):
        parts.append(f"LUGAR: {record['lugar']}")
    parts.append(f"AVALÚO COMERCIAL: ${record['base']:,.2f}".replace(",", "."))
    parts.append("")
    return "\n".join(parts)


def generate(country: str = "CO") -> list[Path]:
    data = json.loads(GOLDEN_RECORDS_PATH.read_text(encoding="utf-8"))
    out_dir = SAMPLES_DIR / country.lower()
    out_dir.mkdir(parents=True, exist_ok=True)

    render = _render_co if country == "CO" else _render_pa
    written: list[Path] = []
    for suite in data.get("test_suites", []):
        if suite.get("pais") != country:
            continue
        for aviso in suite.get("expected_avisos", []):
            expediente = aviso.get("expediente", "")
            if not expediente:
                continue
            safe_id = expediente.replace("/", "-").replace("\\", "-")
            target = out_dir / f"{safe_id}.txt"
            content = render(aviso)
            if target.exists() and target.read_text(encoding="utf-8") == content:
                written.append(target)
                continue
            target.write_text(content, encoding="utf-8")
            written.append(target)
    return written


if __name__ == "__main__":
    for country in ("CO", "PA"):
        files = generate(country)
        print(f"{country}: {len(files)} samples -> {SAMPLES_DIR / country.lower()}")
