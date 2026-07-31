"""FASE 13 — Tests: Real World Accuracy Optimization (Panamá Prioritario).

Cubre las Partes 1-14 del prompt 13:
  corpus estadístico real, country_statistics, pattern discovery, coverage,
  sugerencias de knowledge, knowledge analytics, parser gap, false positives,
  dashboard de precisión y orquestador phase13 (artefactos + determinismo).

Verifica que el análisis NO escribe knowledge.db, NO aprueba sugerencias y NO
modifica parsers. No se elimina ni modifica ningún test anterior.
"""

import json
import math
import shutil
from pathlib import Path

import pytest

from backend.app.v2.evaluation.accuracy.corpus import (
    build_corpus,
    country_statistics,
    statistics_to_markdown,
)
from backend.app.v2.evaluation.accuracy.pattern_discovery import (
    discover,
    discovery_to_markdown,
)
from backend.app.v2.evaluation.accuracy.coverage import (
    coverage_analysis,
    coverage_to_markdown,
)
from backend.app.v2.evaluation.accuracy.suggestions import (
    generate_suggestions,
    suggestions_to_markdown,
)
from backend.app.v2.evaluation.accuracy.knowledge_analytics import (
    knowledge_analytics,
    analytics_to_markdown,
)
from backend.app.v2.evaluation.accuracy.parser_gap import (
    parser_gap_report,
    gap_to_markdown,
)
from backend.app.v2.evaluation.accuracy.false_positive import (
    false_positive_report,
    fp_to_markdown,
)
from backend.app.v2.evaluation.accuracy.dashboard import (
    accuracy_dashboard,
    dashboard_to_markdown,
)
from backend.app.v2.evaluation.accuracy.phase13 import run_phase13, OUTPUT_DIR

ARTIFACTS = [
    "production_accuracy", "country_statistics", "pattern_discovery",
    "coverage_real", "false_positive_report", "parser_gap",
    "knowledge_suggestions", "knowledge_analytics",
]

PANAMA_FIRST = {"precio_base": "base"}


def approx(a, b, tol=0.001):
    return math.isclose(a, b, rel_tol=tol, abs_tol=tol)


# --------------------------------------------------------------------------
# Parte 1-2: Corpus y country_statistics
# --------------------------------------------------------------------------

def test_corpus_tiene_72_documentos():
    docs = build_corpus()
    assert len(docs) == 72


def test_corpus_panama_primero():
    docs = build_corpus()
    assert docs[0].country == "PA"
    assert docs[-1].country == "CO"
    pa = [d for d in docs if d.country == "PA"]
    assert all(d.country == "PA" for d in docs[: len(pa)])


def test_corpus_32_pa_y_40_co():
    docs = build_corpus()
    assert len([d for d in docs if d.country == "PA"]) == 32
    assert len([d for d in docs if d.country == "CO"]) == 40


def test_corpus_fuentes_pa():
    docs = build_corpus()
    from collections import Counter
    c = Counter(d.source for d in docs if d.country == "PA")
    assert c["upload_ocr"] == 13, "13 imágenes PA con OCR real"
    assert c["sample"] == 6, "6 avisos canónicos del cliente"
    assert c["parser_validation"] == 7
    assert c["golden"] == 6


def test_corpus_fuentes_co():
    docs = build_corpus()
    from collections import Counter
    c = Counter(d.source for d in docs if d.country == "CO")
    assert c["upload_ocr"] == 5
    assert c["sample"] == 16
    assert c["parser_validation"] == 3
    assert c["golden"] == 16


def test_corpus_determinista():
    a = [d.document_id for d in build_corpus()]
    b = [d.document_id for d in build_corpus()]
    assert a == b


def test_corpus_incluye_imagenes_reales_pa():
    docs = build_corpus()
    ids = {d.document_id for d in docs if d.country == "PA"}
    for img in ("imagen1.jpg", "9a1ef910_1.jpg", "IMG-20260710-WA0018.jpg"):
        assert img in ids


def test_corpus_upload_ocr_tiene_texto_real():
    for d in build_corpus():
        if d.country == "PA" and d.source == "upload_ocr":
            assert d.chars > 2000, f"{d.document_id} tiene texto insuficiente"


