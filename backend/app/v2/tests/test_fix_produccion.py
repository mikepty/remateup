"""FASE BUG-PRODUCCION — Tests: columnas OCR, montos, prevista y codigo_prensa.

Cubre los arreglos del bug reportado por el cliente (página PA con 3 de 5
avisos sin monto, sin ubicación de Maps ni código de prensa):

  1. _detectar_columnas: NO debe crear columnas fantasma en páginas de ancho
     completo (canalones débiles por sangrías alineadas) — el reordenado por
     palabras destruía el texto y la IA no asociaba montos ni cabecera.
     Y SÍ debe detectar columnas reales cuando el canalón es ancho y vacío.
  2. _cabecera_periodico_desde_ocr: detecta "La Prensa, Panamá, jueves 9 de
     julio de 2026" -> ("La Prensa", "2026-07-09") para el código de prensa.
  3. _pagina_prensa_desde_ocr: detecta el código de página impreso ("6B").
  4. _buscar_base_en_ocr: recupera el monto (base) desde el texto OCR cuando
     la IA no lo asoció, sin coger el monto del aviso vecino.
  5. _generar_prevista: construye ubicación para Google Maps (approximada)
     desde descripcion/provincia cuando el modelo no la dio.
  6. _generar_codigo_prensa: genera LP09JUL20266B a partir de los datos
     completados por los respaldos.

No usa red ni BD: todos los casos son funciones puras o sintéticas.
"""

import pytest

from backend.app.pipeline.ocr_vision import _detectar_columnas, _reconstruir_por_palabras
from backend.app.pipeline.orchestrator import (
    _cabecera_periodico_desde_ocr,
    _pagina_prensa_desde_ocr,
    _buscar_base_en_ocr,
)
from backend.app.pipeline.business_rules import _generar_prevista, _generar_codigo_prensa, aplicar_reglas


def _palabras_sinteticas(ancho, palabras):
    """Convierte lista de (x0, y0, texto, alto) a palabras estilo Vision."""
    out = []
    for x0, y0, t, h in palabras:
        x1 = x0 + int(max(30, len(t) * 9))
        out.append({"x0": x0, "x1": x1, "y0": y0, "y1": y0 + h, "t": t, "brk": ""})
    return out, ancho


# ── 1. Detección de columnas ────────────────────────────────────────────────

def test_no_detecta_columnas_en_pagina_ancho_completo():
    """Caso real del bug: página de avisos justificados de ancho completo.
    Los únicos huecos son el canalón débil (24px) y las sangrías alineadas:
    el detector ESTRICTO debe devolver 0-1 columnas (no 2 fantasma)."""
    ancho = 3000
    pal = []
    # Texto continuo de la columna central (56..2900), con un "canalón" débil
    # de 24px en x=1472 (como la página real de La Prensa) y muchas líneas.
    y = 0
    for fila in range(80):
        x = 60
        while x < 1440:
            pal.append((x, y, f"PALABRA{fila}x{x}", 20))
            x += 120
        x = 1500
        while x < 2900:
            pal.append((x, y, f"TEXTO{fila}x{x}", 20))
            x += 120
        y += 30
    palabras, _ = _palabras_sinteticas(ancho, pal)
    cols = _detectar_columnas(palabras, ancho)
    assert len(cols) < 2, f"columnas fantasma: {cols}"


def test_detecta_columnas_reales_con_canalon_ancho():
    """Página con 2 columnas reales separadas por un canalón vacío de 200px:
    el detector ESTRICTO SÍ debe encontrarlas."""
    ancho = 3000
    pal = []
    y = 0
    for fila in range(60):
        x = 60
        while x < 1300:
            pal.append((x, y, f"A{fila}x{x}", 20))
            x += 110
        x = 1500
        while x < 2900:
            pal.append((x, y, f"B{fila}x{x}", 20))
            x += 110
        y += 30
    palabras, _ = _palabras_sinteticas(ancho, pal)
    cols = _detectar_columnas(palabras, ancho)
    assert len(cols) == 2, f"columnas: {cols}"
    assert cols[0][1] <= 1500 and cols[1][0] >= 1495


