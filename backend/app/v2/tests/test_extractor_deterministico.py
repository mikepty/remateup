"""Extractor DETERMINÍSTICO (sin IA) — respaldo final del pipeline.

Cubre el módulo de regex que se usa cuando ninguna IA está disponible:
  1. Segmentación por encabezados de aviso.
  2. El expediente debe leerse del CUERPO (después del encabezado), NO del
     pie del aviso anterior que cuelga al inicio del segmento.
  3. Partes limpias: sin "MEDIO DEL PRESENTE EDICTO" ni captura con minúsculas.
  4. Base recuperada desde el texto OCR (patrón "la cifra de"/"la suma de").
  5. La base del aviso vecino NO se le asigna a otro aviso.

Sin red ni BD: todas las funciones son puras.
"""

import pytest

from backend.app.pipeline.extractor_deterministico import (
    _extraer_partes,
    _extraer_aviso,
    extraer,
)
from backend.app.pipeline.orchestrator import _buscar_base_en_ocr


AVISO_54802 = """AVISO DE REMATE Expediente No. 54802-25 La suscrita, ALGUACIL EJECUTORA
DEL JUZGADO SEGUNDO DE CIRCUITO DE INSOLVENCIA DEL PRIMER CIRCUITO JUDICIAL
DE PANAMA, promovido por BAC INTERNATIONAL BANK, INC., en contra de ANA LINETH
SOTO BEDOYA. FINCA 7452623, LOTE 212. ... el día 11 de agosto de 2026 a las
09:00 A.M. Se servirá de base para el remate la cifra de B/.74,000.00 (valor de
mercado) y serán posturas admisibles las sumas que cubran las dos terceras
partes (2/3) de la base del remate. FIANZA 10%."""

# "en contra de ANA LINETH SOTO BEDOYA." debe quedar en UNA sola línea (el
# regex corta el demandado en el salto de línea).
AVISO_54802 = AVISO_54802.replace(
    "en contra de ANA LINETH\nSOTO BEDOYA.", "en contra de ANA LINETH SOTO BEDOYA.")


def test_extraer_aviso_campos_principales():
    item = _extraer_aviso(AVISO_54802, "PA", 0)
    d = item["datos"]
    assert d["expediente"] == "54802-25"
    assert d["demandante"] == "BAC INTERNATIONAL BANK"
    assert d["demandado"] == "ANA LINETH SOTO BEDOYA"
    assert d["base"] == "74000.0"
    assert d["hora"] in ("09:00 AM", "09:00 A.M", "09:00 A.M.")
    assert d["minimo_porcentaje"] == 66.67
    assert item["confianza"]["expediente"] > 0


def test_extraer_expediente_no_toma_el_del_pie_del_aviso_anterior():
    """El pie del aviso previo (Exp. 41612-26 KS/nr...) cuelga del inicio del
    segmento; el extractor debe leer el expediente del CUERPO del aviso."""
    texto = "publicación. La Chorrera, 24 de abril de 2026. Exp.41612-26 KS/nr. " + AVISO_54802
    item = _extraer_aviso(texto, "PA", 0)
    assert item["datos"]["expediente"] == "54802-25"


def test_extraer_partes_descarta_basura():
    demte, demdo = _extraer_partes(
        "por medio del presente edicto, promovido por BANCO GENERAL S.A. en "
        "contra de PABLO EDGARDO VARGAS NAVARRO.")
    assert demte == "BANCO GENERAL S.A"
    assert demdo == "PABLO EDGARDO VARGAS NAVARRO"


def test_extraer_partes_no_captura_sobre_minusculas():
    demte, _ = _extraer_partes(
        "promovido por BANCO GENERAL, el día 11 DE AGOSTO DE 2026, para que "
        "en sus horas hábiles se lleve a cabo la diligencia de remate.")
    assert demte == "BANCO GENERAL"


def test_extraer_segmenta_por_encabezados():
    texto = ("AVISO DE REMATE E-60255-25/mb La suscrita, ALGUACIL EJECUTORA. "
             "servirá de base para el remate la cifra de B/.60,850.00\n" +
             AVISO_54802)
    avisos = extraer(texto, "PA")
    exps = [a["datos"]["expediente"] for a in avisos]
    assert exps == ["60255-25", "54802-25"]


def test_base_se_encuentra_aun_lejos_del_encabezado():
    """La base suele quedar a miles de caracteres del encabezado (el folio va
    en medio); la ventana debe llegar hasta el siguiente aviso."""
    texto = ("AVISO DE REMATE Exp.Electr.161722025 La suscrita... " + "X" * 6000 +
             "Servirá de base para el remate la cifra de B/.110,000.00 y será "
             "postura admisible la que cubra las dos terceras partes.")
    base = _buscar_base_en_ocr({"expediente": "161722025", "base": None}, texto)
    assert base == 110000.0


def test_base_con_monto_en_palabras():
    texto = ("AVISO DE REMATE Expediente No. 214012026 ... "
             "servirá de base para el remate, la suma de CUARENTAY NUEVE MIL "
             "QUINIENTOS TREINTA Y UNO BALBOAS CON 65/100 (B/.49,531.65), y "
             "será postura admisible la que cubra...")
    base = _buscar_base_en_ocr({"expediente": "214012026", "base": None}, texto)
    assert base == 49531.65


def test_no_toma_valor_del_folio_como_base():
    """'CON UN VALOR DE B/.68,073.10' (folio) NO es la base: sin palabra clave
    de base/cuantía cerca, el monto genérico se rechaza."""
    texto = ("AVISO DE REMATE (Exp. 126990-25) ... NOMERO DE PLANO: 80717-135068 "
             "CON UN VALOR DE B/.68,073.10 (SESENTA Y OCHO MIL SETENTA Y TRES "
             "BALBOAS CON DIEZ) ...")
    base = _buscar_base_en_ocr({"expediente": "126990-25", "base": None}, texto)
    assert base is None
