"""
Extractor DETERMINÍSTICO (sin IA) — respaldo final de la extracción.

Cuando ni Claude ni Gemini están disponibles (sin saldo, sin llave), el
pipeline no puede quedarse muerto: este módulo estructura el texto OCR con
regex sobre la estructura REGULAR de los avisos de remate panameños:

  AVISO DE REMATE E-54802-25/mb La suscrita, ALGUACIL EJECUTORA DEL
  JUZGADO PRIMERO DE CIRCUITO DE INSOLVENCIA ... promovido por BAC
  INTERNATIONAL BANK, INC., en contra de ANA LINETH ... FIANZA 10% ...
  Servirá de base para el remate la cifra de B/.74,000.00 ...

Devuelve el MISMO formato que el extractor de IA: lista de
{"datos": {...CAMPOS...}, "confianza": {...0-1...}}. La confianza es baja
(solo campos confirmados por regex con 0.9 y el resto 0.0), de modo que los
avisos salen en esperando_aprobacion para revisión del cliente, igual que
los extraídos con IA dudosa.
"""
import re
from datetime import datetime

from ..config import CODIGOS_PROVINCIA_PA, CODIGOS_DEPARTAMENTO_CO

CAMPOS = [
    "pais", "codigo", "fecha", "hora", "proceso", "expediente", "lugar", "categoria",
    "demandante", "demandado", "lote_casa", "descripcion", "descripcion_completa",
    "prevista", "superficie", "finca_matr", "codigo_ubicacion_prensa", "provincia", "plano", "base",
    "fianza_porcentaje", "minimo_porcentaje", "fianza", "minimo", "codigo_fuente",
    "codigo_prensa", "email_observaciones", "periodico", "fecha_prensa", "pagina_prensa",
]

_RE_ENCABEZADO = re.compile(r"AVISO\s+DE\s+[A-Z]{0,2}E[MN]ATE")
_MESES = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
    "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11,
    "DICIEMBRE": 12,
}

_CONFIANZA_ALTA = 0.9

# Porcentajes legales de FIANZA (PA: 10/20/25 ; CO: 40 fijo).
# Se usa para VALIDAR cualquier porcentaje leído: el mínimo usa 50/66.67/100,
# conjunto disjunto, de modo que nunca se confunden.
_PORCENTAJES_FIANZA_VALIDOS = {10, 20, 25, 40}
_PALABRAS_FIANZA = {"diez": 10, "veinte": 20, "veinticinco": 25, "cuarenta": 40}


def _extraer_fianza_pct(texto: str) -> float | None:
    """Extrae el porcentaje de FIANZA (10/20/25 PA, 40 CO).

    El aviso lo escribe casi siempre como 'diez por ciento ( 10 % )' o
    'VEINTICINCO POR CIENTO ( 25 % )', a veces solo '10 %', y rara vez junto
    a la palabra 'FIANZA'. Por eso no se puede exigir la keyword 'FIANZA':
    el regex viejo (`FIANZA...X%`) dejaba fiana_pct = None en los judiciales
    reales, con lo que ni la fianza ni el 'Mínimo para participar' se calculaban.
    """
    # 1) 'FIANZA' seguido del % (caso clásico / del test de unidades)
    m = re.search(r"FIANZA[^\d]{0,50}?(\d{1,2})\s*%", texto, re.IGNORECASE)
    if m:
        v = int(m.group(1))
        if v in _PORCENTAJES_FIANZA_VALIDOS:
            return float(v)
    # 2) 'diez por ciento ( 10 % )' con número entre paréntesis (formato real)
    for m in re.finditer(r"\b(diez|veinte|veinticinco|cuarenta)\s+por\s+ciento\s*\(\s*(\d{1,2})\s*%",
                         texto, re.IGNORECASE):
        v = int(m.group(2))
        if v in _PORCENTAJES_FIANZA_VALIDOS:
            return float(v)
    # 3) 'diez por ciento' en palabras, sin número entre paréntesis
    #    (ej. 'participar con diez por ciento'). El mínimo usa cincuenta/cien,
    #    nunca 10/20/25/40, así que no hay colisión.
    for m in re.finditer(r"\b(diez|veinte|veinticinco|cuarenta)\s+por\s+ciento", texto, re.IGNORECASE):
        return float(_PALABRAS_FIANZA[m.group(1).lower()])
    # 4) Forma judicial real: 'el 10 % de la base', 'VEINTICINCO POR CIENTO ( 25 % )',
    #    'el diez ( 10 % ) de la suma', 'el 25 % de la base del remate'.
    #    Como el conjunto de porcentajes de fianza {10,20,25,40} es DISYUNTO del
    #    de mínimo {50,66.67,100}, cualquier token '% ' con valor en el conjunto
    #    legal es fianza; recoger el primero en aparecer.
    for m in re.finditer(r"(\d{1,2})\s*%", texto):
        v = int(m.group(1))
        if v in _PORCENTAJES_FIANZA_VALIDOS:
            return float(v)
    return None