def test_reconstruccion_por_palabras_con_columnas_reales():
    """Con columnas reales detectadas (líneas continuas de palabras y canalón
    vacío), el reordenado lee la columna izquierda completa y luego la derecha,
    sin entremezclar las líneas."""
    ancho = 3000
    palabras = []
    # Cada línea: 10 palabras contiguas (x1 = x0+140, paso 130) -> cobertura
    # continua en la columna; canalón vacío de 1370..1600 entre columnas.
    for fila, y in enumerate([10, 50, 90]):
        for c in range(10):
            x = 100 + c * 130
            palabras.append({"x0": x, "x1": x + 140, "y0": y, "y1": y + 20,
                             "t": f"IZQ{fila + 1}-{c + 1}", "brk": ""})
        for c in range(10):
            x = 1600 + c * 130
            palabras.append({"x0": x, "x1": x + 140, "y0": y, "y1": y + 20,
                             "t": f"DER{fila + 1}-{c + 1}", "brk": ""})

    def anotacion():
        bloques = []
        for w in palabras:
            verts = [{"x": w["x0"], "y": w["y0"]}, {"x": w["x1"], "y": w["y0"]},
                     {"x": w["x1"], "y": w["y1"]}, {"x": w["x0"], "y": w["y1"]}]
            bloques.append({
                "boundingBox": {"vertices": verts},
                "paragraphs": [{"words": [{
                    "boundingBox": {"vertices": verts},
                    "symbols": [{"text": ch, "property": {"detectedBreak": {"type": ""}}}
                                for ch in w["t"]],
                }]}],
            })
        return {"pages": [{"width": ancho, "blocks": bloques}]}

    txt = _reconstruir_por_palabras(anotacion())
    izq = [f"IZQ{f}-{c}" for f in range(1, 4) for c in range(1, 11)]
    der = [f"DER{f}-{c}" for f in range(1, 4) for c in range(1, 11)]
    esperado = (
        " ".join(izq[0:10]) + "\n" + " ".join(izq[10:20]) + "\n" + " ".join(izq[20:30])
        + "\n\n" + " ".join(der[0:10]) + "\n" + " ".join(der[10:20]) + "\n"
        + " ".join(der[20:30])
    )
    assert txt == esperado


# ── 2/3. Cabecera del periódico y página ────────────────────────────────────

def test_cabecera_periodico_desde_ocr():
    t = "texto previo...\nLa Prensa Panamá, jueves 9 de julio de 2026\nmás texto"
    assert _cabecera_periodico_desde_ocr(t) == ("La Prensa", "2026-07-09")


def test_cabecera_periodico_sin_texto_retorna_none():
    assert _cabecera_periodico_desde_ocr(None) is None
    assert _cabecera_periodico_desde_ocr("sin cabecera aquí") is None


def test_cabecera_la_estrella():
    t = "La Estrella, Panamá, viernes 3 de julio de 2026 ..."
    assert _cabecera_periodico_desde_ocr(t) == ("La Estrella", "2026-07-03")


def test_pagina_prensa_desde_ocr():
    assert _pagina_prensa_desde_ocr("6B\nAVISO DE REMATE...") == "6B"
    assert _pagina_prensa_desde_ocr("A\nI\n6B\nEN DIRECCION...") == "6B"
    assert _pagina_prensa_desde_ocr("sin pagina aqui") is None
    assert _pagina_prensa_desde_ocr("") is None


# ── 4. Base (monto) desde OCR ───────────────────────────────────────────────

def test_buscar_base_por_patron_base_del_remate():
    texto = ("AVISO DE REMATE E-132472-24/mb ... la base del remate, es decir "
             "la suma de B/.5,800.00. Fianza 10%...")
    d = {"expediente": "132472-24", "base": None}
    assert _buscar_base_en_ocr(d, texto) == 5800.0


def test_buscar_base_por_cuantia_del_embargo():
    texto = ("AVISO DE REMATE (Exp. 214012026) ... CUANTIA DEL EMBARGO: "
             "CINCUENTA Y UN MIL SETECIENTOS CINCUENTA (B/.51,750.00) ...")
    d = {"expediente": "214012026", "base": None}
    assert _buscar_base_en_ocr(d, texto) == 51750.0


def test_buscar_base_no_toma_monto_de_aviso_vecino():
    """Con otro aviso entre el expediente y el monto genérico, NO debe tomar
    el monto genérico (pertenece al vecino)."""
    texto = ("AVISO DE REMATE E-154007-24 ... texto del aviso ... "
             "AVISO DE REMATE E-63539-23 ... CUANTIA DEL EMBARGO: "
             "OCHENTA MIL (B/.80,062.57) ...")
    d = {"expediente": "154007-24", "base": None}
    assert _buscar_base_en_ocr(d, texto) is None


def test_buscar_base_no_toma_cuantia_del_aviso_anterior():
    """La CUANTIA del aviso ANTERIOR (dentro de los 2000 chars previos al
    expediente, como en la página real de La Prensa) NO debe usarse como base:
    el monto propio del aviso viene DESPUÉS de su expediente."""
    texto = ("AVISO DE REMATE E-99999-25 ... CUANTIA DEL EMBARGO: "
             "CINCUENTA Y UN MIL SETECIENTOS CINCUENTA (B/.51,750.00) ... "
             "AVISO DE REMATE E-54802-25 ... CUANTIA DEL EMBARGO: "
             "SETENTA Y CUATRO MIL (B/.74,000.00) ...")
    d = {"expediente": "54802-25", "base": None}
    assert _buscar_base_en_ocr(d, texto) == 74000.0