def test_corpus_golden_tiene_ground_truth():
    docs = build_corpus()
    for d in docs:
        if d.source == "golden":
            assert d.ground_truth is not None


def test_country_statistics_pa_headers():
    stats = country_statistics("PA", build_corpus())
    headers = stats["headers"]
    assert any("AVISO DE REMATE" in h for h in headers)
    assert any("EDICTO EMPLAZATORIO" in h for h in headers)


def test_country_statistics_pa_etiquetas():
    stats = country_statistics("PA", build_corpus())
    keys = list(stats["etiquetas"].keys())
    assert any("JUZGADO" in k for k in keys)
    assert any("FINCA" in k for k in keys)
    assert any("EXPEDIENTE" in k or "EXPE" in k for k in keys)


def test_country_statistics_pa_formatos_monetarios():
    stats = country_statistics("PA", build_corpus())
    assert len(stats["formatos_monetarios"]) >= 5


def test_country_statistics_pa_expedientes():
    stats = country_statistics("PA", build_corpus())
    assert len(stats["expedientes"]) >= 5


def test_country_statistics_pa_juzgados():
    stats = country_statistics("PA", build_corpus())
    assert len(stats["juzgados"]) >= 5


def test_country_statistics_pa_provincias():
    stats = country_statistics("PA", build_corpus())
    assert any("PANAMA" in p for p in stats["provincias"])


def test_country_statistics_co_headers():
    stats = country_statistics("CO", build_corpus())
    headers = stats["headers"]
    assert any("REMATE" in h.upper() for h in headers)


def test_statistics_to_markdown_pa_primero():
    md = statistics_to_markdown(country_statistics("PA", build_corpus()))
    assert "Panamá First" in md
    assert "## Estadísticas país: PA" in md


# --------------------------------------------------------------------------
# Parte 5: Pattern Discovery Engine
# --------------------------------------------------------------------------

def _pd_pa():
    docs = build_corpus()
    return discover([d.text for d in docs if d.country == "PA"], "PA")


def test_discovery_variantes_labels():
    pd = _pd_pa()
    var = pd.to_dict()["variantes_labels"]
    assert "JUZGADO" in var
    assert "FINCA" in var
    assert "EXPEDIENTE" in var or "EXPE" in var


def test_discovery_palabras_partidas_ocr():
    pd = _pd_pa()
    partidas = pd.to_dict()["palabras_partidas"]
    assert any("JUDI-CIAL" in k for k in partidas), "OCR parte JUDICIAL en JUDI-CIAL"
    assert any("CIR-CUITO" in k for k in partidas)


def test_discovery_palabras_unidas():
    pd = _pd_pa()
    unidas = pd.to_dict()["palabras_unidas"]
    assert any("JUDI+CIAL" in k for k in unidas)
    assert any("JUZ+GADO" in k for k in unidas)


def test_discovery_acentos_perdidos():
    pd = _pd_pa()
    acentos = pd.to_dict()["acentos_perdidos"]
    assert any("PANAMA" in k for k in acentos)


def test_discovery_simbolos_n_variantes():
    pd = _pd_pa()
    simbolos = pd.to_dict()["simbolos"]
    assert any("N°" in s for s in simbolos)


def test_discovery_pa_no_vacio():
    pd = _pd_pa().to_dict()
    assert len(pd["palabras_partidas"]) >= 5
    assert len(pd["palabras_unidas"]) >= 5
    assert len(pd["acentos_perdidos"]) >= 5


def test_discovery_to_markdown():
    md = discovery_to_markdown(_pd_pa())
    assert "PA" in md


def test_discovery_co_tiene_grid():
    docs = build_corpus()
    pd = discover([d.text for d in docs if d.country == "CO"], "CO").to_dict()
    assert pd["pais"] == "CO"


# --------------------------------------------------------------------------
# Parte 6: Coverage Analyzer
# --------------------------------------------------------------------------

def _coverage():
    return coverage_analysis(build_corpus())


def test_coverage_33_campos_en_catalogo():
    cov = _coverage()
    report = cov["por_campo_catalogo"]
    assert len(report) == 33
    assert all(v["en_catalogo"] for v in report.values())


