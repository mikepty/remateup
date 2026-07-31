"""Field Auditor — scans V1 database, V1 extraction code, JSON exports, frontend,
and builds a complete inventory of ALL fields the client actually uses."""

import json
import os
import re
import sqlite3
from collections import Counter
from typing import Any, Optional


def _find_db() -> Optional[str]:
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "remateup.db"),
    ]
    for c in candidates:
        p = os.path.abspath(c)
        if os.path.exists(p):
            return p
    return None


def _find_v1_extraction() -> Optional[str]:
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "..", "pipeline", "extraction.py"),
    ]
    for c in candidates:
        p = os.path.abspath(c)
        if os.path.exists(p):
            return p
    return None


def _find_frontend() -> Optional[str]:
    p = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "frontend", "public", "index.html"))
    return p if os.path.exists(p) else None


def _find_debug_jsons() -> list[str]:
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
    found = []
    for root, dirs, files in os.walk(base):
        for f in files:
            if f.endswith("_avisos.json") or f.endswith("_debug.json") or f.endswith("_avisos_backup.json"):
                found.append(os.path.join(root, f))
    return found


def _find_export_code() -> Optional[str]:
    p = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "exports.py"))
    return p if os.path.exists(p) else None


def _find_platform_uploader() -> Optional[str]:
    p = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "platform_uploader.py"))
    return p if os.path.exists(p) else None


def _parse_python_fields(code: str) -> list[str]:
    fields = set()
    for m in re.finditer(r'["\'](\w+)["\']\s*[:=]', code):
        fields.add(m.group(1))
    for m in re.finditer(r'CAMPOS\s*=\s*\[([^\]]+)\]', code):
        for f in re.findall(r'["\'](\w+)["\']', m.group(1)):
            fields.add(f)
    for m in re.finditer(r'\b(\w+)\b.*#.*campo', code, re.IGNORECASE):
        fields.add(m.group(1))
    return sorted(fields)


def _parse_html_fields(html: str) -> list[str]:
    fields = set()
    for m in re.finditer(r'id=["\'](\w+)["\']', html):
        fields.add(m.group(1))
    for m in re.finditer(r'name=["\'](\w+)["\']', html):
        fields.add(m.group(1))
    for m in re.finditer(r'data-campo=["\'](\w+)["\']', html):
        fields.add(m.group(1))
    for m in re.finditer(r'\{\{\s*(\w+)\s*\}\}', html):
        fields.add(m.group(1))
    return sorted(fields)


def _scan_avisos_json(path: str) -> tuple[list[str], int]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = [data]
    fields: set[str] = set()
    for aviso in data:
        fields.update(aviso.keys())
    return sorted(fields), len(data)