def _posiciones_avisos(texto: str) -> list[int]:
    """Posiciones donde EMPIEZA un aviso de remate (encabezado en mayúsculas).
    Descarta menciones internas precedidas por 'presente'/'fija' o que citan
    folios ("DE UN AVISO DE REMATE EXP. No. X")."""
    posiciones = []
    for m in _RE_ENCABEZADO.finditer(texto):
        previo = texto[max(0, m.start() - 40):m.start()].upper()
        if "PRESENTE" in previo or "FIJA" in previo or "DE UN AVISO" in previo:
            continue
        posiciones.append(m.start())
    return posiciones


def _normalizar(texto: str) -> str:
    """Junta palabras partidas por guion de fin de línea ("IN-\nSOLVENCIA")
    sin romper números ni fechas. El OCR de periódicos parte mucho."""
    return re.sub(r"-\s*\n\s*", "", texto)


def _buscar(patron: str, texto: str, grupo: int = 1, flags=re.IGNORECASE):
    m = re.search(patron, texto, flags)
    return m.group(grupo) if m else None


def _fecha_remate(texto: str) -> str | None:
    """Fecha de la subasta. Solo se aceptan fechas CERCANAS a REMATE/SUBASTA/
    CELEBRAR; las fechas de hipotecas/traspasos del folio ("inscrito el día
    30 de octubre de 2019") NO son la fecha del remate."""
    for m in re.finditer(
            r"(?:EL\s+)?D[IÍ]A\s+(\d{1,2})\s+DE\s+([A-ZÁÉÍÓÚÑ]+)(?:\s+DE\s+|\s+)(\d{4})",
            texto, re.IGNORECASE):
        alrededor = texto[max(0, m.start() - 150):m.end() + 100].upper()
        if not any(k in alrededor for k in ("REMATE", "SUBASTA", "CELEBRAR",
                                            "VERIFICA", "EFECTUAR")):
            continue
        numero_mes = _MESES.get(m.group(2).upper())
        if not numero_mes:
            continue
        try:
            return datetime(int(m.group(3)), numero_mes, int(m.group(1))).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _hora_remate(texto: str) -> str | None:
    m = re.search(r"(\d{1,2}):(\d{2})\s*(A\.?\s*M\.?|P\.?\s*M\.?)", texto, re.IGNORECASE)
    if m and 1 <= int(m.group(1)) <= 12 and 0 <= int(m.group(2)) <= 59:
        return f"{int(m.group(1)):02d}:{m.group(2)} {m.group(3).replace(' ', '').upper()}"
    m = re.search(r"LAS?\s+(\d{1,2})\s*(?:HORAS?)?\s*(A\.?\s*M\.?|P\.?\s*M\.?)",
                  texto, re.IGNORECASE)
    if m and 1 <= int(m.group(1)) <= 12:
        return f"{int(m.group(1)):02d}:00 {m.group(2).replace(' ', '').upper()}"
    return None