def test_coverage_juzgado_evidencia_real_pa():
    cov = _coverage()
    assert cov["por_pais"]["PA"]["evidencia_textual"].get("juzgado", 0) > 0


def test_coverage_matricula_es_finca():
    cov = _coverage()
    assert cov["por_campo_catalogo"]["finca"]["evidencia_pa"] > 0


def test_coverage_avaluo_es_precio_base():
    cov = _coverage()
    assert cov["por_campo_catalogo"]["precio_base"]["evidencia_pa"] > 0


def test_coverage_campos_que_faltan_en_catalogo():
    cov = _coverage()
    assert set(cov["campos_faltan"].keys()) == {"juzgado", "municipio"}
    assert cov["campos_faltan"]["juzgado"]["evidencia_pa"] > 0
    assert cov["campos_faltan"]["municipio"]["evidencia_co"] > 0
    for nombre, info in cov["campos_faltan"].items():
        assert info["en_catalogo"] is False
        assert info["evidencia_pa"] + info["evidencia_co"] > 0


def test_coverage_exclusivos_pa():
    cov = _coverage()
    assert cov["campos_exclusivos_pa"] == ["lugar", "provincia"]


def test_coverage_exclusivos_co():
    cov = _coverage()
    assert set(cov["campos_exclusivos_co"]) == {"fianza_porcentaje", "minimo_porcentaje"}


def test_coverage_hay_campos_nunca_aparecen():
    cov = _coverage()
    assert len(cov["campos_nunca_aparecen"]) > 5


def test_coverage_por_campo_headers_pa():
    cov = _coverage()
    texto = cov["por_pais"]["PA"]["evidencia_textual"]
    assert texto.get("juzgado", 0) > 0
    assert texto.get("expediente", 0) > 0


def test_coverage_to_markdown():
    md = coverage_to_markdown(_coverage())
    assert "Coverage" in md
    assert "juzgado" in md


# --------------------------------------------------------------------------
# Partes 4+7: Sugerencias y Knowledge Analytics
# --------------------------------------------------------------------------

def _sugerencias():
    docs = build_corpus()
    return generate_suggestions(
        [d.text for d in docs if d.country == "PA"],
        [d.text for d in docs if d.country == "CO"],
    )


def test_sugerencias_total_53():
    sug = _sugerencias()
    assert sug["total_sugerencias"] == 53


def test_sugerencias_nunca_aprobadas():
    sug = _sugerencias()
    assert sug["nunca_aprobadas_automaticamente"] is True
    assert all(s.get("aprobado") is False for s in sug["sugerencias"])


def test_sugerencias_incluyen_avaluo_comercial():
    sug = _sugerencias()
    items = json.dumps(sug, ensure_ascii=False)
    assert "AVAL" in items and "COMERCIAL" in items


def test_sugerencias_tipos():
    sug = _sugerencias()
    tipos = {s["tipo"] for s in sug["sugerencias"]}
    assert "alias" in tipos
    assert "expresion" in tipos
    assert "label_nuevo" in tipos


def test_sugerencias_pa_primero():
    sug = _sugerencias()
    assert sug["sugerencias"][0]["pais"] == "PA"
    pa = [s for s in sug["sugerencias"] if s["pais"] == "PA"]
    assert all(s["pais"] == "PA" for s in sug["sugerencias"][: len(pa)])


def test_suggestions_to_markdown():
    md = suggestions_to_markdown(_sugerencias())
    assert "Sugerencias" in md


def test_knowledge_db_real_vacia():
    k = knowledge_analytics()
    assert k["knowledge_db"] == {"reglas": 0, "correcciones": 0}


def test_knowledge_no_crea_reglas():
    k = knowledge_analytics()
    assert k["reglas_creadas"] == 0


def test_knowledge_por_que_esta_vacia():
    k = knowledge_analytics()
    assert len(k["por_que_esta_vacia"]["razones"]) >= 3


def test_knowledge_reglas_utiles_no_vacio():
    k = knowledge_analytics()
    assert len(k["reglas_utiles"]) >= 5


def test_knowledge_evidencia_por_pais():
    k = knowledge_analytics()
    assert k["evidencia_por_pais"]["PA"] > 0
    assert k["evidencia_por_pais"]["CO"] > 0