def test_buscar_base_no_toma_valor_del_traspaso_del_folio():
    """El folio real dentro del aviso trae OTROS montos (valor del traspaso,
    hipoteca) que NO son la base. La base real se expresa como
    'servirá de base para el remate la cifra de B/.X'."""
    texto = ("AVISO DE REMATE E-54802-25/mb ... FOLIO: 80102-123735 "
             "EL VALOR DEL TRASPASO ES CINCUENTA Y UN MIL SETECIENTOS "
             "CINCUENTA BALBOAS(B/.51,750.00) TITULAR(ES) ... hipoteca POR "
             "LA SUMA DE B/.46.575.00 CON UN PLAZO ... no hay entradas "
             "pendientes. Servirá de base para el remate la cifra de "
             "B/.74,000.00 (valor de mercado)")
    d = {"expediente": "54802-25", "base": None}
    assert _buscar_base_en_ocr(d, texto) == 74000.0


def test_buscar_base_por_cuantia_con_acento():
    """El OCR real escribe 'CUANTÍA DEL EMBARGO' con tilde; el patrón debe
    tolerarla."""
    texto = ("AVISO DE REMATE (Exp. 214012026) ... CUANTÍA DEL EMBARGO: "
             "CUARENTA Y DOS MIL SETECIENTOS (B/.42,733.11) CLAUSULAS ...")
    d = {"expediente": "214012026", "base": None}
    assert _buscar_base_en_ocr(d, texto) == 42733.11


def test_buscar_base_si_ya_hay_base_no_toca():
    texto = "AVISO DE REMATE ... la base del remate B/.5,800.00"
    d = {"expediente": "132472-24", "base": "74000.0"}
    assert _buscar_base_en_ocr(d, texto) is None


# ── 5. prevista (ubicación Maps) ────────────────────────────────────────────

def test_generar_prevista_desde_descripcion_y_provincia():
    d = {"descripcion": "Casa lote 212, Arraiján, Panamá", "provincia": "PANAMA"}
    assert _generar_prevista(d) == "Casa lote 212, Arraiján, Panamá, PANAMA"


def test_generar_prevista_respeta_la_existente():
    d = {"prevista": "LOTE 156, Dist: Arraiján, Prov: Panamá", "descripcion": "x", "provincia": "y"}
    assert _generar_prevista(d) == "LOTE 156, Dist: Arraiján, Prov: Panamá"


def test_generar_prevista_con_solo_provincia():
    d = {"provincia": "LOS SANTOS", "descripcion": ""}
    assert _generar_prevista(d) == "LOS SANTOS"


def test_generar_prevista_sin_datos():
    assert _generar_prevista({"descripcion": "", "provincia": None}) is None


# ── 6. codigo_prensa ────────────────────────────────────────────────────────

def test_codigo_prensa_compuesto_con_respaldos():
    """Datos completados por los respaldos (cabecera OCR + página): el código
    debe salir con el formato del cliente INICIAL+DDMESAAAA+PÁGINA."""
    d = {"pais": 1, "periodico": "La Prensa", "fecha_prensa": "2026-07-09",
         "pagina_prensa": "6B", "codigo_fuente": "LP-2026-12345"}
    assert _generar_codigo_prensa(d) == "LP09JUL20266B"


def test_codigo_prensa_null_sin_datos_suficientes():
    d = {"pais": 1, "periodico": None, "fecha_prensa": None, "pagina_prensa": None}
    assert _generar_codigo_prensa(d) is None


# ── 7. Cuotas partes -> misceláneo ──────────────────────────────────────────

@pytest.fixture
def sin_bd(monkeypatch):
    """aplicar_reglas genera el código interno consultando la BD; en tests
    unitarios se reemplaza para no depender de Postgres."""
    monkeypatch.setattr("backend.app.pipeline.business_rules._generar_codigo_interno",
                        lambda datos: "PA00000000")
    return None


def test_cuotas_partes_es_miscelaneo_por_proceso(sin_bd):
    """AVISO DE VENTA DE CUOTAS PARTES (proceso) debe clasificar como
    MISCELANEO (5), aunque la categoria/detalle no lo mencione."""
    d = {"pais": 1, "provincia": "PANAMA", "categoria": "TERRENO",
         "proceso": "VENTA DE CUOTAS PARTES", "descripcion": "Lote 210-G en Vista Alegre"}
    salida = aplicar_reglas(d)
    assert salida["categoria_codigo"] == 5
    assert salida["categoria"] == "MISCELANEO"


def test_cuotas_partes_es_miscelaneo_por_descripcion_completa(sin_bd):
    d = {"pais": 1, "provincia": "PANAMA", "categoria": "CASA",
         "proceso": "AVISO DE REMATE", "descripcion": "Casa",
         "descripcion_completa": "venta de las cuotas partes del 50% de la finca..."}
    salida = aplicar_reglas(d)
    assert salida["categoria_codigo"] == 5
    assert salida["categoria"] == "MISCELANEO"


def test_remate_normal_no_es_miscelaneo(sin_bd):
    d = {"pais": 1, "provincia": "PANAMA", "categoria": "APARTAMENTO",
         "proceso": "AVISO DE REMATE", "descripcion": "Apto 2B, Bella Vista"}
    salida = aplicar_reglas(d)
    assert salida["categoria_codigo"] == 2
    assert salida["categoria"] == "APARTAMENTO"