def _extraer_expediente(texto: str, previo: str) -> str | None:
    """Busca el expediente en el CUERPO (después del encabezado); el pie del
    aviso anterior ('Exp. 41612-26 KS/nr...') que cuelga del inicio del
    segmento NO debe ganarle al expediente propio."""
    exp = _buscar(r"(?:EXP|EXPEDIENTE)\s*\.?\s*ELECTR\.?\s*(\d{4,9})", texto)
    if not exp:
        exp = _buscar(r"(?:E|EXP|EXPEDIENTE)\s*[-.]?\s*[Nn]?[Oo]?\.?\s*(\d{3,7}[-/]\d{2})", texto)
    if not exp:
        exp = _buscar(r"(?:EXP|EXPEDIENTE)\s*[-.]?\s*[Nn]?[Oo]?\.?\s*(\d{4,9})", texto)
    if not exp:
        exp = _buscar(r"NEGOCIO\s+N[°º]?\.?\s*(\d{3,7}[-/]\d{2})", previo)
    if not exp:
        exp = _buscar(r"(?:E|EXP)\s*[-.]?\s*(\d{3,7}[-/]\d{2})", previo)
    if exp and "/" in exp:
        exp = exp.replace("/", "-")
    return exp


_PARTES_BASURA = ("MEDIO DEL PRESENTE", "PRESENTE AVISO", "PRESENTE EDICTO",
                  "PRESENTE PUBLICACION", "HA PROMOVIDO", "SEGUN", "PARA QUE")


def _limpiar_parte(s: str | None) -> str | None:
    """Normaliza una parte capturada y descarta basura. La clase de captura
    permite minúsculas por IGNORECASE, así que un resultado con minúsculas
    casi siempre significa que el regex se pasó del límite (tomó otra frase)."""
    if not s:
        return None
    s = re.sub(r"\s+", " ", s).strip().rstrip(",.").strip()
    if len(s) < 3 or s != s.upper():
        return None
    if any(b in s for b in _PARTES_BASURA):
        return None
    return s


def _extraer_partes(texto: str) -> tuple[str | None, str | None]:
    demandante = None
    for patron in (
        r"(?:PROMOVIDO|INSTAURADO|PROPUESTO)\s+POR\s+"
        r"([A-ZÑÁÉÍÓÚ0-9.,& ]{3,80}?)(?:,|EN\s+CONTRA|\n|\.\s)",
        r"POR\s+([A-ZÑÁÉÍÓÚ0-9.,& ]{3,80}?)(?:,|EN\s+CONTRA|\n)",
    ):
        demandante = _limpiar_parte(_buscar(patron, texto))
        if demandante:
            break
    demandado = None
    for patron in (
        r"EN\s+CONTRA\s+DE\s+([A-ZÑÁÉÍÓÚ0-9.,& ]{3,80}?)(?:,|\n|\.\s|POR\s+EL|$)",
        r"(?:CONTRA|EN\s+CONTRA\s+DE)\s+([A-ZÑÁÉÍÓÚ0-9.,& ]{3,80}?)(?:,|\n|\.\s|$)",
    ):
        demandado = _limpiar_parte(_buscar(patron, texto))
        if demandado:
            break
    return demandante, demandado


def _extraer_categoria(texto: str, proceso: str) -> str:
    if "CUOTA PARTE" in texto.upper():
        return "MISCELANEO"
    for kw, cat in (("APARTAMENTO", "APARTAMENTO"), ("APTO", "APARTAMENTO"),
                    ("VEHICULO", "VEHICULO"), ("CARRO", "VEHICULO"),
                    ("MOTO", "VEHICULO"), ("CAMION", "VEHICULO"),
                    ("CASA", "CASA"), ("VIVIENDA", "CASA"),
                    ("RESIDENCIA", "CASA"), ("QUINTA", "CASA")):
        if kw in texto.upper():
            return cat
    return "TERRENO"


def _extraer_provincia(texto: str, pais: str) -> str | None:
    tabla = CODIGOS_PROVINCIA_PA if pais == "PA" else CODIGOS_DEPARTAMENTO_CO
    upper = texto.upper()
    for nombre in sorted(tabla, key=len, reverse=True):
        if nombre in upper:
            return nombre
    return None


