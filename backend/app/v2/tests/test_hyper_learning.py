"""Tests FASE 14 — Hyper Learning / Intelligence / Prediction engines.

Los motores de `backend/app/learning/engine.py` son puros (reciben dicts,
devuelven dicts), así que son totalmente testeables sin tocar la base de datos
ni la V2: garantizan determinismo, serialización y reproducibilidad (Parte 1/2).
NO modifican Knowledge/Parser/Validator: solo emiten sugerencias.
"""
import json as _json

from backend.app.learning.engine import (
    generar_sugerencias,
    inteligencia_aviso,
    predecir,
)
from backend.app.learning.reports import BUILDERS, available_reports
from backend.app.routers.admin_ext import _auditar_ui

# Invariantes globales ------------------------------------------------------
# 1) fianza / minimo (montos y porcentajes) NO están en la superficie de
#    sugerencias: el motor NUNCA propone valores para ellos (nunca confunde
#    fianza con mínimo). (Parte 14: no romper cálculos de negocio.)
def _c(campo, old, new, pais=1, vacio=False):
    return {"campo": campo, "valor_anterior": old, "valor_nuevo": new,
            "pais": pais, "contexto": "", "codigo_prensa": "LE08JUL20261C",
            "era_vacio": vacio, "creado_en": "2026-07-08T10:00:00"}


# ---------------- Parte 1: generar_sugerencias ----------------

def test_fianza_y_minimo_no_estan_en_superficie_sugerencias():
    # correcciones repetidas de fianza/minimo NUNCA generan sugerencias
    corrs = (_c("fianza_porcentaje", "10", "25", pais=1) for _ in range(5)),
    corrs = [_c("fianza_porcentaje", "10", "25", pais=1)] * 5 + \
           [_c("minimo_porcentaje", "50", "66", pais=1)] * 5
    assert generar_sugerencias(corrs) == []


def test_sugerencia_correccion_repetida():
    # una corrección repetida 4× en PA -> sugerencia única de corrección
    corrs = [_c("provincia", "JDO", "JUZGADO", pais=1)] * 4 + \
            [_c("provincia", "JDO", "JUZGADO", pais=2)]  # 1× en CO -> no sugiere
    sugs = generar_sugerencias(corrs)
    rep = [s for s in sugs if s["tipo"] == "correccion_repetida"]
    assert len(rep) == 1
    assert rep[0]["pais"] == 1
    assert rep[0]["count"] == 4
    assert rep[0]["valor_sugerido"] == "JUZGADO"
    assert rep[0]["valor_referencia"] == "JDO"
    assert rep[0]["confianza"] > 0.9


def test_sugerencia_alias_forma_distinta_misma_normalizacion():
    # "Panamá" y "PANAMA" normalizan igual -> sugerencia alias (unificar)
    corrs = [_c("provincia", "a", "Panamá", pais=1),
             _c("provincia", "b", "PANAMA", pais=1)]
    sugs = generar_sugerencias(corrs)
    alias = [s for s in sugs if s["tipo"] == "alias"]
    assert len(alias) == 1
    assert set(alias[0]["alternativas"]) == {"Panamá", "PANAMA"}


def test_sugerencia_etiqueta_nueva_categoria():
    corrs = [_c("categoria", "", "CASOTA", pais=1)] * 2
    sugs = generar_sugerencias(corrs)
    nueva = [s for s in sugs if s["tipo"] == "etiqueta_nueva"
             and s["campo"] == "categoria" and s["valor_sugerido"] == "CASOTA"]
    assert len(nueva) == 1


def test_sugerencias_priorizan_pais_pa():
    corrs = [_c("provincia", "x", "JUZGADO", pais=1)] * 3 + \
            [_c("provincia", "x", "BOGOTA", pais=2)] * 3
    sugs = generar_sugerencias(corrs)
    idx_pa = [i for i, s in enumerate(sugs) if s.get("pais") == 1]
    idx_co = [i for i, s in enumerate(sugs) if s.get("pais") == 2]
    assert idx_pa and idx_co
    assert max(idx_pa) < min(idx_co)  # Panamá aparece antes que Colombia


def test_sugerencias_vacias_sin_correcciones():
    assert generar_sugerencias([]) == []


# ---------------- Parte 2: inteligencia_aviso ----------------

_AVISO = {
    "id": 7, "pais": 1, "expediente": "54802-25", "estado": "esperando_aprobacion",
    "confianza_promedio": 0.4, "discrepancia_valores": True,
    "base": "110000.0", "fianza_porcentaje": None, "minimo_porcentaje": None,
    "fianza": None, "minimo": None,
    "fecha": None, "hora": None, "proceso": None, "lugar": None, "categoria": None,
    "demandante": None, "demandado": None, "descripcion": None, "finca_matr": None,
    "provincia": None,
    "codigo_fuente": "det-0", "codigo_prensa": "LE08JUL20261C",
}


