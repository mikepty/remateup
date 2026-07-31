import sqlite3
import json
from collections import Counter

DB_PATH = r"backend\data\remateup.db"


def extract_baseline():
    db = sqlite3.connect(DB_PATH)

    avisos = db.execute("""SELECT id, documento_id, pais, codigo, expediente,
        demandante, demandado, base, fianza_porcentaje, minimo_porcentaje,
        confianza_promedio, estado, campos_faltantes_json
        FROM avisos""").fetchall()

    try:
        docs = db.execute(
            "SELECT id, pais, estado, length(texto_ocr) FROM documentos"
        ).fetchall()
    except sqlite3.OperationalError:
        docs = db.execute(
            "SELECT id, pais, estado, 0 FROM documentos"
        ).fetchall()

    total = len(avisos)
    estados = Counter(r[11] for r in avisos)
    paises = Counter(r[2] for r in avisos)
    confianzas = [r[10] for r in avisos if r[10] is not None]

    faltantes_total = Counter()
    for r in avisos:
        if r[12]:
            try:
                for f in json.loads(r[12]):
                    faltantes_total[f] += 1
            except (json.JSONDecodeError, TypeError):
                pass

    metrics = {
        "total_avisos": total,
        "total_documentos": len(docs),
        "por_pais": dict(paises),
        "por_estado": dict(estados),
        "confianza_promedio": round(sum(confianzas) / len(confianzas), 4) if confianzas else 0,
        "confianza_min": round(min(confianzas), 4) if confianzas else 0,
        "confianza_max": round(max(confianzas), 4) if confianzas else 0,
        "campos_faltantes_mas_comunes": faltantes_total.most_common(10),
        "auto_aprobados": estados.get("auto_aprobado", 0) + estados.get("subido", 0),
        "pendientes": estados.get("esperando_aprobacion", 0),
        "tasa_automatizacion": round(
            (estados.get("auto_aprobado", 0) + estados.get("subido", 0)) / total * 100, 1
        ) if total else 0,
    }

    db.close()
    return metrics


def compare_v1_v2(v1_metrics: dict, v2_metrics: dict) -> dict:
    comparison = {
        "total_avisos": {"v1": v1_metrics["total_avisos"], "v2": v2_metrics["total_avisos"]},
        "confianza_promedio": {"v1": v1_metrics["confianza_promedio"], "v2": v2_metrics.get("confianza_promedio", 0)},
        "tasa_automatizacion": {"v1": v1_metrics["tasa_automatizacion"], "v2": v2_metrics.get("tasa_automatizacion", 0)},
    }
    if v1_metrics["confianza_promedio"] > 0:
        comparison["confianza_delta"] = round(
            v2_metrics.get("confianza_promedio", 0) - v1_metrics["confianza_promedio"], 4
        )
    return comparison


if __name__ == "__main__":
    metrics = extract_baseline()
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