def _extraer_aviso(texto: str, pais: str, idx: int, header_offset: int | None = None) -> dict:
    datos = {c: None for c in CAMPOS}
    confianza = {c: 0.0 for c in CAMPOS}
    texto_limpio = _normalizar(texto)

    datos["pais"] = 1 if pais == "PA" else 2

    proceso = "VENTA DE CUOTAS PARTES" if "CUOTAS PARTES" in texto_limpio.upper() else "AVISO DE REMATE"
    datos["proceso"] = proceso

    if header_offset is None:
        pos_header = _RE_ENCABEZADO.search(texto_limpio)
        header_offset = pos_header.start() if pos_header else 0
    previo = texto_limpio[max(0, header_offset - 150):header_offset]
    cuerpo = texto_limpio[header_offset:]

    exp = _extraer_expediente(cuerpo, previo)
    if exp:
        datos["expediente"] = exp
        confianza["expediente"] = _CONFIANZA_ALTA

    lugar = _buscar(
        r"(JUZGADO\s+[A-ZÑÁÉÍÓÚ]+\s+DE\s+CIRCUITO\s+DE\s+INSOLVENCIA"
        r"(?:\s+DEL\s+[A-ZÑÁÉÍÓÚ]+(?:\s+[A-ZÑÁÉÍÓÚ]+){0,3})?)", texto_limpio)
    if lugar:
        datos["lugar"] = re.sub(r"\s+", " ", lugar).strip()
        confianza["lugar"] = _CONFIANZA_ALTA

    demandante, demandado = _extraer_partes(texto_limpio)
    if demandante:
        datos["demandante"] = demandante
        confianza["demandante"] = _CONFIANZA_ALTA
    if demandado:
        datos["demandado"] = demandado
        confianza["demandado"] = _CONFIANZA_ALTA

    finca = _buscar(r"FINCA\s*:?\s*(\d{5,9})", texto_limpio)
    if not finca:
        finca = _buscar(r"FOLIO\s+REAL\s*:?\s*(\d{5,9})", texto_limpio)
    if not finca:
        finca = _buscar(r"FOLIO\s+REAL\s*:?\s*([\d-]{5,15})", texto_limpio)
    if finca:
        datos["finca_matr"] = finca
        confianza["finca_matr"] = _CONFIANZA_ALTA

    lote = _buscar(r"LOTE\s+([A-ZÑÁÉÍÓÚ0-9-]{1,12})", texto_limpio)
    if not lote:
        lote = _buscar(r"CASA\s+(?:LOTE\s+)?([A-ZÑÁÉÍÓÚ0-9-]{1,12})", texto_limpio)
    if lote and lote.upper() in ("NUMERO", "NRO", "NO", "COLOR", "CASA", "N"):
        lote = None
    if lote:
        datos["lote_casa"] = lote
        confianza["lote_casa"] = _CONFIANZA_ALTA

    plano = _buscar(r"PLANO\s*:?\s*([0-9-]{5,15})", texto_limpio)
    if plano:
        datos["plano"] = plano
        confianza["plano"] = _CONFIANZA_ALTA

    superficie = _buscar(r"([\d.,]{3,10})\s*(?:M2|MTS2|METROS\s+CUADRADOS|MTRS2|MTS\.?\s*2)",
                         texto_limpio, flags=re.IGNORECASE)
    if superficie:
        datos["superficie"] = superficie
        confianza["superficie"] = _CONFIANZA_ALTA

    m_cod = re.search(
        r"C[OÓ]DIGO\s+DE\s+UBICACI[OÓ]N\s*:?\s*([A-ZÑÁÉÍÓÚ0-9]{1,6})(?:[,;)\s]|$)",
        texto_limpio, re.IGNORECASE)
    codigo_ubic = m_cod.group(1) if m_cod and re.search(r"\d", m_cod.group(1)) else None
    if codigo_ubic:
        datos["codigo_ubicacion_prensa"] = codigo_ubic
        confianza["codigo_ubicacion_prensa"] = _CONFIANZA_ALTA

    datos["categoria"] = _extraer_categoria(texto_limpio, proceso)
    confianza["categoria"] = _CONFIANZA_ALTA

    provincia = _extraer_provincia(texto_limpio, pais)
    if provincia:
        datos["provincia"] = provincia
        confianza["provincia"] = _CONFIANZA_ALTA

    fecha = _fecha_remate(texto_limpio)
    if fecha:
        datos["fecha"] = fecha
        confianza["fecha"] = _CONFIANZA_ALTA
    hora = _hora_remate(texto_limpio)
    if hora:
        datos["hora"] = hora
        confianza["hora"] = _CONFIANZA_ALTA

    fianza_pct = _extraer_fianza_pct(texto_limpio)
    if fianza_pct:
        datos["fianza_porcentaje"] = fianza_pct
        confianza["fianza_porcentaje"] = _CONFIANZA_ALTA

    minimo_pct = None
    if "2/3" in texto_limpio or "DOS TERCERAS" in texto_limpio.upper():
        minimo_pct = 66.67
    elif "LA MITAD" in texto_limpio.upper() or "50%" in texto_limpio.upper():
        minimo_pct = 50.0
    elif "TOTALIDAD" in texto_limpio.upper() or "100%" in texto_limpio.upper():
        minimo_pct = 100.0
    else:
        m = _buscar(r"(?:POSTURA\s+MINIMA|MINIMO)[^\d]{0,60}?(\d{1,3}(?:\.\d{1,2})?)\s*%",
                    texto_limpio)
        if m:
            minimo_pct = float(m)
    if minimo_pct:
        datos["minimo_porcentaje"] = minimo_pct
        confianza["minimo_porcentaje"] = _CONFIANZA_ALTA

    base = _buscar_base_desde_ocr(datos, texto_limpio)
    if base:
        datos["base"] = str(base)
        confianza["base"] = _CONFIANZA_ALTA

    partes_desc = [datos["categoria"]]
    if datos["lote_casa"]:
        partes_desc.append(f"lote {datos['lote_casa']}")
    if datos["superficie"]:
        partes_desc.append(f"{datos['superficie']} m2")
    if datos["provincia"]:
        partes_desc.append(datos["provincia"])
    datos["descripcion"] = ", ".join(partes_desc)
    # La descripción es construida (no OCR-libre) a partir de campos ya validados,
    # por lo que es confiable: lleva confianza alta (no queda pendiente por esto).
    confianza["descripcion"] = _CONFIANZA_ALTA

    datos["descripcion_completa"] = texto_limpio.strip()[:3000]
    datos["codigo_fuente"] = f"det-{idx}"

    return {"datos": datos, "confianza": confianza}