def test_inteligencia_motivo_discrepancia_y_confianza_baja():
    rep = inteligencia_aviso(dict(_AVISO))
    assert "discrepancia_valores" in rep["motivo_fallo"]
    assert "confianza_baja" in rep["motivo_fallo"]
    assert "fianza_indeterminada" in rep["motivo_fallo"]
    assert "minimo_indeterminado" in rep["motivo_fallo"]
    assert 0.0 <= rep["confianza_predicha"] <= 1.0


def test_inteligencia_recuperacion_deterministico():
    rep = inteligencia_aviso(dict(_AVISO))
    assert rep["recuperacion"]["motor_principal"] == "deterministico"


def test_inteligencia_campos_faltantes():
    rep = inteligencia_aviso(dict(_AVISO))
    for f in ("fecha", "hora", "categoria", "provincia"):
        assert f in rep["campos_faltantes"]


# ---------------- Parte 5: predecir ----------------

def test_predecir_ocr_conflictos():
    # dos valores normalizados DISTINTOS para el mismo campo -> ambigüedad OCR
    corrs = [_c("provincia", "a", "JUZGADO", pais=1),
             _c("provincia", "b", "BOGOTA", pais=1)]
    res = predecir(corrs, avisos=[])
    assert any(c["campo"] == "provincia" and c["variantes"] > 1
               for c in res["ocr_conflictos"])


def test_predecir_no_confunde_acentos_alias():
    # "Panamá" vs "PANAMA" son el MISMO token normalizado -> no es conflicto
    corrs = [_c("provincia", "a", "Panamá", pais=1),
             _c("provincia", "b", "PANAMA", pais=1)]
    res = predecir(corrs, avisos=[])
    assert res["ocr_conflictos"] == []


def test_predecir_duplicados_por_expediente_finca_base():
    corrs = [_c("lugar", "", "X", pais=1)]
    avisos = [
        {"id": 1, "expediente": "1-25", "finca_matr": "7452623", "base": "100", "pais": 1},
        {"id": 2, "expediente": "1-25", "finca_matr": "7452623", "base": "100", "pais": 1},
    ]
    res = predecir(corrs, avisos=avisos)
    assert any(len(d["ids"]) > 1 for d in res["posibles_duplicados"])


# ---------------- Parte 12: reportes ----------------

def test_reportes_disponibles_y_renderizan():
    esperados = {"hyper_learning", "hyper_intelligence", "production_diagnosis",
                 "ui_audit", "knowledge_evolution", "continuous_learning", "client_ready"}
    assert set(available_reports()) == esperados
    samples = {
        "hyper_learning": {"sugerencias": [{"tipo": "correccion_repetida", "campo": "provincia",
            "pais": 1, "valor_sugerido": "JUZGADO", "valor_referencia": "JDO", "count": 4,
            "confianza": 0.9, "ultima": "2026-01-01"}]},
        "hyper_intelligence": {"analisis_por_aviso": [{"aviso_id": 1, "expediente": "1-25",
            "motivo_fallo": ["confianza_baja"], "campos_faltantes": ["fecha"],
            "confianza_predicha": 0.4}]},
        "production_diagnosis": {"checks": {"db": {"status": "ok", "detalle": "x"},
            "ia": {"status": "fail", "detalle": "sin key"}}, "fallos_criticos": ["ia"]},
        "ui_audit": _auditar_ui(),
        "knowledge_evolution": {"evolucion": [{"campo": "provincia", "valor_anterior": "JDO",
            "valor_nuevo": "JUZGADO", "count": 4, "ultima": "2026-01-01"}]},
        "continuous_learning": {"registro": [{"timestamp": "2026-01-01T00:00:00", "agente": "cliente",
            "accion": "correccion", "aviso_id": 1, "detalle": "c"}]},
        "client_ready": {"timestamp": "2026-01-01T00:00:00",
            "resumen": {"db": "ok"}, "issues": []},
    }
    for name in esperados:
        j, m = BUILDERS[name](samples[name])
        assert isinstance(j, str) and isinstance(m, str) and len(m) > 10
        _json.loads(j)  # serializable


def test_ui_audit_detecta_botones_implementados():
    rep = _auditar_ui()
    estados = {h["estado"] for h in rep["hallazgos"]}
    # el archivo existe y al menos un botón está implementado
    assert "ok" in estados