def test_knowledge_analytics_to_markdown():
    md = analytics_to_markdown(knowledge_analytics())
    assert "Knowledge Analytics" in md
    assert "NINGUNA regla" in md


# --------------------------------------------------------------------------
# Parte 8: Parser Gap
# --------------------------------------------------------------------------

def _gap():
    return parser_gap_report()


def test_gap_fuentes_co_anclados():
    gap = _gap()
    assert gap["fuentes"]["co_avisos_anclados"] == 63


def test_gap_fuentes_pa():
    gap = _gap()
    assert gap["fuentes"]["pa_canonicos_cliente"] == 24
    assert gap["fuentes"]["pa_parser_validation"] == 34
    assert gap["fuentes"]["pa_imagenes_benchmark"] == 78


def test_gap_rows():
    gap = _gap()
    assert len(gap["rows"]) == 199
    assert gap["filas_con_golden"] == 121


def test_gap_perdidas_totales_69():
    gap = _gap()
    assert gap["perdidas_totales"] == 69


def test_gap_parser_pierde_69():
    gap = _gap()
    resumen = gap["resumen_por_etapa"]
    assert resumen["parser_pierde"] == 69
    assert resumen["ocr_pierde"] == 0
    assert resumen["knowledge_pierde"] == 0


def test_gap_validator_certifica_invalid():
    gap = _gap()
    assert gap["resumen_por_etapa"]["validator_certificacion"].get("INVALID") == 63


def test_gap_precio_base_se_pierde_en_parser():
    gap = _gap()
    perdido = gap["donde_se_pierde_por_campo"]
    assert perdido["precio_base"]["se_pierde_en_parser"] == 22


def test_gap_no_rompe_anclado():
    gap = _gap()
    assert gap["resumen_por_etapa"]["ia_recupera"] == 0
    assert gap["resumen_por_etapa"]["ia_no_recupera"] == 0


def test_gap_to_markdown():
    md = gap_to_markdown(_gap())
    assert "Parser Gap" in md


# --------------------------------------------------------------------------
# Parte 9: False Positive Report
# --------------------------------------------------------------------------

def _fp():
    return false_positive_report()


def test_fp_descartados():
    fp = _fp()
    assert fp["totales"]["descartados_correctos"] == 1
    assert fp["totales"]["descartados_incorrectos"] == 0


def test_fp_duplicados():
    fp = _fp()
    assert fp["totales"]["duplicados"] == 27
    dup = fp["duplicados"]
    assert "32852-2026" in dup, "el mismo expediente real aparece en 3 imágenes"
    assert "153929" in dup, "expediente CO repetido entre PDFs SEJURE y extras"


def test_fp_falsos_duplicados():
    fp = _fp()
    assert fp["totales"]["falsos_duplicados"] == 10


def test_fp_rechazados_e_invalidos():
    fp = _fp()
    assert fp["totales"]["rechazados"] == 16
    assert fp["totales"]["invalidos_aceptados"] == 6


def test_fp_no_incluye_golden_sinteticos():
    fp = _fp()
    docs = [d["documento"] for d in fp["avisos_descartados_incorrectamente"]]
    assert docs == [], "golden sintético no debe contarse como página real"


def test_fp_to_markdown():
    md = fp_to_markdown(_fp())
    assert "False Positive" in md


# --------------------------------------------------------------------------
# Parte 13: Dashboard de Precisión
# --------------------------------------------------------------------------

def _acc():
    return accuracy_dashboard()


def test_dashboard_panama_precision_1():
    pa = _acc()["panama"]
    assert pa["tp"] == 52
    assert pa["fp"] == 0
    assert pa["fn"] == 6
    assert approx(pa["precision"], 1.0)
    assert approx(pa["recall"], 0.8966)
    assert approx(pa["f1"], 0.9455)


def test_dashboard_panama_por_campo():
    pa = _acc()["panama"]
    por = pa["por_campo"]
    assert por["expediente"]["recall"] == 1.0
    assert por["demandante"]["recall"] == 1.0
    assert por["demandado"]["recall"] == 1.0
    assert por["precio_base"]["recall"] == 0.5, "AVALÚO COMERCIAL no cubierto por parser PA"
    assert por["precio_base"]["fn"] == 6