def _buscar_base_desde_ocr(datos: dict, texto: str):
    try:
        from .orchestrator import _buscar_base_en_ocr
        return _buscar_base_en_ocr(datos, texto)
    except Exception as e:
        print(f"[extractor_deterministico] respaldo de base no disponible: {e}")
        return None


def _completar_cabecera_periodico(datos: dict, texto: str) -> None:
    try:
        from .orchestrator import _cabecera_periodico_desde_ocr, _pagina_prensa_desde_ocr
        cabecera = _cabecera_periodico_desde_ocr(texto)
        if cabecera and not datos.get("periodico") and not datos.get("fecha_prensa"):
            datos["periodico"], datos["fecha_prensa"] = cabecera
        pagina = _pagina_prensa_desde_ocr(texto)
        if pagina and not datos.get("pagina_prensa"):
            datos["pagina_prensa"] = pagina
    except Exception as e:
        print(f"[extractor_deterministico] cabecera de periodico no disponible: {e}")


def extraer(texto_ocr: str, pais: str = "PA") -> list[dict]:
    """Estructura el texto OCR en avisos de remate SIN IA. Formato de salida
    idéntico al de extraction.extraer: [{"datos": {...}, "confianza": {...}}]."""
    if not texto_ocr or len(texto_ocr.strip()) < 20:
        return []
    posiciones = _posiciones_avisos(texto_ocr)
    if not posiciones:
        print("[extractor_deterministico] Sin encabezados de remate en el texto")
        return []

    segmentos = []
    for i, p in enumerate(posiciones):
        fin = posiciones[i + 1] if i + 1 < len(posiciones) else len(texto_ocr)
        ini = max(p - 150, 0)
        segmentos.append((texto_ocr[ini:fin], p - ini))

    avisos = []
    for idx, (seg, header_offset) in enumerate(segmentos):
        item = _extraer_aviso(seg, pais, idx, header_offset)
        if not item["datos"].get("expediente") and not item["datos"].get("finca_matr"):
            continue
        _completar_cabecera_periodico(item["datos"], texto_ocr)
        avisos.append(item)

    print(f"[extractor_deterministico] {len(avisos)} aviso(s) de {len(segmentos)} segmento(s)")
    return avisos