def audit_all() -> dict:
    report: dict[str, Any] = {
        "v1_db_fields": [],
        "v1_extraction_fields": [],
        "v2_parser_fields": [],
        "frontend_fields": [],
        "export_fields": [],
        "platform_fields": [],
        "json_export_fields": [],
        "all_fields": {},
        "fields_in_v1_not_in_v2": [],
        "fields_in_v2_not_in_v1": [],
        "field_frequencies": {},
    }

    # 1. Database audit
    db_path = _find_db()
    if db_path:
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("PRAGMA table_info(avisos)")
        db_fields = [{"name": row[1], "type": row[2], "nullable": not row[3]} for row in cursor.fetchall()]
        report["v1_db_fields"] = [f["name"] for f in db_fields]
        report["v1_db_fields_detail"] = db_fields

        cursor = conn.execute("SELECT * FROM avisos LIMIT 50")
        rows = cursor.fetchall()
        col_names = [desc[0] for desc in cursor.description]
        field_freq: Counter = Counter()
        for row in rows:
            for i, val in enumerate(row):
                if val is not None and val != "":
                    field_freq[col_names[i]] += 1
        report["field_frequencies"] = dict(field_freq.most_common())
        conn.close()

    # 2. V1 extraction code
    ext_path = _find_v1_extraction()
    campos_list: list[str] = []
    if ext_path:
        with open(ext_path, encoding="utf-8") as f:
            code = f.read()
        campos_match = re.search(r'CAMPOS\s*=\s*\[(.*?)\]', code, re.DOTALL)
        if campos_match:
            campos_list = re.findall(r'["\'](\w+)["\']', campos_match.group(1))
        report["v1_campos_list"] = campos_list
        report["v1_extraction_code_fields"] = campos_list

    # 3. V2 parser fields
    v2_fields = ["expediente", "finca", "precio_base", "fecha_remate", "demandante", "demandado"]
    report["v2_parser_fields"] = v2_fields

    # 4. V2 all known fields (from document models)
    report["v2_known_fields"] = [
        "expediente", "finca", "precio_base", "fecha_remate", "demandante", "demandado",
        "fianza_porcentaje", "minimo_porcentaje", "codigo_ubicacion_prensa",
        "fecha", "hora", "lugar", "proceso", "categoria", "provincia",
        "descripcion", "descripcion_completa", "prevista", "plano", "lote_casa",
        "superficie", "periodico", "fecha_prensa", "pagina_prensa",
        "codigo_prensa", "email_observaciones", "codigo_fuente", "codigo_ubicacion",
    ]

    # 5. Frontend
    fe_path = _find_frontend()
    if fe_path:
        with open(fe_path, encoding="utf-8") as f:
            html = f.read()
        report["frontend_fields"] = _parse_html_fields(html)
        report["frontend_field_count"] = len(report["frontend_fields"])

    # 6. Export code
    exp_path = _find_export_code()
    if exp_path:
        with open(exp_path, encoding="utf-8") as f:
            code = f.read()
        report["export_code_fields"] = _parse_python_fields(code)

    # 7. Platform uploader
    plat_path = _find_platform_uploader()
    if plat_path:
        with open(plat_path, encoding="utf-8") as f:
            code = f.read()
        report["platform_upload_fields"] = _parse_python_fields(code)

    # 8. JSON exports
    json_files = _find_debug_jsons()
    json_fields: set[str] = set()
    total_avisos = 0
    _aviso_field_pattern = re.compile(r'^[a-z][a-z0-9_]*$')
    _known_aviso_prefixes = {"expediente", "finca", "base", "fianza", "minimo",
                              "demandante", "demandado", "fecha", "hora", "lugar",
                              "proceso", "categoria", "codigo", "provincia", "plano",
                              "lote", "superficie", "descripcion", "confianza", "pais",
                              "prevista", "periodico", "pagina", "email", "documento",
                              "aviso", "tipo", "estado", "campos", "texto"}
    for jf in json_files:
        fields, count = _scan_avisos_json(jf)
        for f in fields:
            if _aviso_field_pattern.match(f) and (
                any(f.startswith(p) for p in _known_aviso_prefixes)
                or f in ("id", "estado", "pais")
            ):
                json_fields.add(f)
        total_avisos += count
    report["json_export_fields"] = sorted(json_fields)
    report["json_export_avisos_count"] = total_avisos
    report["json_export_files"] = json_files

    # 9. Build unified field catalog
    all_sources = set()
    for key in ["v1_db_fields", "v1_extraction_code_fields", "frontend_fields",
                 "export_code_fields", "platform_upload_fields", "json_export_fields",
                 "v1_campos_list"]:
        if key in report:
            all_sources.update(report[key])
    all_sources.update(v2_fields)
    all_sources.update(report.get("v2_known_fields", []))

    # Build catalog with per-field metadata
    v1_campos_set = set(report.get("v1_campos_list", []))
    _exclude = {"id", "creado_en", "actualizado_en", "data", "contents", "parts", "role",
                "text", "key", "source", "type", "meta", "gemini", "gif", "jpeg", "jpg",
                "png", "webp", "pdf", "content", "datos",
                "generationConfig", "maxOutputTokens", "responseMimeType", "temperature",
                "systemInstruction", "media_type", "fields", "PA", "CO",
                "confianza", "campos", "aviso"}
    catalog = {}
    for field in sorted(all_sources):
        if not field or field.startswith("_") or field in _exclude:
            continue
        entry = {
            "name": field,
            "in_v1_db": field in report.get("v1_db_fields", []),
            "in_v1_extraction": field in v1_campos_set,
            "in_v2_parser": field in v2_fields,
            "in_v2_known": field in report.get("v2_known_fields", []),
            "in_frontend": field in report.get("frontend_fields", []),
            "in_exports": field in report.get("export_code_fields", []),
            "in_platform_upload": field in report.get("platform_upload_fields", []),
            "in_json_exports": field in report.get("json_export_fields", []),
            "frequency": report.get("field_frequencies", {}).get(field, 0),
            "priority": "unknown",
        }
        catalog[field] = entry

    # Assign priorities
    critical = {"expediente", "demandante", "demandado", "base", "finca_matr",
                "precio_base", "finca", "fecha_remate", "fecha"}
    high = {"fianza_porcentaje", "minimo_porcentaje", "codigo", "pais"}
    for field, entry in catalog.items():
        if field in critical:
            entry["priority"] = "critical"
        elif field in high:
            entry["priority"] = "high"
        elif entry["frequency"] >= 10:
            entry["priority"] = "high"
        elif entry["frequency"] >= 3:
            entry["priority"] = "medium"
        elif entry["frequency"] > 0:
            entry["priority"] = "low"
        else:
            entry["priority"] = "unknown"

    report["field_catalog"] = catalog
    report["total_fields"] = len(catalog)

    # Fields in V1 not in V2
    v1_extraction_fields = set(report.get("v1_campos_list", []))
    v1_db_meta = set(report.get("v1_db_fields", [])) - v1_extraction_fields
    v2_set = set(v2_fields) | set(report.get("v2_known_fields", []))
    report["fields_in_v1_not_in_v2"] = sorted(v1_extraction_fields - v2_set)
    report["fields_in_v2_not_in_v1"] = sorted(v2_set - v1_extraction_fields)
    report["v1_db_metadata_fields"] = sorted(v1_db_meta)

    # Count by priority
    priority_counts = Counter()
    for entry in catalog.values():
        priority_counts[entry["priority"]] += 1
    report["fields_by_priority"] = dict(priority_counts)

    return report