def test_dashboard_colombia_cero():
    co = _acc()["colombia"]
    assert co["tp"] == 0
    assert co["fp"] == 0
    assert co["recall"] == 0.0


def test_dashboard_por_parser():
    acc = _acc()
    assert "PA REMATE" in acc["por_parser"]
    assert "CO REMATE" in acc["por_parser"]


def test_dashboard_cobertura_por_campo():
    acc = _acc()
    cob = acc["cobertura_por_campo"]
    assert cob["precio_base"]["cobertura_pa"] == 0.5
    assert cob["expediente"]["cobertura_pa"] == 1.0
    assert cob["expediente"]["cobertura_co"] == 0.0


def test_dashboard_cobertura_por_pais():
    acc = _acc()
    assert acc["cobertura_por_pais"]["PA"]["documentos"] == 32
    assert acc["cobertura_por_pais"]["CO"]["documentos"] == 40


def test_dashboard_campos_por_origen():
    acc = _acc()
    assert acc["campos_knowledge"] == 0
    assert acc["campos_ia"] == {"fuente": "benchmark FASE 12", "detalle": 0}
    assert acc["campos_parser"] == 52
    assert acc["campos_perdidos"] == 69


def test_dashboard_markdown_panama_primero():
    md = dashboard_to_markdown(_acc())
    assert md.index("Panamá") < md.index("Colombia")
    assert "Cobertura por campo" in md


# --------------------------------------------------------------------------
# Parte 12: Orquestador phase13 (artefactos + determinismo)
# --------------------------------------------------------------------------

def _run():
    return run_phase13()


def test_phase13_escribe_todos_los_artefactos():
    _run()
    for name in ARTIFACTS:
        assert (OUTPUT_DIR / f"{name}.json").exists(), f"falta {name}.json"
        assert (OUTPUT_DIR / f"{name}.md").exists(), f"falta {name}.md"
    assert (OUTPUT_DIR / "phase13_summary.json").exists()


def test_phase13_resumen():
    s = _run()["resumen"]
    assert s["documentos_analizados"] == 72
    assert s["pa"] == 32
    assert s["co"] == 40
    assert s["reglas_creadas"] == 0
    assert s["sugerencias"] == 53
    assert approx(s["recall_pa"], 0.8966)
    assert approx(s["f1_pa"], 0.9455)


def test_phase13_determinista():
    a = json.loads((OUTPUT_DIR / "phase13_summary.json").read_text(encoding="utf-8"))
    _run()
    b = json.loads((OUTPUT_DIR / "phase13_summary.json").read_text(encoding="utf-8"))
    a.pop("timestamp", None)
    b.pop("timestamp", None)
    a.pop("tiempo_total_ms", None)
    b.pop("tiempo_total_ms", None)
    assert a == b


def test_phase13_artefactos_validos_json():
    _run()
    for name in ARTIFACTS:
        data = json.loads((OUTPUT_DIR / f"{name}.json").read_text(encoding="utf-8"))
        assert data, f"{name}.json vacío"


def test_phase13_orden_panama_primero():
    _run()
    for name in ("country_statistics", "pattern_discovery"):
        data = json.loads((OUTPUT_DIR / f"{name}.json").read_text(encoding="utf-8"))
        assert data["orden"] == ["PA", "CO"]


def test_phase13_no_modifica_knowledge_db():
    db = OUTPUT_DIR.parents[2] / "knowledge" / "knowledge.db"
    assert db.exists()
    antes = db.stat().st_mtime_ns
    _run()
    assert db.stat().st_mtime_ns == antes, "phase13 no debe escribir knowledge.db"


def test_phase13_no_modifica_parsers():
    parser_pa = OUTPUT_DIR.parents[2] / "parser" / "documents" / "panama_remate.py"
    assert parser_pa.exists()
    antes = parser_pa.read_text(encoding="utf-8")
    _run()
    assert parser_pa.read_text(encoding="utf-8") == antes


def test_phase13_artefactos_md_no_vacios():
    _run()
    for name in ARTIFACTS:
        md = (OUTPUT_DIR / f"{name}.md").read_text(encoding="utf-8")
        assert len(md) > 200, f"{name}.md demasiado corto"