def generate_field_catalog_md(report: dict) -> str:
    lines = [
        "# FIELD CATALOG — Complete Inventory of Extraction Fields\n",
        "## Generado automáticamente por FASE 6.8 Field Auditor\n",
        f"**Total de campos únicos encontrados:** {report.get('total_fields', 0)}\n",
        f"**Campos en V1 que NO existen en V2:** {len(report.get('fields_in_v1_not_in_v2', []))}\n",
        f"**Campos en V2 que NO existen en V1:** {len(report.get('fields_in_v2_not_in_v1', []))}\n",
        "---\n",
        "## Catálogo de Campos\n",
        "| Campo | Prioridad | V1 DB | V1 Extracción | V2 Parser | Frontend | Export | Frecuencia |\n",
        "|---|---|---|---|---|---|---|\n",
    ]
    catalog = report.get("field_catalog", {})
    for field_name in sorted(catalog.keys()):
        entry = catalog[field_name]
        lines.append(
            f"| `{field_name}` | {entry['priority']} | "
            f"{'✓' if entry['in_v1_db'] else '✗'} | "
            f"{'✓' if entry['in_v1_extraction'] else '✗'} | "
            f"{'✓' if entry['in_v2_parser'] else '✗'} | "
            f"{'✓' if entry['in_frontend'] else '✗'} | "
            f"{'✓' if entry['in_exports'] else '✗'} | "
            f"{entry['frequency']} |\n"
        )

    lines.extend([
        "\n---\n",
        "## Campos en V1 que faltan en V2\n",
    ])
    for field in report.get("fields_in_v1_not_in_v2", []):
        lines.append(f"- `{field}`\n")

    lines.extend([
        "\n---\n",
        "## Distribución por Prioridad\n",
    ])
    for pri, cnt in sorted(report.get("fields_by_priority", {}).items()):
        lines.append(f"- **{pri}**: {cnt} campos\n")

    return "".join(lines)
